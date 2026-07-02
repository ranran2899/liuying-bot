from dataclasses import dataclass
import re

from nonebot.adapters import Bot, Event
from nonebot.exception import IgnoredException
from nonebot.matcher import Matcher
from nonebot.message import run_preprocessor
from nonebot.typing import T_State
from nonebot_plugin_alconna import At, UniMsg
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.config import Config
from liuying.models.ban_console import BanConsole
from liuying.models.sensitive_word import SensitiveWord
from liuying.services.cache import Cache
from liuying.utils.enum import CacheType, PluginType
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from .auth.utils import get_group_channel_ids

Config.add_plugin_config(
    "hook",
    "SENSITIVE_CHECK_ENABLE",
    True,
    help="是否启用敏感词检测",
    default_value=True,
    type=bool,
)

Config.add_plugin_config(
    "hook",
    "SENSITIVE_BAN_TIME",
    60,
    help="触发敏感词封禁时长（分钟）",
    default_value=60,
    type=int,
)

LOG_COMMAND = "SensitiveHook"

sensitive_cache = Cache(CacheType.SENSITIVE)


@dataclass(slots=True)
class SensitiveResult:
    """敏感词检测结果"""

    matched: bool
    words: list[str]
    action: int
    replacement: str


class SensitiveWordManager:
    """敏感词管理器"""

    @staticmethod
    async def get_words() -> list[SensitiveWord]:
        """获取敏感词列表（带缓存）

        返回:
            list[SensitiveWord]: 敏感词列表
        """
        return await sensitive_cache.get_or_load(
            "all",
            loader=SensitiveWord.get_active_words,
            expire=300,
            default=[],
        )

    @staticmethod
    def check_text(text: str, words: list[SensitiveWord]) -> SensitiveResult:
        """检查文本是否包含敏感词

        参数:
            text: 待检查文本
            words: 敏感词列表

        返回:
            SensitiveResult: 检测结果
        """
        matched_words: list[str] = []
        max_action = 0
        replacement = "*"
        regex_patterns: list[tuple[re.Pattern, SensitiveWord]] = []

        text_lower = text.lower()
        for word in words:
            if word.is_regex:
                try:
                    pattern = re.compile(word.word, re.IGNORECASE)
                    regex_patterns.append((pattern, word))
                except re.error:
                    continue
            elif word.word.lower() in text_lower:
                matched_words.append(word.word)
                if word.action > max_action:
                    max_action = word.action
                    replacement = word.replacement or "*"

        for pattern, word in regex_patterns:
            if pattern.search(text):
                matched_words.append(word.word)
                if word.action > max_action:
                    max_action = word.action
                    replacement = word.replacement or "*"

        return SensitiveResult(
            matched=bool(matched_words),
            words=matched_words,
            action=max_action,
            replacement=replacement,
        )

    @staticmethod
    def replace_text(text: str, result: SensitiveResult) -> str:
        """替换文本中的敏感词

        参数:
            text: 原文本
            result: 检测结果

        返回:
            str: 替换后的文本
        """
        replaced_text = text
        for word in result.words:
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            replaced_text = pattern.sub(
                result.replacement * len(word), replaced_text
            )
        return replaced_text


@run_preprocessor
async def _(
    matcher: Matcher,
    bot: Bot,
    event: Event,
    state: T_State,
    session: Uninfo,
    message: UniMsg,
):
    """敏感词检测"""
    if not Config.get_config("hook", "SENSITIVE_CHECK_ENABLE"):
        return

    if plugin := matcher.plugin:
        if metadata := plugin.metadata:
            extra = metadata.extra
            if extra.get("plugin_type") in {
                PluginType.HIDDEN,
                PluginType.DEPENDANT,
                PluginType.ADMIN,
                PluginType.SUPERUSER,
            }:
                return

    user_id = session.user.id
    if user_id in bot.config.superusers:
        return

    words = await SensitiveWordManager.get_words()
    if not words:
        return

    text = message.extract_plain_text()
    if not text:
        return

    result = SensitiveWordManager.check_text(text, words)

    if not result.matched:
        return

    ids = get_group_channel_ids(session)
    logger.warning(
        f"用户触发敏感词: {result.words}, 动作: {result.action}",
        LOG_COMMAND,
        session=session,
    )

    match result.action:
        case 3:
            ban_time = Config.get_config("hook", "SENSITIVE_BAN_TIME") or 60
            await BanConsole.ban(
                user_id,
                ids.group_id,
                9,
                f"触发敏感词: {result.words}",
                ban_time * 60,
                bot.self_id,
            )
            await MessageUtils.build_message(
                [
                    At(flag="user", target=user_id),
                    f"检测到敏感内容，您将被封禁 {ban_time} 分钟",
                ]
            ).send()
            raise IgnoredException("触发敏感词封禁")

        case 2:
            await MessageUtils.build_message(
                [At(flag="user", target=user_id), "您的消息包含敏感内容，已被拦截"]
            ).send()
            raise IgnoredException("触发敏感词拦截")

        case _:
            replaced_text = SensitiveWordManager.replace_text(text, result)
            state["sensitive_replaced"] = True
            state["sensitive_original"] = text
            state["sensitive_replaced_text"] = replaced_text
            logger.info(
                f"敏感词已替换: {result.words}",
                LOG_COMMAND,
                session=session,
            )
