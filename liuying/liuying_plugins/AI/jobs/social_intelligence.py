"""社交智能定时任务

早晚问候、节日问候、新闻推送、话题延续。
基于context_manager时段判断 + llm_helper生成文案。
集成社交门控（gate）与配额（quota），避免过度打扰。
"""

from datetime import datetime
import json
import random
from typing import Any

from nonebot import get_bot
from nonebot_plugin_alconna import Target

from liuying.models._user.user_info import UserInfo
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from ..agent.intent.group_style import ProfileToolkit
from ..agent.review.social_gate import social_gate
from ..config import get_config
from ..core.context import context_manager
from ..core.llm import llm_helper
from ..core.llm.model_router import ROLE_WARMUP, model_router
from ..core.persona import persona_manager
from ..core.runtime import ProtocolHelper
from ..core.social import social_quota
from ..core.social.framework import (
    SocialContext,
    SocialTrigger,
    social_trigger_registry,
)
from ..models.group_context import GroupContextSnapshot

__all__ = [
    "register_social_triggers",
    "setup_social_intelligence_jobs",
]

_PROACTIVE_POKE_FAVOR_THRESHOLD = 5
"""主动拍一拍触发的好感度阈值"""

_PROACTIVE_POKE_DAILY_LIMIT = 3
"""主动拍一拍每日上限"""

