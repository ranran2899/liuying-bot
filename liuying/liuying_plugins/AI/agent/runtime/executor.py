"""工具执行器

负责按规划调用工具，支持：
1. Schema 校验（必填参数、类型）
2. 超时预算控制
3. 重试与指数退避
4. 调用指标记录（耗时/重试次数/成功失败）
5. 与证据合成器集成
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import time
from typing import Any

from liuying.utils.log import logger

from .constants import (
    DEFAULT_RETRY_COUNT,
    DEFAULT_TOOL_TIMEOUT,
    EVIDENCE_KIND_CONTEXT,
)
from .evidence import RETRYABLE_LOOKUP_TOOLS, EvidenceComposer
from .tool_catalog import tool_catalog

# 时效性搜索工具白名单（注入当前日期提升结果新鲜度）
# 仅限真实联网检索类工具，避免对插件能力查询等无关工具注入日期
_TIMESENSITIVE_SEARCH_TOOLS: set[str] = {
    "web_search",
    "fetch_webpage",
}

# 时效性关键词，命中时触发日期注入
_TIMESENSITIVE_KEYWORDS: tuple[str, ...] = (
    "最新",
    "近期",
    "现在",
    "今年",
    "今天",
    "当前",
    "最近",
    "latest",
    "recent",
    "now",
)
"""时效性关键词"""

_MAX_QUERY_VARIANTS = 3
"""单工具最多尝试的查询变体数"""

_MAX_PARALLEL_TOOLS = 3
"""研究模式下单批并发执行的工具数上限"""

_DEFAULT_CHAIN_BUDGET = 180.0
"""工具链默认时间预算（秒）"""


@dataclass(slots=True)
class ToolCallRecord:
    """工具调用记录

    Attributes:
        tool_name: 工具名
        args: 调用参数
        result: 调用结果
        elapsed: 耗时（秒）
        retries: 重试次数
        success: 是否成功
        error: 错误信息（失败时）
        timestamp: 调用时间戳
        metadata: 工具元数据
    """

    tool_name: str
    args: dict[str, Any] = field(default_factory=dict)
    result: str = ""
    elapsed: float = 0.0
    retries: int = 0
    success: bool = False
    error: str = ""
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典

        返回:
            dict: 调用记录字典
        """
        return {
            "tool_name": self.tool_name,
            "args": dict(self.args),
            "result": self.result[:500],
            "elapsed": round(self.elapsed, 3),
            "retries": self.retries,
            "success": self.success,
            "error": self.error,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class ExecutionMetrics:
    """执行指标

    Attributes:
        total_calls: 总调用次数
        success_calls: 成功调用次数
        failed_calls: 失败调用次数
        total_elapsed: 总耗时（秒）
        total_retries: 总重试次数
        by_tool: 按工具名分组的统计
    """

    total_calls: int = 0
    success_calls: int = 0
    failed_calls: int = 0
    total_elapsed: float = 0.0
    total_retries: int = 0
    by_tool: dict[str, dict[str, Any]] = field(default_factory=dict)

    def record(self, call: ToolCallRecord) -> None:
        """记录一次调用

        参数:
            call: 调用记录
        """
        self.total_calls += 1
        self.total_elapsed += call.elapsed
        self.total_retries += call.retries
        if call.success:
            self.success_calls += 1
        else:
            self.failed_calls += 1

        if call.tool_name not in self.by_tool:
            self.by_tool[call.tool_name] = {
                "total": 0,
                "success": 0,
                "failed": 0,
                "elapsed": 0.0,
                "retries": 0,
            }
        stats = self.by_tool[call.tool_name]
        stats["total"] += 1
        stats["elapsed"] += call.elapsed
        stats["retries"] += call.retries
        if call.success:
            stats["success"] += 1
        else:
            stats["failed"] += 1

    def to_dict(self) -> dict[str, Any]:
        """转换为字典

        返回:
            dict: 指标字典
        """
        return {
            "total_calls": self.total_calls,
            "success_calls": self.success_calls,
            "failed_calls": self.failed_calls,
            "total_elapsed": round(self.total_elapsed, 3),
            "total_retries": self.total_retries,
            "by_tool": dict(self.by_tool),
        }


class ToolExecutor:
    """工具执行器

    提供带超时、重试、Schema校验的工具调用能力，
    并将成功调用结果合成为证据。
    """

    def __init__(
        self,
        registry,
        evidence: EvidenceComposer | None = None,
        default_timeout: float = DEFAULT_TOOL_TIMEOUT,
        default_retries: int = DEFAULT_RETRY_COUNT,
    ) -> None:
        """初始化工具执行器

        参数:
            registry: 工具注册表
            evidence: 证据合成器，None时新建
            default_timeout: 默认工具超时（秒）
            default_retries: 默认重试次数
        """
        self._registry = registry
        self._evidence = evidence or EvidenceComposer()
        self._default_timeout = default_timeout
        self._default_retries = default_retries
        self._metrics = ExecutionMetrics()

    @property
    def evidence(self) -> EvidenceComposer:
        """获取证据合成器"""
        return self._evidence

    @property
    def metrics(self) -> ExecutionMetrics:
        """获取执行指标"""
        return self._metrics

    def validate_args(
        self, tool, args: dict[str, Any]
    ) -> tuple[bool, str]:
        """校验工具参数

        基于 JSON Schema 的 required 字段做必填校验，
        基于类型声明做基本类型校验。

        参数:
            tool: 工具实例
            args: 参数字典

        返回:
            tuple[bool, str]: (是否通过, 错误信息)
        """
        schema = tool.parameters or {}
        properties = schema.get("properties", {}) or {}
        required = schema.get("required", []) or []

        missing = [r for r in required if r not in args]
        if missing:
            return False, f"缺少必填参数: {', '.join(missing)}"

        for key, value in args.items():
            if key not in properties:
                continue
            expected_type = properties[key].get("type", "")
            if not expected_type:
                continue
            type_ok = self._check_type(value, expected_type)
            if not type_ok:
                return False, (
                    f"参数 '{key}' 类型错误，"
                    f"期望 {expected_type}，实际 {type(value).__name__}"
                )

        return True, ""

    def _check_type(self, value: Any, expected: str) -> bool:
        """检查值是否符合JSON Schema类型

        参数:
            value: 待检查值
            expected: 期望类型字符串

        返回:
            bool: 是否符合
        """
        if expected == "string":
            return isinstance(value, str)
        if expected == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if expected == "number":
            return isinstance(value, int | float) and not isinstance(
                value, bool
            )
        if expected == "boolean":
            return isinstance(value, bool)
        if expected == "array":
            return isinstance(value, list)
        if expected == "object":
            return isinstance(value, dict)
        return True

    def _filter_args(
        self, tool, args: dict[str, Any]
    ) -> dict[str, Any]:
        """过滤掉工具 schema 未声明的多余参数

        仅保留 schema properties 中定义的键，避免 LLM 误传未知键
        导致函数签名不匹配（如 get_group_members 误收 query）。

        参数:
            tool: 工具实例
            args: 原始参数字典

        返回:
            dict[str, Any]: 仅包含合法键的参数字典
        """
        schema = tool.parameters or {}
        properties = schema.get("properties", {}) or {}
        if not properties:
            return dict(args)
        return {
            k: v for k, v in args.items() if k in properties
        }

    async def execute(
        self,
        tool_name: str,
        args: dict[str, Any],
        timeout: float | None = None,
        retries: int | None = None,
    ) -> ToolCallRecord:
        """执行一次工具调用

        参数:
            tool_name: 工具名
            args: 调用参数
            timeout: 超时（秒），None时用默认
            retries: 重试次数，None时用默认

        返回:
            ToolCallRecord: 调用记录
        """
        use_timeout = timeout if timeout is not None else self._default_timeout
        use_retries = retries if retries is not None else self._default_retries

        tool = self._registry.get(tool_name)
        record = ToolCallRecord(
            tool_name=tool_name,
            args=dict(args),
            timestamp=time.time(),
            metadata=dict(tool.metadata) if tool else {},
        )
        if tool is None:
            record.error = f"工具 '{tool_name}' 不存在"
            self._metrics.record(record)
            logger.warning(
                record.error, command="AI"
            )
            return record

        if tool.is_disabled:
            record.error = f"工具 '{tool_name}' 已禁用"
            self._metrics.record(record)
            logger.debug(record.error, command="AI")
            return record

        ok, err = self.validate_args(tool, args)
        if not ok:
            record.error = err
            self._metrics.record(record)
            logger.warning(
                f"工具 '{tool_name}' 参数校验失败: {err}",
                command="AI",
            )
            return record

        # 过滤掉 schema 未声明的多余参数，避免 LLM 误传未知键
        # 导致函数签名不匹配（如 get_group_members 误收 query）
        args = self._filter_args(tool, args)
        # 时效性搜索工具注入当前日期，提升结果新鲜度
        args = self._maybe_inject_date(tool_name, args)
        record.args = dict(args)

        start = time.time()
        last_error = ""
        for attempt in range(use_retries + 1):
            try:
                result = await asyncio.wait_for(
                    tool.func(**args), timeout=use_timeout
                )
                result_text = (
                    result if isinstance(result, str) else str(result)
                )
                record.result = result_text
                record.success = True
                record.elapsed = time.time() - start
                record.retries = attempt

                # 按工具声明的证据类型分流，上下文类工具走 context 通道
                evidence_metadata = {
                    "args": dict(args),
                    "elapsed": round(record.elapsed, 3),
                    "retries": attempt,
                }
                if getattr(tool, "evidence_kind", "") == (
                    EVIDENCE_KIND_CONTEXT
                ):
                    self._evidence.add_context_evidence(
                        source=tool_name,
                        content=result_text,
                        relevance=self._estimate_relevance(result_text),
                        metadata=evidence_metadata,
                    )
                else:
                    self._evidence.add_tool_evidence(
                        tool_name=tool_name,
                        result=result_text,
                        relevance=self._estimate_relevance(result_text),
                        metadata=evidence_metadata,
                    )
                self._metrics.record(record)
                logger.debug(
                    f"工具 '{tool_name}' 执行成功，"
                    f"耗时 {record.elapsed:.2f}s，重试 {attempt} 次",
                    command="AI",
                )
                return record
            except TimeoutError:
                last_error = f"工具 '{tool_name}' 超时（{use_timeout}s）"
                logger.warning(last_error, command="AI")
            except Exception as e:
                last_error = f"工具 '{tool_name}' 执行失败: {e}"
                logger.warning(
                    last_error, command="AI", e=e
                )

            if attempt < use_retries:
                backoff = min(0.1 * (2 ** attempt), 1.0)
                await asyncio.sleep(backoff)

        record.error = last_error
        record.elapsed = time.time() - start
        record.retries = use_retries
        self._metrics.record(record)
        return record

    def _maybe_inject_date(
        self, tool_name: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        """对时效性搜索工具注入当前日期

        当工具是时效性搜索工具且query含时间关键词时，
        在query前注入当前日期，提升搜索结果新鲜度。

        参数:
            tool_name: 工具名
            args: 参数字典

        返回:
            dict[str, Any]: 可能注入日期后的参数字典
        """
        if tool_name not in _TIMESENSITIVE_SEARCH_TOOLS:
            return args
        query = str(args.get("query", "") or "").strip()
        if not query:
            return args
        lowered = query.lower()
        if not any(kw in lowered for kw in _TIMESENSITIVE_KEYWORDS):
            return args
        date_str = datetime.now().strftime("%Y年%m月")
        args = dict(args)
        args["query"] = f"{date_str} {query}"
        return args

    def _estimate_relevance(self, text: str) -> float:
        """粗略估计工具结果的相关性

        参数:
            text: 工具结果文本

        返回:
            float: 相关性评分（0-1）
        """
        if not text:
            return 0.1
        if "失败" in text or "错误" in text:
            return 0.3
        length = len(text)
        if length < 10:
            return 0.5
        if length < 100:
            return 0.7
        return 0.8

    def _select_tool(
        self, plan, exclude: set[str] | None = None
    ) -> str:
        """根据规划选择具体工具

        内联工具选择逻辑，避免对 TurnPlanner 的冗余依赖。
        优先使用规划指定的 tool_name，其次按候选/意图标签推荐。

        参数:
            plan: 回合规划
            exclude: 需排除的工具名集合

        返回:
            str: 工具名（未找到返回空串）
        """
        if plan.tool_name:
            tool = self._registry.get(plan.tool_name)
            if tool and not tool.is_disabled:
                if not exclude or plan.tool_name not in exclude:
                    return plan.tool_name

        candidates = list(plan.tool_candidates)
        if not candidates and plan.intent_tags:
            candidates = tool_catalog.recommend_tools(
                plan.intent_tags, exclude=exclude
            )

        active_names = {t.name for t in self._registry.active_tools()}
        exclude_set = exclude or set()
        for name in candidates:
            if name in active_names and name not in exclude_set:
                return name
        return ""

    def _is_satisfiable(
        self, tool_name: str, args: dict[str, Any]
    ) -> bool:
        """判断工具的必填参数能否被给定参数满足

        并发批次中除主工具外没有 LLM 给出的专属参数，
        必填参数无法满足的工具直接排除，避免白跑一次校验失败。

        参数:
            tool_name: 工具名
            args: 可用参数字典

        返回:
            bool: 必填参数是否齐备
        """
        tool = self._registry.get(tool_name)
        if tool is None or tool.is_disabled:
            return False
        required = (tool.parameters or {}).get("required") or []
        return all(key in args for key in required)

    def _pick_parallel_tools(
        self, plan, base_args: dict[str, Any]
    ) -> list[str]:
        """挑选可并发执行的工具批次

        从规划候选中取出参数可满足、彼此独立的工具，
        最多 _MAX_PARALLEL_TOOLS 个。

        参数:
            plan: 回合规划
            base_args: LLM 给出的基础参数

        返回:
            list[str]: 工具名列表，首个为规划主工具
        """
        active_names = {
            t.name for t in self._registry.active_tools()
        }
        ordered: list[str] = []
        if plan.tool_name:
            ordered.append(plan.tool_name)
        ordered.extend(plan.tool_candidates)
        if not plan.tool_candidates and plan.intent_tags:
            ordered.extend(
                tool_catalog.recommend_tools(plan.intent_tags)
            )

        picked: list[str] = []
        for name in ordered:
            if name in picked or name not in active_names:
                continue
            if picked and not self._is_satisfiable(name, base_args):
                continue
            picked.append(name)
            if len(picked) >= _MAX_PARALLEL_TOOLS:
                break
        return picked

    async def execute_batch(
        self,
        specs: list[tuple[str, dict[str, Any]]],
        time_budget: float,
    ) -> list[ToolCallRecord]:
        """并发执行一批工具调用

        单个工具失败或超时不影响同批其他工具，
        整批共享同一时间预算。

        参数:
            specs: (工具名, 参数) 列表
            time_budget: 本批时间预算（秒）

        返回:
            list[ToolCallRecord]: 与 specs 顺序一致的调用记录
        """
        if not specs:
            return []
        per_call_timeout = min(self._default_timeout, time_budget)
        results = await asyncio.gather(
            *(
                self.execute(
                    tool_name=name,
                    args=args,
                    timeout=per_call_timeout,
                )
                for name, args in specs
            ),
            return_exceptions=True,
        )

        records: list[ToolCallRecord] = []
        for (name, args), result in zip(specs, results, strict=True):
            if isinstance(result, ToolCallRecord):
                records.append(result)
                continue
            # gather 的异常已被 execute 内部消化，此分支仅兜底
            # 任务取消等极端情况，转为失败记录保持返回结构一致。
            record = ToolCallRecord(
                tool_name=name,
                args=dict(args),
                timestamp=time.time(),
                error=f"工具 '{name}' 并发执行异常: {result}",
            )
            self._metrics.record(record)
            records.append(record)
        return records

    async def execute_chain(
        self,
        plan,
        time_budget: float | None = None,
    ) -> list[ToolCallRecord]:
        """按规划链式执行工具

        当 plan.need_tool 为 True 时执行；
        当 plan.need_research 为 True 时先尝试并发批次，
        把原本 N 轮串行往返压缩为 1 轮；并发无收获时回退串行链式。
        非研究模式只调用一次。支持查询变体重试：可重试工具返回空结果时
        换用变体query重试，最多 _MAX_QUERY_VARIANTS 次。

        参数:
            plan: 回合规划
            time_budget: 时间预算（秒）

        返回:
            list[ToolCallRecord]: 调用记录列表
        """
        if not plan.need_tool:
            return []

        records: list[ToolCallRecord] = []
        budget = time_budget or _DEFAULT_CHAIN_BUDGET
        start = time.time()
        exclude: set[str] = set()

        max_steps = plan.max_steps if plan.need_research else 1

        if plan.need_research and max_steps > 1:
            batch = await self._execute_research_batch(plan, budget)
            records.extend(batch)
            exclude.update(record.tool_name for record in batch)
            if any(
                record.success
                and not self._is_empty_tool_result(record.result)
                for record in batch
            ):
                return records
            max_steps -= 1

        for step_index in range(max_steps):
            # 时间预算检查
            remaining = budget - (time.time() - start)
            if remaining <= 0:
                logger.warning(
                    f"工具链执行超时（{budget}s），停止",
                    command="AI",
                )
                break

            tool_name = self._select_tool(plan, exclude)
            if not tool_name:
                break

            # 首步用LLM给出的tool_args；后续研究步骤用空参数
            base_args = plan.tool_args if step_index == 0 else {}

            # 查询变体重试：可重试工具空结果时换变体
            record = await self._execute_with_variants(
                tool_name=tool_name,
                base_args=base_args,
                plan=plan,
                remaining_budget=remaining,
            )
            records.append(record)
            exclude.add(tool_name)

            if not record.success:
                break
            if not plan.need_research:
                break

        return records

    async def _execute_research_batch(
        self, plan, budget: float
    ) -> list[ToolCallRecord]:
        """执行研究模式的并发首批工具

        单工具时退化为普通执行（含查询变体重试），
        多工具时并发执行，把多轮网络往返压缩为一轮。

        参数:
            plan: 回合规划
            budget: 时间预算（秒）

        返回:
            list[ToolCallRecord]: 调用记录列表
        """
        base_args = dict(plan.tool_args or {})
        picked = self._pick_parallel_tools(plan, base_args)
        if not picked:
            return []
        if len(picked) == 1:
            return [
                await self._execute_with_variants(
                    tool_name=picked[0],
                    base_args=base_args,
                    plan=plan,
                    remaining_budget=budget,
                )
            ]

        specs = [
            (name, base_args if index == 0 else dict(base_args))
            for index, name in enumerate(picked)
        ]
        records = await self.execute_batch(specs, budget)
        logger.debug(
            f"并发研究批次完成: {len(picked)}个工具，"
            f"成功{sum(r.success for r in records)}个",
            command="AI",
        )
        return records

    async def _execute_with_variants(
        self,
        tool_name: str,
        base_args: dict[str, Any],
        plan,
        remaining_budget: float,
    ) -> ToolCallRecord:
        """带查询变体重试的工具执行

        可重试工具（RETRYABLE_LOOKUP_TOOLS）返回空结果时，
        生成查询变体重试，最多 _MAX_QUERY_VARIANTS 次。
        非可重试工具直接执行一次。

        参数:
            tool_name: 工具名
            base_args: 基础参数
            plan: 回合规划
            remaining_budget: 剩余时间预算（秒）

        返回:
            ToolCallRecord: 调用记录
        """
        # 非可重试工具直接执行
        if tool_name not in RETRYABLE_LOOKUP_TOOLS:
            return await self.execute(
                tool_name=tool_name,
                args=base_args,
                timeout=min(self._default_timeout, remaining_budget),
            )

        # 生成查询变体
        variants = self._generate_query_variants(base_args, plan)
        variant_start = time.time()
        last_record = ToolCallRecord(
            tool_name=tool_name,
            args=dict(base_args),
            timestamp=variant_start,
        )

        for variant_args in variants[:_MAX_QUERY_VARIANTS]:
            # 预算基于批次起点累计，否则每轮重置导致预算永不耗尽
            remaining = remaining_budget - (
                time.time() - variant_start
            )
            if remaining <= 0:
                last_record.error = (
                    f"工具 '{tool_name}' 查询变体超时"
                )
                break
            record = await self.execute(
                tool_name=tool_name,
                args=variant_args,
                timeout=min(self._default_timeout, remaining),
            )
            last_record = record
            # 成功且非空结果，直接返回
            if record.success and record.result.strip():
                if not self._is_empty_tool_result(record.result):
                    return record
            logger.debug(
                f"工具 '{tool_name}' 查询变体返回空结果，"
                f"尝试下一个变体",
                command="AI",
            )

        return last_record

    def _generate_query_variants(
        self, base_args: dict[str, Any], plan
    ) -> list[dict[str, Any]]:
        """生成查询变体列表

        优先使用查询改写器生成的高质量候选查询（plan.query_candidates），
        不足时补充规则变体（用户原始消息、截取前半部分）。
        参考参考插件 _query_variants_for_tool 的多候选词重试策略。

        参数:
            base_args: 基础参数
            plan: 回合规划

        返回:
            list[dict[str, Any]]: 变体参数列表
        """
        variants: list[dict[str, Any]] = [dict(base_args)]
        query = str(base_args.get("query", "") or "").strip()
        existing: set[str] = {query}
        # 优先使用查询改写器生成的候选查询（高质量，已去口语化）
        candidates = list(getattr(plan, "query_candidates", []) or [])
        for candidate in candidates[:_MAX_QUERY_VARIANTS]:
            cand = str(candidate or "").strip()[:200]
            if cand and cand not in existing:
                variant = dict(base_args)
                variant["query"] = cand
                variants.append(variant)
                existing.add(cand)
                if len(variants) >= _MAX_QUERY_VARIANTS:
                    return variants
        # 补充规则变体：用用户原始消息作为query
        user_msg = str(getattr(plan, "user_message", "") or "").strip()
        if user_msg and user_msg not in existing:
            variant = dict(base_args)
            variant["query"] = user_msg[:200]
            variants.append(variant)
            existing.add(user_msg)
        # 补充规则变体：截取query前半部分（简化查询）
        if len(query) > 20 and len(variants) < _MAX_QUERY_VARIANTS:
            short_query = query[:20]
            if short_query not in existing:
                variant = dict(base_args)
                variant["query"] = short_query
                variants.append(variant)
        return variants

    @staticmethod
    def _is_empty_tool_result(text: str) -> bool:
        """判断工具结果是否为空

        参数:
            text: 工具结果文本

        返回:
            bool: 是否为空结果
        """
        if not text or not text.strip():
            return True
        lowered = text.strip().lower()
        markers = (
            "未找到",
            "没有找到",
            "无结果",
            "no_results",
            "暂无",
            "搜索失败",
            "未检索到",
        )
        return any(marker in lowered for marker in markers)

    def reset(self) -> None:
        """重置执行器状态（清空指标与证据）"""
        self._metrics = ExecutionMetrics()
        self._evidence.clear()
