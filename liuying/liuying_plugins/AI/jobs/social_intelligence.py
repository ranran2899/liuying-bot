"""社交智能定时任务

主动社交场景的统一入口：早晚问候、节日问候、新闻推送、话题延续、
主动拍一拍、群空闲发话与私聊问候（后三者由 jobs/proactive 合并而来）。
基于SocialTrigger框架声明式注册，集成社交门控（gate）与配额（quota），
所有群发/私聊文案统一经过安全模板过滤与Markdown规范化，避免过度打扰。
"""

from datetime import datetime, timedelta
import json
import random
from typing import Any

from nonebot import get_bot
from nonebot_plugin_alconna import Target

from liuying.models._user.user_info import UserInfo
from liuying.services.liuying_db import Q
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from ..agent.review.social_gate import social_gate
from ..config import get_config
from ..core.context import context_manager
from ..core.group.profile import ProfileToolkit
from ..core.llm import llm_helper
from ..core.llm.model_router import ROLE_WARMUP, model_router
from ..core.persona import persona_manager
from ..core.runtime import ProtocolHelper
from ..core.safety import SafetyFilter
from ..core.social import social_quota
from ..core.social.framework import (
    ScheduleKind,
    SocialTrigger,
    social_trigger_registry,
)
from ..core.tools.json_utils import extract_json_payload
from ..models.conversation_record import ConversationRecord
from ..models.group_context import GroupContextSnapshot
from ..pipeline.text_policy import ReplyTextPolicy

__all__ = [
    "register_social_triggers",
    "setup_social_intelligence_jobs",
]

_PROACTIVE_POKE_FAVOR_THRESHOLD = 5
"""主动拍一拍触发的好感度阈值"""

_TEXT_LENGTH_LIMIT = 100
"""社交文案长度上限（字符）"""

_PRIVATE_GREET_FAVOR_THRESHOLD = 5
"""私聊问候触发的好感度阈值（亲密及以上）"""

_SCENARIO_GROUP_CHAT = "群空闲发话"
"""群空闲发话场景标记"""

_SCENARIO_PRIVATE_GREET = "私聊问候"
"""私聊问候场景标记"""

_FESTIVAL_MAP: dict[str, str] = {
    "01-01": "元旦",
    "02-14": "情人节",
    "03-08": "妇女节",
    "05-01": "劳动节",
    "05-04": "青年节",
    "06-01": "儿童节",
    "10-01": "国庆节",
    "12-25": "圣诞节",
}
"""固定日期节日映射"""


