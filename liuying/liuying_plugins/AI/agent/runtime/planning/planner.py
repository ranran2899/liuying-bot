"""回合规划器

基于用户消息和上下文，决策本回合的行为：
回复/沉默/请求澄清，以及是否需要工具调用、记忆召回、视觉理解、
网络搜索等。输出 TurnPlan 结构供执行器和响应器消费。
"""

from liuying.utils.log import logger

from ....config import get_config
from ....core.llm import llm_helper
from ....core.vision import vision_router
from ..catalog.tool_catalog import ToolCatalog, tool_catalog
from ..constants import (
    INTENT_TAG_IMAGE,
    OUTPUT_MODE_CHAT_ANSWER,
    OUTPUT_MODE_CHAT_SHORT,
    OUTPUT_MODE_SILENCE,
    OUTPUT_MODE_SOURCE_SUMMARY,
    OUTPUT_MODE_STRUCTURED_HELP,
    TURN_ACTION_ASK_CLARIFY,
    TURN_ACTION_REPLY,
    TURN_ACTION_SILENCE,
)
from .intent_rules import IntentRuleManager, _get_agent_max_steps
from .json_utils import extract_json_payload
from .types import TurnPlan

# 向后兼容：外部模块通过 planner.TurnPlan / planner.extract_json_payload 访问
__all__ = ["TurnPlan", "TurnPlanner", "extract_json_payload"]

_PLAN_SYSTEM_PROMPT = """你是ai回合规划器。
分析用户消息和上下文，决策本回合的最佳行为。

可选动作：
- reply: 直接回复用户
- silence: 保持沉默（不相关或无需回应）
- ask_clarify: 请求澄清（信息不足）

可选输出模式：
- chat_short: 短聊天回复（闲聊、问候）
- chat_answer: 完整答案回复（问答、解释）
- structured_help: 结构化帮助（求助、命令查询）
- source_summary: 来源摘要（带工具证据的回答）
- silence: 静默

意图标签集合：
- realtime: 实时信息查询（新闻、天气、股价）
- memory: 记忆召回（过往互动、用户偏好）
- image: 图片相关（看图、生成图）
- network: 网络请求（搜索、抓取）
- admin: 管理操作（开关、配置）
- local: 本地操作（时间、计算）
- plugin: 插件调用（特定功能）

请用JSON格式返回决策，字段如下：
- action: 动作（reply/silence/ask_clarify）
- output_mode: 输出模式
- intent_tags: 意图标签数组
- need_tool: 是否需要工具调用
- tool_candidates: 候选工具名数组（need_tool为true时填写）
- tool_args: 工具参数对象（单工具调用时填写）
- need_memory: 是否需要记忆召回
- memory_query: 记忆查询文本
- need_vision: 是否需要视觉理解
- need_research: 是否需要多步研究
- ambiguity_level: 模糊度（0-1，0最清晰）
- reason: 决策理由（一句话）

只返回JSON，不要其他内容。"""

_PLAN_USER_TEMPLATE = """用户消息: {user_message}

上下文摘要: {context_summary}

可用工具目录:
{catalog_prompt}

请输出回合规划JSON。"""