_TEXT_LENGTH_LIMIT = 100
"""社交文案长度上限（字符）"""


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

    封装早晚问候、节日问候、新闻推送、话题延续等任务逻辑。
    """

    @staticmethod
    def _parse_group_style(style_raw: str | None) -> str:
        """解析群风格为prompt文本

        style 字段为 profile.py 与 autobuild 统一写入的 JSON 对象
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
    def _truncate_text(text: str, limit: int = _TEXT_LENGTH_LIMIT) -> str:
        """文案超长时截断并追加省略号

        参数:
            text: 原始文案
            limit: 长度上限（字符）

        返回:
            str: 未超长返回原文，超长返回前limit字加省略号
        """
        if len(text) <= limit:
            return text
        logger.debug(
            f"社交文案超长({len(text)}字)，截断到{limit}字后发送",
            command="AI",
        )
        return text[:limit] + "…"

    @staticmethod
    async def _generate_and_send_to_groups(
        build_prompt: Any,
        *,
        scenario: str,
        generate_once: bool = False,
    ) -> int:
        """生成文案并发送到所有活跃群

        集成社交配额与门控检查：
        - 配额检查：每群每日上限 + 单场景冷却
        - 门控检查：LLM二次判断是否适合发送

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
        daily_quota = get_config("SOCIAL_QUOTA", {}).get("per_user", 5)
        cooldown = get_config("SOCIAL_QUOTA", {}).get("cooldown", 3600)
        gate_enabled = get_config("SOCIAL_GATE_ENABLED", False)
        # 深夜静默配置与群无关，提取到循环外只读一次
        quiet_start = get_config("GROUP_QUIET", {}).get("start", 0)
        quiet_end = get_config("GROUP_QUIET", {}).get("end", 7)

        shared_text: str | None = None
        if generate_once:
            prompt = await build_prompt(None, time_period)
            if not prompt:
                return 0
            shared_text = await llm_helper.chat_text(
                [{"role": "user", "content": prompt}],
                options=model_router.resolve(
                    ROLE_WARMUP
                ).apply_to_options(),
            )
            if not shared_text:
                return 0
            shared_text = (
                SocialIntelligenceHelper._truncate_text(shared_text)
            )

        sent = 0
        for group in groups:
            if not context_manager.is_group_active_hour(
                group.group_id,
                quiet_start=quiet_start,
                quiet_end=quiet_end,
            ):
                continue

            # 配额检查：每群每日上限 + 单场景冷却
            if social_quota.is_quota_exceeded(
                group.group_id,
                scenario=scenario,
                daily_quota_per_user=daily_quota,
                cooldown_seconds=cooldown,
            ):
                logger.debug(
                    f"群 {group.group_id} 场景 {scenario} "
                    f"配额已满或冷却中，跳过",
                    command="AI",
                )
                continue

            try:
                if shared_text is not None:
                    text = shared_text
                else:
                    prompt = await build_prompt(group, time_period)
                    if not prompt:
                        continue
                    text = await llm_helper.chat_text(
                        [{"role": "user", "content": prompt}],
                        options=model_router.resolve(
                            ROLE_WARMUP
                        ).apply_to_options(),
                    )
                    if not text:
                        continue
                    text = (
                        SocialIntelligenceHelper._truncate_text(text)
                    )

                # 社交门控：LLM二次判断是否适合发送
                if gate_enabled:
                    allow, rewritten, reason = (
                        await social_gate.gate_should_send(
                            scenario=scenario,
                            user_id=group.group_id,
                            draft=text,
                            now_str=datetime.now().strftime(
                                "%Y-%m-%d %H:%M"
                            ),
                        )
                    )
                    if not allow:
                        logger.debug(
                            f"社交门控拒绝发送 {group.group_id}: "
                            f"{reason}",
                            command="AI",
                        )
                        continue
                    if rewritten:
                        text = rewritten

                await SocialIntelligenceHelper._send_to_group(
                    group.group_id, text
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
    async def _proactive_poke() -> None:
        """主动拍一拍高好感度用户

        随机选一个高好感度用户戳一下，作为亲昵互动。
        深夜静默时段跳过，受配额限制避免过度打扰。
        """
        if not get_config("POKE", {}).get("proactive_enabled", False):
            return
        if context_manager.is_rest_time():
            return

        # 仅需user_id单列，避免整行ORM拉取
        user_ids = await UserInfo.filter(
            favor_value__gte=_PROACTIVE_POKE_FAVOR_THRESHOLD
        ).values_list("user_id", flat=True)
        if not user_ids:
            return

        daily_limit = get_config(
            "PROACTIVE_POKE_DAILY_LIMIT",
            _PROACTIVE_POKE_DAILY_LIMIT,
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


def _make_handler(func: Any) -> Any:
    """包装SocialIntelligenceHelper方法为接收SocialContext的handler

    SocialTrigger.handler签名要求接收SocialContext，
    但社交智能任务内部自行遍历所有群，不使用ctx。

    参数:
        func: SocialIntelligenceHelper的无参数async方法

    返回:
        接收SocialContext的async handler
    """

    async def _handler(_ctx: SocialContext) -> None:
        await func()

    return _handler


def register_social_triggers() -> None:
    """注册社交智能触发器到SocialTrigger框架

    把早安/晚安/新闻/话题延续4个任务注册为SocialTrigger，
    由social_trigger_registry.setup_to_scheduler统一调度。
    """

    def _social_enabled(_cfg: Any) -> bool:
        return get_config("SOCIAL_INTELLIGENCE_ENABLED", True)

    def _poke_enabled(_cfg: Any) -> bool:
        return get_config("POKE", {}).get("proactive_enabled", False)

    social_trigger_registry.register(
        SocialTrigger(
            name="morning_greeting",
            handler=_make_handler(
                SocialIntelligenceHelper._morning_greeting
            ),
            schedule_kind="cron",
            schedule_args={"hour": 8, "minute": 0},
            enabled=_social_enabled,
        )
    )
    social_trigger_registry.register(
        SocialTrigger(
            name="evening_greeting",
            handler=_make_handler(
                SocialIntelligenceHelper._evening_greeting
            ),
            schedule_kind="cron",
            schedule_args={"hour": 22, "minute": 30},
            enabled=_social_enabled,
        )
    )
    social_trigger_registry.register(
        SocialTrigger(
            name="news_push",
            handler=_make_handler(
                SocialIntelligenceHelper._news_push
            ),
            schedule_kind="interval",
            schedule_args={"hours": 4},
            enabled=_social_enabled,
        )
    )
    social_trigger_registry.register(
        SocialTrigger(
            name="topic_followup",
            handler=_make_handler(
                SocialIntelligenceHelper._topic_followup
            ),
            schedule_kind="interval",
            schedule_args={"hours": 2},
            enabled=_social_enabled,
        )
    )
    social_trigger_registry.register(
        SocialTrigger(
            name="proactive_poke",
            handler=_make_handler(
                SocialIntelligenceHelper._proactive_poke
            ),
            schedule_kind="interval",
            schedule_args={"hours": 6},
            enabled=_poke_enabled,
        )
    )


async def setup_social_intelligence_jobs() -> None:
    """注册社交智能定时任务

    通过SocialTrigger框架注册触发器并统一调度。
    """
    if not get_config("SOCIAL_INTELLIGENCE_ENABLED", True):
        logger.info(
            "社交智能功能已禁用，跳过任务注册",
            command="AI",
        )
        return

    register_social_triggers()
    count = await social_trigger_registry.setup_to_scheduler()

    logger.info(
        f"社交智能任务已注册 {count} 个触发器"
        "（早安8:00/晚安22:30/新闻4h/话题2h/主动拍6h）",
        command="AI",
    )
