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
import time
from typing import Any

from liuying.utils.log import logger

from ..constants import (
    DEFAULT_RETRY_COUNT,
    DEFAULT_TOOL_TIMEOUT,
    EVIDENCE_KIND_CONTEXT,
)
from ..planning.planner import TurnPlanner
from .evidence import EvidenceComposer


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
        self._planner = TurnPlanner()

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

    def _fill_context_args(
        self,
        tool_name: str,
        args: dict[str, Any],
        plan,
    ) -> dict[str, Any]:
        """根据回合规划填充上下文参数

        对需要 user_id / group_id 的工具自动注入当前会话上下文，
        并对检索类工具的 query、find_group_member 的 name 等必填
        参数做兜底填充，避免 LLM 漏传必填项导致工具校验失败。

        参数:
            tool_name: 工具名
            args: LLM 给出的原始参数
            plan: 回合规划（含上下文）

        返回:
            dict[str, Any]: 填充后的参数
        """
        filled = dict(args)
        tool = self._registry.get(tool_name)
        if tool is None:
            return filled

        schema = tool.parameters or {}
        properties = schema.get("properties", {}) or {}

        if "user_id" in properties and not filled.get("user_id"):
            filled["user_id"] = plan.user_id or ""

        if "group_id" in properties and not filled.get("group_id"):
            filled["group_id"] = plan.group_id or ""

        # persona_name 自动注入：确保工具调用使用当前用户的人格上下文
        if "persona_name" in properties and not filled.get("persona_name"):
            filled["persona_name"] = plan.persona_name or "default"

        # 检索类工具的 query 参数兜底：LLM 漏传时用用户消息填充
        if (
            tool_name in ("recall_memory", "search_plugin_knowledge", "web_search")
            and "query" in properties
            and not filled.get("query")
        ):
            filled["query"] = (
                plan.user_message or plan.memory_query or ""
            )

        # find_group_member 的 name 参数兜底：LLM 漏传时用用户消息填充
        # 用户消息中通常包含被查找的成员名称关键词
        if (
            tool_name == "find_group_member"
            and "name" in properties
            and not filled.get("name")
        ):
            filled["name"] = plan.user_message or ""

        return filled

    async def execute_chain(
        self,
        plan,
        time_budget: float | None = None,
    ) -> list[ToolCallRecord]:
        """按规划链式执行工具

        当 plan.need_tool 为 True 时执行；
        当 plan.need_research 为 True 时允许多步调用，
        否则只调用一次。

        参数:
            plan: 回合规划
            time_budget: 时间预算（秒）

        返回:
            list[ToolCallRecord]: 调用记录列表
        """
        if not plan.need_tool:
            return []

        records: list[ToolCallRecord] = []
        budget = time_budget or 180.0
        start = time.time()
        exclude: set[str] = set()

        max_steps = plan.max_steps if plan.need_research else 1

        for step_index in range(max_steps):
            if time.time() - start >= budget:
                logger.warning(
                    f"工具链执行超时（{budget}s），停止",
                    command="AI",
                )
                break

            planner = self._planner
            tool_name = planner.select_tool(plan, self._registry, exclude)
            if not tool_name:
                break

            # 仅首步使用 LLM 给出的 tool_args；
            # 后续研究步骤使用空参数，依赖 _fill_context_args 注入
            # 上下文（user_id/group_id/query 兜底），避免不同工具
            # 共用同一份参数导致校验失败或参数错传。
            raw_args = plan.tool_args if step_index == 0 else {}
            args = self._fill_context_args(tool_name, raw_args, plan)
            record = await self.execute(
                tool_name=tool_name,
                args=args,
            )
            records.append(record)
            exclude.add(tool_name)

            if not record.success:
                break
            if not plan.need_research:
                break

        return records

    def reset(self) -> None:
        """重置执行器状态（清空指标与证据）"""
        self._metrics = ExecutionMetrics()
        self._evidence.clear()
