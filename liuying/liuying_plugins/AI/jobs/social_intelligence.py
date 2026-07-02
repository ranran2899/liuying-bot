"""社交智能定时任务

早晚问候、节日问候、新闻推送、话题延续。
基于context_manager时段判断 + llm_helper生成文案。
"""

from datetime import datetime
import json
from typing import Any

from nonebot import get_bot
from nonebot_plugin_alconna import Target

from liuying.utils.apscheduler import task_manager
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from ..config import get_config
from ..core.context import context_manager
from ..core.group import build_group_style_prompt_block
from ..core.llm import llm_helper
from ..models.group_context import GroupContextSnapshot

__all__ = ["setup_social_intelligence_jobs"]


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


_GREETING_PROMPT = """你是流萤，请生成一句自然的{greeting_type}问候语。

当前时段: {time_period}
{festival_line}{group_style}

要求：
- 简短自然，不超过30字
- 符合流萤的性格和当前时段氛围
- 不要使用模板化用语

直接输出问候语，不要解释。"""


_NEWS_PROMPT = """请生成一条适合在群聊分享的轻松话题或新闻摘要。

当前时段: {time_period}

要求：
- 简短有趣，不超过40字
- 适合群聊氛围
- 可以是科技/游戏/生活类话题

直接输出内容，不要解释。"""


_TOPIC_FOLLOWUP_PROMPT = """基于最近的群聊摘要，生成一句自然的延续话题。

群聊摘要: {summary}

要求：
- 简短自然，不超过30字
- 像真人继续之前的聊天

直接输出内容，不要解释。"""


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

        参数:
            build_prompt: 接收(group, time_period)返回prompt的函数
            scenario: 场景标记

        返回:
            int: 发送成功的群数
        """
        if not get_config("SOCIAL_INTELLIGENCE_ENABLED", True):
            return 0

        try:
            groups = await GroupContextSnapshot.filter(
                is_active=True
            ).all()
        except Exception:
            groups = []
        if not groups:
            return 0

        time_period = context_manager.get_current_time_period()
        sent = 0
        for group in groups:
            if not context_manager.is_group_active_hour(
                group.group_id,
                quiet_start=get_config("GROUP_QUIET_START", 0),
                quiet_end=get_config("GROUP_QUIET_END", 7),
            ):
                continue

            try:
                prompt = await build_prompt(group, time_period)
                if not prompt:
                    continue
                text = await llm_helper.chat_text(
                    [{"role": "user", "content": prompt}],
                    options={"temperature": 0.7},
                )
                if text and len(text) < 100:
                    await SocialIntelligenceHelper._send_to_group(
                        group.group_id, text
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
            style_prompt = build_group_style_prompt_block(style)
            return _GREETING_PROMPT.format(
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
            style_prompt = build_group_style_prompt_block(style)
            return _GREETING_PROMPT.format(
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
            return _NEWS_PROMPT.format(time_period=time_period)

        await SocialIntelligenceHelper._generate_and_send_to_groups(
            _build_prompt, scenario="新闻推送"
        )

    @staticmethod
    async def _topic_followup() -> None:
        """话题延续任务"""
        try:
            groups = await GroupContextSnapshot.filter(
                is_active=True
            ).all()
        except Exception:
            groups = []

        for group in groups:
            summary = group.summary or ""
            if not summary:
                continue
            prompt = _TOPIC_FOLLOWUP_PROMPT.format(
                summary=summary[:200]
            )
            try:
                text = await llm_helper.chat_text(
                    [{"role": "user", "content": prompt}],
                    options={"temperature": 0.7},
                )
                if text and len(text) < 100:
                    await SocialIntelligenceHelper._send_to_group(
                        group.group_id, text
                    )
            except Exception as e:
                logger.debug(
                    f"话题延续失败 {group.group_id}: {e}",
                    command="AI",
                    e=e,
                )


# 向后兼容别名
_parse_group_style = (
    SocialIntelligenceHelper._parse_group_style
)
_generate_and_send_to_groups = (
    SocialIntelligenceHelper._generate_and_send_to_groups
)
_send_to_group = SocialIntelligenceHelper._send_to_group
_get_festival = SocialIntelligenceHelper._get_festival
_morning_greeting = (
    SocialIntelligenceHelper._morning_greeting
)
_evening_greeting = (
    SocialIntelligenceHelper._evening_greeting
)
_news_push = SocialIntelligenceHelper._news_push
_topic_followup = SocialIntelligenceHelper._topic_followup


async def setup_social_intelligence_jobs() -> None:
    """注册社交智能定时任务"""
    if not get_config("SOCIAL_INTELLIGENCE_ENABLED", True):
        logger.info(
            "社交智能功能已禁用，跳过任务注册",
            command="AI",
        )
        return

    await task_manager.add_cron_task(
        task_id="ai_morning_greeting",
        func=_morning_greeting,
        hour=8,
        minute=0,
    )
    await task_manager.add_cron_task(
        task_id="ai_evening_greeting",
        func=_evening_greeting,
        hour=22,
        minute=30,
    )
    await task_manager.add_interval_task(
        task_id="ai_news_push",
        func=_news_push,
        hours=4,
    )
    await task_manager.add_interval_task(
        task_id="ai_topic_followup",
        func=_topic_followup,
        hours=2,
    )

    logger.info(
        "社交智能任务已注册（早安8:00/晚安22:30/新闻4h/话题2h）",
        command="AI",
    )