class SocialIntelligenceHelper:
    """社交智能辅助工具类

    封装问候、新闻、话题延续、群空闲发话、私聊问候、
    主动拍一拍等主动社交场景的任务逻辑。
    """

    # ---------- 通用出口：过滤/规范/门控/配额 ----------

    @staticmethod
    def _parse_group_style(style_raw: str | None) -> str:
        """解析群风格为prompt文本

        style 字段为 group_style_autobuild 写入的 JSON 对象
        （键名: tone/pace/catchphrases/taboos/typical_length），
        解析失败或非 dict 时视为未设置。

        参数:
            style_raw: 群风格JSON字符串

        返回:
            str: prompt文本，空串表示未设置
        """
        if not style_raw or not style_raw.strip():
            return ""
        try:
            data = json.loads(style_raw)
            if isinstance(data, dict):
                return ProfileToolkit.build_group_style_prompt_block(data)
        except (json.JSONDecodeError, TypeError):
            pass
        return ""

    @staticmethod
    def _sanitize_text(text: str) -> str:
        """主动消息统一文本出口

        Markdown规范化 + 超长截断 + 拒绝模板过滤，
        命中不可发送情形返回空串。

        参数:
            text: 原始文案

        返回:
            str: 可发送文本，空串表示放弃发送
        """
        cleaned = ReplyTextPolicy.normalize_visible_reply_text(text)
        if not cleaned:
            return ""
        if len(cleaned) > _TEXT_LENGTH_LIMIT:
            logger.debug(
                f"社交文案超长({len(cleaned)}字)，截断到"
                f"{_TEXT_LENGTH_LIMIT}字后发送",
                command="AI",
            )
            cleaned = cleaned[:_TEXT_LENGTH_LIMIT] + "…"
        if SafetyFilter.detect_refusal(cleaned):
            logger.debug(
                "社交文案命中拒绝模板，放弃发送", command="AI"
            )
            return ""
        return cleaned

    @staticmethod
    async def _apply_gate(
        scenario: str, target_id: str, text: str
    ) -> str | None:
        """社交门控：LLM二次判断是否适合发送

        门控关闭时直接放行；拒绝时返回None；
        允许但改写时返回改写文案。

        参数:
            scenario: 场景标记
            target_id: 目标群/用户ID
            text: 待发送文案

        返回:
            str | None: 最终文案，None表示不发送
        """
        if not get_config("SOCIAL_GATE_ENABLED", False):
            return text
        allow, rewritten, reason = await social_gate.gate_should_send(
            scenario=scenario,
            user_id=target_id,
            draft=text,
            now_str=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        if not allow:
            logger.debug(
                f"社交门控拒绝发送 {target_id}: {reason}",
                command="AI",
            )
            return None
        return rewritten or text

    @staticmethod
    def _quota_and_quiet(
        group_id: str,
        scenario: str,
        quiet_start: int,
        quiet_end: int,
    ) -> bool:
        """群发送前的统一准入检查：静默时段 + 配额

        参数:
            group_id: 群组ID
            scenario: 场景标记
            quiet_start: 深夜静默开始小时
            quiet_end: 深夜静默结束小时

        返回:
            bool: 是否允许发送
        """
        if not context_manager.is_group_active_hour(
            group_id, quiet_start=quiet_start, quiet_end=quiet_end
        ):
            return False
        quota_cfg = get_config("SOCIAL_QUOTA", {})
        return not social_quota.is_quota_exceeded(
            group_id,
            scenario=scenario,
            daily_quota_per_user=quota_cfg.get("per_user", 5),
            cooldown_seconds=quota_cfg.get("cooldown", 3600),
        )

    # ---------- 群级场景 ----------

    @staticmethod
    async def _generate_and_send_to_groups(
        build_prompt: Any,
        *,
        scenario: str,
        generate_once: bool = False,
    ) -> int:
        """生成文案并发送到所有活跃群

        统一经过安全过滤、门控与配额检查。
        群主动发言不写入 ConversationRecord：对话历史按
        (user_id, group_id) 维度存储，群发内容归属任意单个
        用户都会污染其私有历史，群级语境由群摘要任务承载。

        参数:
            build_prompt: 接收(group, time_period)返回prompt的函数，
                generate_once=True 时 group 传 None 只调用一次
            scenario: 场景标记
            generate_once: prompt不依赖群时只生成一次文案，
                所有群复用，避免重复LLM调用

        返回:
            int: 发送成功的群数
        """
        if not get_config("SOCIAL_INTELLIGENCE_ENABLED", True):
            return 0
        groups = await GroupContextSnapshot.filter(
            is_active=True
        ).all()
        if not groups:
            return 0

        time_period = context_manager.get_current_time_period()
        quiet_start = get_config("GROUP_QUIET", {}).get("start", 0)
        quiet_end = get_config("GROUP_QUIET", {}).get("end", 7)

        shared_text: str | None = None
        if generate_once:
            prompt = await build_prompt(None, time_period)
            if not prompt:
                return 0
            shared_text = await SocialIntelligenceHelper._generate_text(prompt)
            if not shared_text:
                return 0

        sent = 0
        for group in groups:
            if not SocialIntelligenceHelper._quota_and_quiet(
                group.group_id, scenario, quiet_start, quiet_end
            ):
                continue

            try:
                if shared_text is not None:
                    text = shared_text
                else:
                    prompt = await build_prompt(group, time_period)
                    if not prompt:
                        continue
                    text = await SocialIntelligenceHelper._generate_text(prompt)
                    if not text:
                        continue

                final_text = await SocialIntelligenceHelper._apply_gate(
                    scenario, group.group_id, text
                )
                if not final_text:
                    continue

                await SocialIntelligenceHelper._send_to_group(
                    group.group_id, final_text
                )
                social_quota.mark_sent(
                    group.group_id, scenario=scenario
                )
                sent += 1
            except Exception as e:
                logger.debug(
                    f"社交智能{scenario}发送失败 {group.group_id}: {e}",
                    command="AI",
                    e=e,
                )

        logger.info(
            f"社交智能{scenario}任务完成，发送{sent}个群",
            command="AI",
        )
        return sent

    @staticmethod
    async def _generate_text(prompt: str) -> str:
        """按预热角色生成并净化文案

        参数:
            prompt: 生成提示词

        返回:
            str: 可发送文案，失败/不可发送返回空串
        """
        role = model_router.resolve(ROLE_WARMUP)
        raw = await llm_helper.chat_text(
            [{"role": "user", "content": prompt}],
            model=role.model or None,
            options=role.apply_to_options(),
            provider_name=role.provider or None,
        )
        return SocialIntelligenceHelper._sanitize_text(raw)

    @staticmethod
    async def _send_to_group(
        group_id: str, text: str
    ) -> None:
        """发送消息到群

        使用MessageUtils.build_message跨适配器发送。

        参数:
            group_id: 群组ID
            text: 消息文本
        """
        try:
            bot = get_bot()
            target = Target(id=str(group_id), private=False)
            await MessageUtils.build_message(text).send(
                target=target, bot=bot
            )
        except Exception as e:
            logger.debug(
                f"发送群消息失败 {group_id}: {e}",
                command="AI",
            )

    @staticmethod
    def _get_festival() -> str:
        """获取今日节日

        返回:
            str: 节日名称，无则返回空串
        """
        now = datetime.now()
        key = f"{now.month:02d}-{now.day:02d}"
        return _FESTIVAL_MAP.get(key, "")

    @staticmethod
    async def _greeting(
        scenario: str,
        with_festival: bool,
    ) -> None:
        """早晚安问候任务

        参数:
            scenario: 场景标记（早安问候/晚安问候）
            with_festival: 是否注入当日节日信息
        """
        festival_line = ""
        if with_festival:
            festival = SocialIntelligenceHelper._get_festival()
            festival_line = (
                f"今日节日: {festival}\n" if festival else ""
            )
        persona_name = (
            persona_manager.get_default_persona().get("name") or "AI"
        )

        async def _build_prompt(
            group: GroupContextSnapshot, time_period: str
        ) -> str:
            group_style_str = (
                SocialIntelligenceHelper._parse_group_style(
                    group.style
                )
                or "群风格: 未设置"
            )
            return (
                f"你是{persona_name}，请生成一句自然的"
                f"{scenario.replace('问候', '')}问候语。\n\n"
                f"当前时段: {time_period}\n"
                f"{festival_line}{group_style_str}\n\n"
                "要求：\n"
                "- 简短自然，不超过30字\n"
                f"- 符合{persona_name}的性格和当前时段氛围\n"
                "- 不要使用模板化用语\n\n"
                "直接输出问候语，不要解释。"
            )

        await SocialIntelligenceHelper._generate_and_send_to_groups(
            _build_prompt, scenario=scenario
        )

    @staticmethod
    async def _morning_greeting() -> None:
        """早安问候任务"""
        await SocialIntelligenceHelper._greeting(
            "早安问候", with_festival=True
        )

    @staticmethod
    async def _evening_greeting() -> None:
        """晚安问候任务"""
        await SocialIntelligenceHelper._greeting(
            "晚安问候", with_festival=False
        )

    @staticmethod
    async def _news_push() -> None:
        """新闻/话题推送任务"""

        async def _build_prompt(
            _group: GroupContextSnapshot | None, time_period: str
        ) -> str:
            return (
                "请生成一条适合在群聊分享的轻松话题或新闻摘要。\n\n"
                f"当前时段: {time_period}\n\n"
                "要求：\n"
                "- 简短有趣，不超过40字\n"
                "- 适合群聊氛围\n"
                "- 可以是科技/游戏/生活类话题\n\n"
                "直接输出内容，不要解释。"
            )

        # prompt不依赖群，只生成一次文案复用给所有群
        await SocialIntelligenceHelper._generate_and_send_to_groups(
            _build_prompt, scenario="新闻推送", generate_once=True
        )

    @staticmethod
    async def _topic_followup() -> None:
        """话题延续任务

        复用 _generate_and_send_to_groups 的配额/门控/静默时段检查。
        """

        async def _build_prompt(
            group: GroupContextSnapshot, _time_period: str
        ) -> str:
            summary = group.summary or ""
            if not summary:
                return ""
            return (
                "基于最近的群聊摘要，生成一句自然的延续话题。\n\n"
                f"群聊摘要: {summary[:200]}\n\n"
                "要求：\n"
                "- 简短自然，不超过30字\n"
                "- 像真人继续之前的聊天\n\n"
                "直接输出内容，不要解释。"
            )

        await SocialIntelligenceHelper._generate_and_send_to_groups(
            _build_prompt, scenario="话题延续"
        )

    # ---------- 群空闲发话（原 proactive 场景） ----------

    @staticmethod
    async def _decide_proactive_message(
        group_id: str,
        group_style: str,
        last_active: datetime | None,
    ) -> tuple[bool, str]:
        """让LLM决策是否主动发话及发什么

        参数:
            group_id: 群组ID
            group_style: 群风格JSON原文
            last_active: 最近活跃时间

        返回:
            tuple[bool, str]: (是否发送, 消息内容)
        """
        period = context_manager.get_current_time_period()
        time_flavor = context_manager.get_time_flavor_prompt()
        last_active_str = (
            last_active.strftime("%Y-%m-%d %H:%M")
            if last_active
            else "未知"
        )

        persona = persona_manager.get_default_persona()
        persona_name = persona.get("name") or "AI"
        interests_list = persona.get("interests") or []
        topics_list = persona.get("proactive_topics") or []
        if not isinstance(interests_list, list):
            interests_list = []
        if not isinstance(topics_list, list):
            topics_list = []
        interests_str = (
            "、".join(str(i) for i in interests_list)
            if interests_list
            else "未指定"
        )
        topics_str = (
            "、".join(str(t) for t in topics_list)
            if topics_list
            else "无"
        )
        style_line = SocialIntelligenceHelper._parse_group_style(
            group_style
        ) or "群风格: 未设置"
        prompt = (
            f"现在群里安静了一段时间，作为{persona_name}，"
            "决定是否要主动说点什么。\n\n"
            f"当前时段: {period}\n"
            f"时段氛围: {time_flavor}\n"
            f"{style_line}\n"
            f"最近活跃时间: {last_active_str}\n"
            f"兴趣领域: {interests_str}\n"
            f"建议话题: {topics_str}\n\n"
            "请用JSON格式返回决策:\n"
            "- should_send: 是否发送消息（true/false）\n"
            "- message: 要发送的消息内容（should_send为true时填写，不超过50字）\n"
            "- reason: 决策理由\n\n"
            "只返回JSON，不要其他内容。"
        )

        role = model_router.resolve(ROLE_WARMUP)
        response = await llm_helper.chat_text(
            [{"role": "user", "content": prompt}],
            model=role.model or None,
            options=role.apply_to_options(),
            provider_name=role.provider or None,
        )
        data = extract_json_payload(response)
        if data is None:
            return False, ""
        return bool(data.get("should_send", False)), str(
            data.get("message", "")
        )

    @staticmethod
    async def _idle_group_chat() -> None:
        """群空闲发话任务（合并自原 proactive 场景）

        遍历长时间无活动的群，LLM决策后走统一准入/门控/发送出口。
        """
        if not get_config("PROACTIVE", {}).get("enabled", True):
            return
        if context_manager.is_rest_time():
            return
        proactive_cfg = get_config("PROACTIVE", {})
        idle_threshold = datetime.now() - timedelta(
            minutes=proactive_cfg.get("group_idle_minutes", 90)
        )
        daily_limit = int(proactive_cfg.get("daily_limit", 3))
        quiet_start = get_config("GROUP_QUIET", {}).get("start", 0)
        quiet_end = get_config("GROUP_QUIET", {}).get("end", 7)

        groups = await GroupContextSnapshot.filter(
            Q(last_activity_time__lte=idle_threshold)
            | Q(last_activity_time__isnull=True),
            is_active=True,
        ).values_list("group_id", "style", "last_activity_time")
        if not groups:
            return

        # 随机化遍历顺序，避免列表头部群长期占用每日配额
        random.shuffle(groups)
        sent = 0
        for group_id, style, last_active in groups:
            if sent >= daily_limit:
                break
            if not SocialIntelligenceHelper._quota_and_quiet(
                str(group_id), _SCENARIO_GROUP_CHAT, quiet_start, quiet_end
            ):
                continue
            try:
                should_send, message = (
                    await SocialIntelligenceHelper._decide_proactive_message(
                        str(group_id), style or "", last_active
                    )
                )
                if not (should_send and message):
                    continue
                text = SocialIntelligenceHelper._sanitize_text(message)
                if not text:
                    continue
                final_text = await SocialIntelligenceHelper._apply_gate(
                    _SCENARIO_GROUP_CHAT, str(group_id), text
                )
                if not final_text:
                    continue
                await SocialIntelligenceHelper._send_to_group(
                    str(group_id), final_text
                )
                social_quota.mark_sent(
                    str(group_id), scenario=_SCENARIO_GROUP_CHAT
                )
                await context_manager.update_group_activity(str(group_id))
                sent += 1
                logger.info(
                    f"群主动发话: {group_id} -> {final_text[:30]}",
                    command="AI",
                )
            except Exception as e:
                logger.debug(
                    f"群主动发话失败 {group_id}: {e}",
                    command="AI",
                    e=e,
                )

    # ---------- 私聊场景 ----------

    @staticmethod
    async def _private_greeting() -> None:
        """私聊问候任务（合并自原 proactive 场景）

        每天8点和22点向高好感度用户发送早晚安问候，
        每次执行受 PROACTIVE.daily_limit 限制，
        问候内容写入对应用户的对话历史供后续对话引用。
        """
        if not get_config("PROACTIVE", {}).get("enabled", True):
            return
        hour = datetime.now().hour
        greeting_type = "早安" if hour < 12 else "晚安"
        proactive_cfg = get_config("PROACTIVE", {})
        daily_limit = int(proactive_cfg.get("daily_limit", 3))

        user_ids = await UserInfo.filter(
            favor_value__gte=_PRIVATE_GREET_FAVOR_THRESHOLD
        ).values_list("user_id", flat=True)
        if not user_ids:
            return

        sent_count = 0
        for user_id in user_ids:
            if sent_count >= daily_limit:
                break
            if not user_id or social_quota.is_quota_exceeded(
                user_id,
                scenario=_SCENARIO_PRIVATE_GREET,
                daily_quota_per_user=daily_limit,
                cooldown_seconds=6 * 3600,
            ):
                continue
            try:
                message = (
                    await SocialIntelligenceHelper._generate_greeting(
                        greeting_type, user_id
                    )
                )
                if not message:
                    continue
                await SocialIntelligenceHelper._send_private_greeting(
                    user_id, message
                )
                social_quota.mark_sent(
                    user_id, scenario=_SCENARIO_PRIVATE_GREET
                )
                sent_count += 1
            except Exception as e:
                logger.debug(
                    f"私聊问候失败 {user_id}: {e}",
                    command="AI",
                    e=e,
                )

        if sent_count > 0:
            logger.info(
                f"私聊问候任务完成: {greeting_type}，"
                f"已发送 {sent_count} 条",
                command="AI",
            )

    @staticmethod
    async def _generate_greeting(
        greeting_type: str,
        user_id: str,
    ) -> str:
        """生成私聊问候消息并按用户激活人格口吻净化

        参数:
            greeting_type: 问候类型（早安/晚安）
            user_id: 目标用户ID，用于按用户切换的人格口吻生成

        返回:
            str: 问候消息，失败返回空串
        """
        persona_name = await persona_manager.get_user_persona_name(
            user_id
        )
        prompt = (
            f"请以{persona_name}的口吻为一位高好感度好友"
            f"发送一条{greeting_type}问候。\n\n"
            "要求：\n"
            "1. 自然亲切，符合好友关系\n"
            "2. 不超过30字\n"
            "3. 不要使用称呼，直接说问候内容\n\n"
            "只返回问候文本，不要其他内容。"
        )
        return await SocialIntelligenceHelper._generate_text(prompt)

    @staticmethod
    async def _send_private_greeting(
        user_id: str, message: str
    ) -> None:
        """发送私聊问候并写入用户对话历史

        参数:
            user_id: 用户ID
            message: 消息内容
        """
        target = Target(user_id, private=True)
        await MessageUtils.build_message(message).send(target=target)
        persona_name = await persona_manager.get_user_persona_name(
            user_id
        )
        await ConversationRecord.create(
            user_id=user_id,
            role="assistant",
            content=message,
            group_id=None,
            persona_name=persona_name,
        )
        logger.info(
            f"私聊问候已发送: {user_id} -> {message[:20]}",
            command="AI",
        )

    # ---------- 主动拍一拍 ----------

    @staticmethod
    async def _proactive_poke() -> None:
        """主动拍一拍高好感度用户

        随机选高好感度用户戳一下，作为亲昵互动。
        深夜静默时段跳过，受配额限制避免过度打扰。
        """
        if not get_config("POKE", {}).get("proactive_enabled", False):
            return
        if context_manager.is_rest_time():
            return

        user_ids = await UserInfo.filter(
            favor_value__gte=_PROACTIVE_POKE_FAVOR_THRESHOLD
        ).values_list("user_id", flat=True)
        if not user_ids:
            return

        daily_limit = get_config(
            "PROACTIVE_POKE_DAILY_LIMIT", 3
        )
        # 直接抽样所需数量，避免对全量列表 shuffle 的浪费
        candidates = random.sample(
            user_ids, min(daily_limit, len(user_ids))
        )
        poked = 0
        for user_id in candidates:
            if poked >= daily_limit:
                break
            if not user_id:
                continue
            if social_quota.is_quota_exceeded(
                user_id,
                scenario="主动拍一拍",
                daily_quota_per_user=daily_limit,
                cooldown_seconds=3600,
            ):
                continue
            try:
                bot = get_bot()
                ok = await ProtocolHelper.poke(
                    bot, user_id=user_id
                )
                if ok:
                    social_quota.mark_sent(
                        user_id, scenario="主动拍一拍"
                    )
                    poked += 1
                    logger.info(
                        f"主动拍一拍: {user_id}",
                        command="AI",
                    )
            except Exception as e:
                logger.debug(
                    f"主动拍一拍失败 {user_id}: {e}",
                    command="AI",
                    e=e,
                )


def register_social_triggers() -> None:
    """按各自开关注册全部主动社交触发器

    启用判断在注册时一次完成：社交场景受
    SOCIAL_INTELLIGENCE_ENABLED 控制，空闲发话/私聊问候受
    PROACTIVE.enabled 控制，拍一拍受 POKE.proactive_enabled 控制。
    """
    social_on = get_config("SOCIAL_INTELLIGENCE_ENABLED", True)
    proactive_cfg = get_config("PROACTIVE", {})
    proactive_on = bool(proactive_cfg.get("enabled", True))
    poke_on = bool(get_config("POKE", {}).get("proactive_enabled", False))

    helper = SocialIntelligenceHelper
    specs: list[tuple[str, Any, ScheduleKind, dict[str, Any], bool]] = [
        (
            "morning_greeting",
            helper._morning_greeting,
            ScheduleKind.CRON,
            {"hour": 8, "minute": 0},
            social_on,
        ),
        (
            "evening_greeting",
            helper._evening_greeting,
            ScheduleKind.CRON,
            {"hour": 22, "minute": 30},
            social_on,
        ),
        (
            "news_push",
            helper._news_push,
            ScheduleKind.INTERVAL,
            {"hours": 4},
            social_on,
        ),
        (
            "topic_followup",
            helper._topic_followup,
            ScheduleKind.INTERVAL,
            {"hours": 2},
            social_on,
        ),
        (
            "proactive_poke",
            helper._proactive_poke,
            ScheduleKind.INTERVAL,
            {"hours": 6},
            poke_on,
        ),
        (
            "idle_group_chat",
            helper._idle_group_chat,
            ScheduleKind.INTERVAL,
            {"minutes": int(proactive_cfg.get("interval_minutes", 30))},
            proactive_on,
        ),
        (
            "private_greeting",
            helper._private_greeting,
            ScheduleKind.CRON,
            {"hour": "8,22", "minute": 0},
            proactive_on,
        ),
    ]
    for name, handler, kind, args, enabled in specs:
        if not enabled:
            continue
        social_trigger_registry.register(
            SocialTrigger(
                name=name,
                handler=handler,
                schedule_kind=kind,
                schedule_args=args,
            )
        )


async def setup_social_intelligence_jobs() -> None:
    """注册社交智能定时任务

    先清空注册表再按开关注册触发器，统一挂到调度器。
    """
    social_trigger_registry.clear()
    register_social_triggers()
    count = await social_trigger_registry.setup_to_scheduler()

    logger.info(
        f"社交智能任务已注册 {count} 个触发器"
        "（问候/新闻/话题/拍一拍/空闲发话/私聊问候）",
        command="AI",
    )
