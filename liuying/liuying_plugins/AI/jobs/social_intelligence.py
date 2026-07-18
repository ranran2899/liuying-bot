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

from ..config import get_config
from ..core.context import context_manager
from ..core.group import ProfileToolkit
from ..core.llm import llm_helper
from ..core.persona import persona_manager
from ..core.runtime import ProtocolHelper
from ..core.social import social_gate, social_quota
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
    def _parse_group_style(
        style_json: str | None
    ) -> dict[str, Any]:
        """解析群风格JSON

        参数:
            style_json: 群风格JSON字符串

        返回:
            dict: 群风格字典
        """
        if not style_json:
            return {}
        try:
            result = json.loads(style_json)
            return result if isinstance(result, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @staticmethod
    async def _generate_and_send_to_groups(
        build_prompt: Any,
        *,
        scenario: str,
    ) -> int:
        """生成文案并发送到所有活跃群

        集成社交配额与门控检查：
        - 配额检查：每群每日上限 + 单场景冷却
        - 门控检查：LLM二次判断是否适合发送

        参数:
            build_prompt: 接收(group, time_period)返回prompt的函数
            scenario: 场景标记

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
        daily_quota = get_config("SOCIAL_QUOTA_PER_USER", 5)
        cooldown = get_config("SOCIAL_QUOTA_COOLDOWN", 3600)
        gate_enabled = get_config("SOCIAL_GATE_ENABLED", False)
        sent = 0
        for group in groups:
            if not context_manager.is_group_active_hour(
                group.group_id,
                quiet_start=get_config("GROUP_QUIET_START", 0),
                quiet_end=get_config("GROUP_QUIET_END", 7),
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
                prompt = await build_prompt(group, time_period)
                if not prompt:
                    continue
                text = await llm_helper.chat_text(
                    [{"role": "user", "content": prompt}],
                    options={"temperature": 0.7},
                )
                if not text or len(text) >= 100:
                    continue

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
                e=e,
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
        if not get_config("PROACTIVE_POKE_ENABLED", False):
            return
        if context_manager.is_rest_time():
            return

        users = await UserInfo.filter(
            favor_value__gte=_PROACTIVE_POKE_FAVOR_THRESHOLD
        ).all()
        if not users:
            return

        daily_limit = get_config(
            "PROACTIVE_POKE_DAILY_LIMIT",
            _PROACTIVE_POKE_DAILY_LIMIT,
        )
        # 直接抽样所需数量，避免对全量列表 shuffle 的浪费
        candidates = random.sample(
            users, min(daily_limit, len(users))
        )
        poked = 0
        for user in candidates:
            if poked >= daily_limit:
                break
            if not user.user_id:
                continue
            if social_quota.is_quota_exceeded(
                user.user_id,
                scenario="主动拍一拍",
                daily_quota_per_user=daily_limit,
                cooldown_seconds=3600,
            ):
                continue
            try:
                bot = get_bot()
                ok = await ProtocolHelper.poke(
                    bot, user_id=user.user_id
                )
                if ok:
                    social_quota.mark_sent(
                        user.user_id, scenario="主动拍一拍"
                    )
                    poked += 1
                    logger.info(
                        f"主动拍一拍: {user.user_id}",
                        command="AI",
                    )
            except Exception as e:
                logger.debug(
                    f"主动拍一拍失败 {user.user_id}: {e}",
                    command="AI",
                    e=e,
                )

    @staticmethod
    async def _morning_greeting() -> None:
        """早安问候任务"""
        festival = SocialIntelligenceHelper._get_festival()
        festival_line = (
            f"今日节日: {festival}\n" if festival else ""
        )

        async def _build_prompt(
            group: GroupContextSnapshot, time_period: str
        ) -> str:
            style = (
                SocialIntelligenceHelper._parse_group_style(
                    group.style
                )
            )
            style_prompt = ProfileToolkit.build_group_style_prompt_block(style)
            return await persona_manager.get_active_persona_template(
                "greeting",
                greeting_type="早安",
                time_period=time_period,
                festival_line=festival_line,
                group_style=style_prompt or "群风格: 未设置",
            )

        await SocialIntelligenceHelper._generate_and_send_to_groups(
            _build_prompt, scenario="早安问候"
        )

    @staticmethod
    async def _evening_greeting() -> None:
        """晚安问候任务"""

        async def _build_prompt(
            group: GroupContextSnapshot, time_period: str
        ) -> str:
            style = (
                SocialIntelligenceHelper._parse_group_style(
                    group.style
                )
            )
            style_prompt = ProfileToolkit.build_group_style_prompt_block(style)
            return await persona_manager.get_active_persona_template(
                "greeting",
                greeting_type="晚安",
                time_period=time_period,
                festival_line="",
                group_style=style_prompt or "群风格: 未设置",
            )

        await SocialIntelligenceHelper._generate_and_send_to_groups(
            _build_prompt, scenario="晚安问候"
        )

    @staticmethod
    async def _news_push() -> None:
        """新闻/话题推送任务"""

        async def _build_prompt(
            _group: GroupContextSnapshot, time_period: str
        ) -> str:
            return await persona_manager.get_active_persona_template(
                "news", time_period=time_period
            )

        await SocialIntelligenceHelper._generate_and_send_to_groups(
            _build_prompt, scenario="新闻推送"
        )

    @staticmethod
    async def _topic_followup() -> None:
        """话题延续任务

        集成社交配额与门控检查。
        """
        groups = await GroupContextSnapshot.filter(
            is_active=True
        ).all()

        daily_quota = get_config("SOCIAL_QUOTA_PER_USER", 5)
        cooldown = get_config("SOCIAL_QUOTA_COOLDOWN", 3600)
        gate_enabled = get_config("SOCIAL_GATE_ENABLED", False)
        scenario = "话题延续"

        for group in groups:
            summary = group.summary or ""
            if not summary:
                continue

            # 配额检查
            if social_quota.is_quota_exceeded(
                group.group_id,
                scenario=scenario,
                daily_quota_per_user=daily_quota,
                cooldown_seconds=cooldown,
            ):
                continue

            prompt = await persona_manager.get_active_persona_template(
                "topic_followup", summary=summary[:200]
            )
            try:
                text = await llm_helper.chat_text(
                    [{"role": "user", "content": prompt}],
                    options={"temperature": 0.7},
                )
                if not text or len(text) >= 100:
                    continue

                # 社交门控
                if gate_enabled:
                    allow, rewritten, _ = (
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
                        continue
                    if rewritten:
                        text = rewritten

                await SocialIntelligenceHelper._send_to_group(
                    group.group_id, text
                )
                social_quota.mark_sent(
                    group.group_id, scenario=scenario
                )
            except Exception as e:
                logger.debug(
                    f"话题延续失败 {group.group_id}: {e}",
                    command="AI",
                    e=e,
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
        return get_config("PROACTIVE_POKE_ENABLED", False)

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
