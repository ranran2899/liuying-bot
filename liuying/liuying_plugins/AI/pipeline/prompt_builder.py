"""系统提示词构建器

从 ReplyProcessor 中抽出的提示词组装逻辑，负责整合人格、
上下文、情绪、记忆、群风格、话题线程、社交上下文、
安全过滤、回复风格策略、环境感知等所有提示词片段。
"""

import asyncio

from liuying.utils.log import logger

from ..config import get_config
from ..core.context import ContextPolicy, context_manager, thread_tracker
from ..core.emotion import emotion_manager
from ..core.group import group_social
from ..core.group.profile import ProfileToolkit, group_profile
from ..core.memory import memory_manager
from ..core.peer_awareness import peer_awareness
from ..core.persona import persona_manager
from ..core.safety import SafetyFilter
from .humanize import HumanizeToolkit
from .types import ReplyContext


class PromptBuilder:
    """系统提示词构建器

    使用用户当前激活的人格构建提示词，并注入对应人格的
    情绪状态与记忆，确保人设间数据隔离。
    """

    async def build_system_prompt(
        self, ctx: ReplyContext, history: list[dict[str, str]]
    ) -> str:
        """构建系统提示词

        参数:
            ctx: 回复上下文
            history: 历史消息列表（用于anti-loop检测）

        返回:
            str: 完整系统提示词
        """
        async def _load_memory_prompt() -> str:
            # 记忆召回属外部不确定性IO，失败时降级为空串
            if not get_config("MEMORY_ENABLED", True):
                return ""
            try:
                return await memory_manager.build_memory_prompt(
                    ctx.user_id,
                    ctx.text,
                    ctx.group_id,
                    top_k=get_config("MEMORY_RECALL", {}).get("top_k", 5),
                    persona_name=ctx.persona_name,
                )
            except Exception as e:
                logger.debug(
                    f"记忆召回失败，降级到无记忆模式: {e}",
                    command="AI",
                    e=e,
                )
                return ""

        # 人格/上下文/情绪/记忆四路独立IO并行加载，缩短总耗时；
        # 记忆路失败已在内部降级，其余三路异常语义与原串行一致
        persona, context_prompt, emotion_prompt, memory_prompt = (
            await asyncio.gather(
                persona_manager.get_user_persona_config(ctx.user_id),
                context_manager.build_full_context_prompt(ctx.group_id),
                emotion_manager.build_emotion_prompt_for_user(
                    ctx.user_id,
                    ctx.group_id,
                    persona_name=ctx.persona_name,
                ),
                _load_memory_prompt(),
            )
        )
        base_prompt = await persona_manager.build_system_prompt(
            persona, ctx.user_id, ctx.group_id
        )

        parts = [base_prompt, context_prompt, emotion_prompt, memory_prompt]

        parts.append(context_manager.get_time_flavor_prompt())

        if ctx.group_id:
            # 群风格只读注入：抽取与持久化由 group_style_autobuild
            # 定时任务负责，热路径不再针对单条消息触发 LLM 抽取
            try:
                style = await group_profile.get_style(ctx.group_id)
                style_prompt = ProfileToolkit.build_group_style_prompt_block(style)
                if style_prompt:
                    parts.append(style_prompt)
            except Exception as e:
                logger.debug(
                    f"注入群风格失败: {e}", command="AI", e=e
                )

            # 话题线程追踪：记录用户消息并注入当前话题上下文
            if get_config("THREAD_TRACKER_ENABLED", True):
                thread_tracker.track_message(
                    group_id=ctx.group_id,
                    user_id=ctx.user_id,
                    text=ctx.text,
                )
                thread_ctx = thread_tracker.get_thread_context(
                    ctx.group_id
                )
                if thread_ctx:
                    parts.append(
                        f"\n{thread_ctx}\n"
                    )

            # 注入群社交上下文（角色/关系/复读跟随提示）
            if get_config("SOCIAL_INTELLIGENCE_ENABLED", True):
                social_prompt = (
                    group_social.build_social_prompt_block(
                        ctx.group_id, ctx.user_id
                    )
                )
                if social_prompt:
                    parts.append(social_prompt)

        if get_config("SAFETY_FILTER_ENABLED", True):
            parts.append(SafetyFilter.build_prompt_injection_guard())

        # 注入回复风格策略：防止堆砌网络热词/模板化口癖
        parts.append(
            "## 人设与输出风格（高优先级）\n"
            "- 你是当前人设本人，不是图片讲解员、资料解释器或互联网梗百科。\n"
            "- 不要堆砌互联网热词、圈子黑话、流行梗或模板化口癖；理解即可，"
            "最终按人设和当前关系自然说话。\n"
            "- 不要把「这波/绷不住/难绷/典/抽象/赢麻了/笑死/破防/太真实了」"
            "等网络套话当作万能反应；用户说了也只当作情绪线索，"
            "输出要换成人设会说的普通短句。\n"
            "- 不要为了显得懂梗而解释笑点；除非对方明确要求解释，"
            "正常聊天优先短句接话。\n"
            "- 避免把「等下/等一下/你这也/这图也/啊这/不是」等当作习惯性开头；"
            "确实需要停顿时也只偶尔使用，更多时候直接接话。\n"
            "- 不要频繁用「。。。/……/...」拖长停顿或凑语气；"
            "一句话能自然说完就直接说完。"
        )
        has_visual = ctx.image_data is not None
        if has_visual:
            parts.append(
                "\n- 图片、表情包、截图的视觉信息只是内部上下文，"
                "不能把视觉摘要复述给用户。"
                "\n- 表情包、梗图和截图只当作语气线索；"
                "除非对方明确让你识别、翻译或解读，"
                "不要主动讲图里是什么。"
            )
            parts.append(
                "\n\n## 图片处理规则（重要）\n"
                "1. 你正在接收图片输入，但仍然保持自己的人设和当前聊天关系。\n"
                "2. 禁止代入、扮演图片中的人物或角色。\n"
                "3. 图片内容只用于理解当前语境；没有被明确要求时，"
                "不要主动讲解、复述或分析画面。\n"
                "4. 如果需要回应，像聊天对象看见这条消息后的自然反应，"
                "不要写成图像识别报告。"
            )

        # 注入环境感知提示词（提醒AI不要将其他插件/其他bot功能说成自己能力）
        if get_config("PEER_AWARENESS_ENABLED", True):
            parts.append(peer_awareness.build_peer_awareness_prompt())

        if (
            ctx.group_id
            and get_config("FRAGMENT", {}).get("style", "prompt") == "prompt"
        ):
            parts.append(HumanizeToolkit.build_group_chat_style_prompt())

        anti_loop = ContextPolicy.build_anti_loop_hint(history)
        if anti_loop:
            parts.append(anti_loop)

        return "".join(parts)
