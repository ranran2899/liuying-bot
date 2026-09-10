"""回合规划器

基于用户消息和上下文，决策本回合的行为：
回复/沉默/请求澄清，以及是否需要工具调用、记忆召回、视觉理解、
网络搜索等。输出 TurnPlan 结构供执行器和响应器消费。
"""

from liuying.utils.log import logger

from ...config import get_config
from ...core.chat_intent import semantic_frame_inferrer
from ...core.llm import llm_helper
from ...core.llm.model_router import ROLE_INTENT, model_router
from ...core.vision import vision_router
from .constants import (
    INTENT_TAG_IMAGE,
    OUTPUT_MODE_CHAT_ANSWER,
    OUTPUT_MODE_CHAT_SHORT,
    OUTPUT_MODE_SILENCE,
    TURN_ACTION_ASK_CLARIFY,
    TURN_ACTION_REPLY,
    TURN_ACTION_SILENCE,
)
from .intent_rules import IntentRuleManager
from .plan_types import (
    TurnPlan,
    extract_json_payload,
    metadata_fallback_turn_plan,
    parse_turn_plan_payload,
)
from .tool_catalog import ToolCatalog, tool_catalog

__all__ = ["TurnPlan", "TurnPlanner"]


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
        self._registry = None
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

    def _get_registry(self):
        """获取工具注册表单例

        延迟导入避免真实循环依赖：agent.tools 包在导入期
        引用 runtime.session_context/constants，而 planner 由
        runtime 包初始化时导入，顶部导入 tools 会成环。
        """
        if self._registry is None:
            from ..tools import tool_registry

            self._registry = tool_registry
        return self._registry

    def plan_fast(
        self,
        user_message: str,
        has_image: bool = False,
    ) -> TurnPlan:
        """快速规则决策（无LLM调用）

        适用于低延迟场景的快速决策，覆盖常见意图。
        使用 IntentRuleManager 按优先级匹配关键词规则，
        未匹配时根据 has_image 走视觉路由或返回默认聊天。

        参数:
            user_message: 用户消息
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
            ambiguity_level="low",
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
        model = str(get_config("CHAT_MODEL", {}).get("model", "") or "")
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

    async def plan(
        self,
        user_message: str,
        context_summary: str = "",
        has_image: bool = False,
        use_llm: bool = True,
        is_group: bool = False,
        is_at_bot: bool = False,
    ) -> TurnPlan:
        """生成本回合规划

        参数:
            user_message: 用户消息
            context_summary: 上下文摘要
            has_image: 是否包含图片
            use_llm: 是否使用LLM精细决策，False时用快速规则
            is_group: 是否群聊（用于LLM失败时的元数据兜底）
            is_at_bot: 是否@bot或直呼bot（用于元数据兜底防误插话）

        返回:
            TurnPlan: 规划结果
        """
        if not use_llm:
            plan = self.plan_fast(user_message, has_image)
        else:
            plan = await self._plan_with_llm(
                user_message,
                context_summary,
                has_image,
                is_group=is_group,
                is_at_bot=is_at_bot,
            )

        # 语义帧增强（独立于LLM规划路径，覆盖规则与LLM两种模式）
        plan = await self._augment_plan_with_semantic_frame(
            plan, user_message, context_summary
        )
        return plan

    async def _plan_with_llm(
        self,
        user_message: str,
        context_summary: str,
        has_image: bool,
        is_group: bool = False,
        is_at_bot: bool = False,
    ) -> TurnPlan:
        """LLM精细规划

        先用元数据兜底生成 fallback，LLM 调用失败或解析失败时
        返回 fallback。LLM 成功时用 parse_turn_plan_payload 解析。
        保留 max_tokens=800 的token优化，
        以及 has_image 的视觉路由增强。

        参数:
            user_message: 用户消息
            context_summary: 上下文摘要
            has_image: 是否包含图片
            is_group: 是否群聊（元数据兜底防误插话）
            is_at_bot: 是否@bot或直呼bot（元数据兜底防误插话）

        返回:
            TurnPlan: 规划结果
        """
        # 元数据兜底：传入完整会话元数据，群聊未@bot时倾向静默
        fallback = metadata_fallback_turn_plan(
            is_group=is_group,
            is_random_chat=is_group and not is_at_bot,
            is_direct_mention=is_at_bot,
            has_images=has_image,
        )
        fallback.user_message = user_message

        registry = self._get_registry()
        tool_metadata_text = self._render_tool_metadata(registry)

        system_prompt = (
            "你是群聊/私聊的回合规划器，只判断本轮应该做什么，"
            "不写最终回复。"
            "输出严格JSON，不要markdown，不要解释。\n"
            "JSON结构："
            '{"action":"reply|silence|ask_clarify",'
            '"output_mode":"chat_short|chat_answer|'
            'structured_help|source_summary|silence",'
            '"intent_tags":["realtime|memory|image|network|admin|local|plugin"],'
            '"need_tool":false,'
            '"tool_candidates":[],'
            '"tool_args":{},'
            '"need_memory":false,'
            '"memory_query":"",'
            '"need_vision":false,'
            '"need_research":false,'
            '"ambiguity_level":"low|medium|high",'
            '"confidence":0.0,'
            '"message_target":"bot|someone_else|broadcast|uncertain",'
            '"session_goal":"一句短中文目标",'
            '"reason":"极短中文原因"}\n'
            "判别要求：\n"
            "1. action只决定回不回复；群聊不确定是否cue bot时用silence\n"
            "2. message_target由@、引用、称呼、上下文共同判断；"
            "uncertain时通常silence\n"
            "3. 风格、用户态度、bot情绪、TTS和表情不要在这里决定\n"
            "4. 工具意图只给候选方向，不要因为工具存在就强行使用\n"
            "5. need_research=true只给明显需要多源查证、时效或争议的问题\n"
            "6. output_mode控制最终回复长度：chat_short接梗(8-40字)，"
            "chat_answer普通答(30-120字)，structured_help教程(80-300字)，"
            "source_summary检索摘要(80-240字)\n"
            "7. ambiguity_level用low/medium/high，high时建议ask_clarify"
        )

        user_content_parts = [
            f"最新消息：{user_message[:500]}",
            f"最近上下文：{context_summary[:900] or '无'}",
            f"是否有图片：{'是' if has_image else '否'}",
            f"可用工具元数据：\n{tool_metadata_text}",
            f"metadata fallback：action={fallback.action}, "
            f"output_mode={fallback.output_mode}, "
            f"target={fallback.message_target}",
            "请输出回合规划JSON。",
        ]
        user_prompt = "\n".join(user_content_parts)

        try:
            llm = self._get_llm()
            role = model_router.resolve(ROLE_INTENT)
            # 限制输出token：规划JSON约400-600 tokens
            plan_options = role.apply_to_options(
                {"max_tokens": 800}
            )
            _, response = await llm.chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                model=role.model or None,
                options=plan_options,
                provider_name=role.provider or None,
            )
            plan = self._parse_plan_response(
                response, user_message, fallback
            )
            if has_image:
                plan.need_vision = True
                if not plan.vision_hint:
                    plan.vision_hint = "用户消息附带图片"
                plan = await self._augment_plan_with_vision_route(plan)
            return plan
        except Exception as e:
            logger.warning(
                f"LLM规划失败，降级到兜底规划: {e}",
                command="AI",
                e=e,
            )
            return fallback

    def _render_tool_metadata(self, registry) -> str:
        """渲染工具元数据供规划prompt使用

        参考参考插件 tool_catalog.build_catalog_prompt：
        渲染工具名、描述、必填参数和意图标签，让LLM能正确
        生成 tool_args（含必填参数），而非仅知道工具候选方向。

        参数:
            registry: 工具注册表

        返回:
            str: 工具元数据文本，无工具时返回"无"
        """
        lines = []
        for tool in registry.active_tools()[:24]:
            tags = (
                ",".join(tool.intent_tags[:5])
                if tool.intent_tags
                else "none"
            )
            # 渲染工具描述（截断到80字，避免prompt过长）
            desc = (tool.description or "").strip()[:80]
            # 渲染必填参数，帮助LLM生成合法tool_args
            schema = tool.parameters or {}
            required = schema.get("required", []) or []
            props = schema.get("properties", {}) or {}
            req_str = ""
            if required:
                req_parts = []
                for r in required:
                    rprop = props.get(r, {})
                    rdesc = str(rprop.get("description", ""))[:40]
                    req_parts.append(f"{r}({rdesc})" if rdesc else r)
                req_str = " required=[" + ",".join(req_parts) + "]"
            lines.append(f"- {tool.name}: {desc}{req_str} tags={tags}")
        return "\n".join(lines) if lines else "无"

    async def _augment_plan_with_semantic_frame(
        self,
        plan: TurnPlan,
        user_message: str,
        context_summary: str,
    ) -> TurnPlan:
        """用语义帧增强规划

        直接用 semantic_frame_inferrer.infer_fast 规则推断语义帧
        （新prompt为扁平结构，LLM不再输出内嵌semantic_frame），
        将 recommend_silence/requires_emotional_care/sticker_appropriate
        等信号应用到规划，并把完整语义帧字典写入 plan.semantic_frame
        供响应器消费 tts_style_hint/sticker_mood_hint/bot_emotion 等字段。

        参数:
            plan: 原始规划
            user_message: 用户消息
            context_summary: 上下文摘要

        返回:
            TurnPlan: 增强后的规划
        """
        if not get_config("CHAT_INTENT_ENABLED", True):
            return plan

        # 规则快速推断语义帧（无LLM调用）
        try:
            frame = semantic_frame_inferrer.infer_fast(user_message)
            frame_dict = frame.to_dict()
        except Exception as e:
            logger.debug(
                f"语义帧规则推断失败，跳过增强: {e}",
                command="AI",
                e=e,
            )
            return plan

        plan.semantic_frame = frame_dict

        # 静默建议优先级最高：覆盖规划动作
        if frame_dict.get("recommend_silence") and plan.action == TURN_ACTION_REPLY:
            plan.action = TURN_ACTION_SILENCE
            plan.output_mode = OUTPUT_MODE_SILENCE
            if plan.reason:
                plan.reason = f"{plan.reason}（语义帧建议静默）"
            else:
                plan.reason = "语义帧建议静默"
            return plan

        # 情感关怀：附加意图标签，提示响应器采用温和风格
        if frame_dict.get("requires_emotional_care"):
            if "emotional_care" not in plan.intent_tags:
                plan.intent_tags.append("emotional_care")

        # 贴纸适配：附加意图标签，提示响应器可发贴纸
        if frame_dict.get("sticker_appropriate"):
            if "sticker" not in plan.intent_tags:
                plan.intent_tags.append("sticker")

        # 元问题：附加意图标签，提示走人格/帮助路径
        if frame_dict.get("meta_question"):
            if "meta_question" not in plan.intent_tags:
                plan.intent_tags.append("meta_question")

        # 模糊度：语义帧float(0-1)映射到low/medium/high字符串
        frame_ambiguity = float(
            frame_dict.get("ambiguity_level", 0.0) or 0.0
        )
        if frame_ambiguity > 0:
            if frame_ambiguity >= 0.7:
                plan.ambiguity_level = "high"
                if plan.action == TURN_ACTION_REPLY:
                    plan.action = TURN_ACTION_ASK_CLARIFY
                    if not plan.reason:
                        plan.reason = "语义帧判断模糊度较高，请求澄清"
            elif frame_ambiguity >= 0.3:
                plan.ambiguity_level = "medium"
            else:
                plan.ambiguity_level = "low"

        return plan

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
        self,
        response: str,
        user_message: str,
        fallback: TurnPlan,
    ) -> TurnPlan:
        """解析LLM规划响应

        使用 extract_json_payload 提取JSON，parse_turn_plan_payload
        解析为TurnPlan（含枚举白名单校验）。提取或解析失败时返回
        fallback 兜底规划。

        参数:
            response: LLM响应文本
            user_message: 原始用户消息（写入plan.user_message）
            fallback: 解析失败时的兜底规划

        返回:
            TurnPlan: 解析后的规划，失败返回fallback
        """
        data = extract_json_payload(response)
        if data is None:
            logger.debug(
                "解析规划JSON失败，降级到兜底规划",
                command="AI",
            )
            return fallback
        plan = parse_turn_plan_payload(data)
        if plan is None:
            logger.debug(
                "规划payload校验失败，降级到兜底规划",
                command="AI",
            )
            return fallback
        plan.user_message = user_message
        return plan