class TurnPlanner:
    """回合规划器

    使用LLM分析用户消息和上下文，生成本回合的规划。
    支持基于规则的快速决策和基于LLM的精细决策两种模式。
    """

    def __init__(self, llm=None, catalog: ToolCatalog | None = None) -> None:
        """初始化回合规划器

        参数:
            llm: LLM助手，None时使用模块单例
            catalog: 工具目录，None时延迟到_get_catalog获取全局单例
        """
        self._llm = llm
        self._catalog = catalog
        self._rule_manager = IntentRuleManager()

    def _get_llm(self):
        """获取LLM助手，None时回退到模块单例"""
        if self._llm is None:
            self._llm = llm_helper
        return self._llm

    def _get_catalog(self) -> ToolCatalog:
        """获取工具目录单例"""
        if self._catalog is not None:
            return self._catalog
        self._catalog = tool_catalog
        return self._catalog

    def plan_fast(
        self,
        user_message: str,
        context_summary: str = "",
        has_image: bool = False,
    ) -> TurnPlan:
        """快速规则决策（无LLM调用）

        适用于低延迟场景的快速决策，覆盖常见意图。
        使用 IntentRuleManager 按优先级匹配关键词规则，
        未匹配时根据 has_image 走视觉路由或返回默认聊天。

        参数:
            user_message: 用户消息
            context_summary: 上下文摘要
            has_image: 是否包含图片

        返回:
            TurnPlan: 规划结果
        """
        text = user_message.strip().lower()
        if not text:
            return TurnPlan(
                action=TURN_ACTION_SILENCE,
                output_mode=OUTPUT_MODE_SILENCE,
                reason="空消息",
                user_message=user_message,
            )

        # 按优先级匹配意图规则
        rule = self._rule_manager.match(text)
        if rule:
            return rule.to_plan(user_message)

        # 图片输入（未匹配到关键词时）
        if has_image:
            vision_hint, supports = self._check_vision_capability()
            return TurnPlan(
                action=TURN_ACTION_REPLY,
                output_mode=OUTPUT_MODE_CHAT_ANSWER,
                intent_tags=[INTENT_TAG_IMAGE],
                need_vision=True,
                vision_hint=vision_hint,
                reason=(
                    "图片输入（视觉支持）"
                    if supports
                    else "图片输入（降级到描述模式）"
                ),
                user_message=user_message,
            )

        # 默认：短聊天
        return TurnPlan(
            action=TURN_ACTION_REPLY,
            output_mode=OUTPUT_MODE_CHAT_SHORT,
            intent_tags=[],
            need_memory=False,
            ambiguity_level=0.2,
            reason="默认聊天回复",
            user_message=user_message,
        )

    def _check_vision_capability(self) -> tuple[str, bool]:
        """检测当前LLM的视觉能力

        通过 vision_router.detect_by_keyword 检查配置的默认
        chat model 关键词，快速判断是否支持视觉理解。

        返回:
            tuple[str, bool]: (视觉提示文本, 是否支持视觉)
        """
        try:
            model = str(get_config("CHAT_MODEL", "") or "")
            supports, confidence = (
                vision_router.detect_by_keyword(model)
            )
            if supports:
                return (
                    f"用户发送了图片，路由到视觉模型（置信度{confidence:.2f}）",
                    True,
                )
            return (
                "用户发送了图片，当前模型可能不支持视觉，降级到描述注入",
                False,
            )
        except Exception:
            return ("用户发送了图片，需要视觉理解", True)

    async def plan(
        self,
        user_message: str,
        context_summary: str = "",
        has_image: bool = False,
        use_llm: bool = True,
    ) -> TurnPlan:
        """生成本回合规划

        参数:
            user_message: 用户消息
            context_summary: 上下文摘要
            has_image: 是否包含图片
            use_llm: 是否使用LLM精细决策，False时用快速规则

        返回:
            TurnPlan: 规划结果
        """
        if not use_llm:
            return self.plan_fast(user_message, context_summary, has_image)

        catalog = self._get_catalog()
        catalog_prompt = catalog.build_catalog_prompt()
        if not catalog_prompt:
            catalog_prompt = "（无注册工具）"

        prompt = _PLAN_USER_TEMPLATE.format(
            user_message=user_message[:500],
            context_summary=context_summary[:300] or "（无）",
            catalog_prompt=catalog_prompt,
        )

        try:
            llm = self._get_llm()
            _, response = await llm.chat(
                [
                    {"role": "system", "content": _PLAN_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0.1},
            )
            plan = self._parse_plan_response(response, user_message)
            if has_image:
                plan.need_vision = True
                if not plan.vision_hint:
                    plan.vision_hint = "用户消息附带图片"
                plan = await self._augment_plan_with_vision_route(plan)
            return plan
        except Exception as e:
            logger.warning(
                f"LLM规划失败，降级到快速规则: {e}",
                command="AI",
                e=e,
            )
            return self.plan_fast(user_message, context_summary, has_image)

    async def _augment_plan_with_vision_route(
        self, plan: TurnPlan
    ) -> TurnPlan:
        """根据视觉能力路由结果增强规划

        当规划需要视觉时，调用 vision_router 探测当前 provider
        是否支持视觉，将路由信息写入 vision_hint 以供执行器参考。
        不支持视觉时附加降级提示，但不修改 need_vision。

        参数:
            plan: 原始规划

        返回:
            TurnPlan: 增强后的规划
        """
        if not plan.need_vision:
            return plan
        try:
            route = await vision_router.route_vision_request()
            if route.success:
                extra = (
                    f"（视觉provider: {route.provider}/{route.model}）"
                )
                if route.info and route.info.confidence > 0:
                    extra += f" 置信度{route.info.confidence:.2f}"
                plan.vision_hint = (
                    f"{plan.vision_hint}{extra}".strip()
                )
            elif route.fallback_used:
                plan.vision_hint = (
                    f"{plan.vision_hint}"
                    f"（降级: {route.fallback_reason}）"
                ).strip()
        except Exception as e:
            logger.debug(
                f"视觉路由增强规划失败: {e}",
                command="AI",
                e=e,
            )
        return plan

    def _parse_plan_response(
        self, response: str, user_message: str
    ) -> TurnPlan:
        """解析LLM规划响应

        使用 extract_json_payload 三重兜底提取JSON，
        失败时降级到快速规则决策。

        参数:
            response: LLM响应文本
            user_message: 原始用户消息（兜底用）

        返回:
            TurnPlan: 解析后的规划
        """
        data = extract_json_payload(response)
        if data is None:
            logger.debug(
                "解析规划JSON失败，降级到快速规则",
                command="AI",
            )
            return self.plan_fast(user_message)

        action = str(data.get("action", TURN_ACTION_REPLY))
        if action not in (
            TURN_ACTION_REPLY,
            TURN_ACTION_SILENCE,
            TURN_ACTION_ASK_CLARIFY,
        ):
            action = TURN_ACTION_REPLY

        output_mode = str(data.get("output_mode", OUTPUT_MODE_CHAT_SHORT))
        if output_mode not in (
            OUTPUT_MODE_CHAT_SHORT,
            OUTPUT_MODE_CHAT_ANSWER,
            OUTPUT_MODE_STRUCTURED_HELP,
            OUTPUT_MODE_SOURCE_SUMMARY,
            OUTPUT_MODE_SILENCE,
        ):
            output_mode = OUTPUT_MODE_CHAT_SHORT

        intent_tags = [
            str(t) for t in data.get("intent_tags", []) if t
        ]

        tool_args_raw = data.get("tool_args", {})
        tool_args = (
            tool_args_raw if isinstance(tool_args_raw, dict) else {}
        )

        ambiguity = float(data.get("ambiguity_level", 0.0))
        ambiguity = max(0.0, min(1.0, ambiguity))

        # 从配置读取上限，允许运行时调整Agent最大步数
        config_max = _get_agent_max_steps()
        try:
            max_steps = int(data.get("max_steps", config_max))
        except (TypeError, ValueError):
            max_steps = config_max
        max_steps = max(1, min(max_steps, config_max))

        return TurnPlan(
            action=action,
            output_mode=output_mode,
            intent_tags=intent_tags,
            need_tool=bool(data.get("need_tool", False)),
            tool_candidates=[
                str(t) for t in data.get("tool_candidates", []) if t
            ],
            tool_name=str(data.get("tool_name", "")),
            tool_args=tool_args,
            need_memory=bool(data.get("need_memory", False)),
            memory_query=str(data.get("memory_query", "")),
            need_vision=bool(data.get("need_vision", False)),
            vision_hint=str(data.get("vision_hint", "")),
            need_research=bool(data.get("need_research", False)),
            ambiguity_level=ambiguity,
            max_steps=max_steps,
            reason=str(data.get("reason", "")),
            user_message=user_message,
        )

    def select_tool(
        self,
        plan: TurnPlan,
        registry,
        exclude: set[str] | None = None,
    ) -> str:
        """根据规划选择具体工具

        参数:
            plan: 回合规划
            registry: 工具注册表
            exclude: 需排除的工具名集合

        返回:
            str: 工具名（未找到返回空串）
        """
        if plan.tool_name:
            tool = registry.get(plan.tool_name)
            if tool and not tool.is_disabled:
                if not exclude or plan.tool_name not in exclude:
                    return plan.tool_name

        candidates = list(plan.tool_candidates)
        if not candidates and plan.intent_tags:
            catalog = self._get_catalog()
            candidates = catalog.recommend_tools(
                plan.intent_tags, exclude=exclude
            )

        active_names = {
            t.name for t in registry.active_tools()
        }
        exclude_set = exclude or set()
        for name in candidates:
            if name in active_names and name not in exclude_set:
                return name
        return ""
