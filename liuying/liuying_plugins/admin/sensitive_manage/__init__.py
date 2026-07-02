from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Match,
    Option,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import PluginExtraData
from liuying.models.sensitive_word import SensitiveWord
from liuying.utils.enum import PluginType
from liuying.utils.message import MessageUtils
from liuying.utils.rules import admin_check

_ACTION_MAP = {1: "替换", 2: "拦截", 3: "封禁"}

__plugin_meta__ = PluginMetadata(
    name="敏感词管理",
    description="管理敏感词，配合敏感词检测Hook使用",
    usage="""
    管理员命令
        格式:
        添加敏感词 [词语] ?[-l 等级] ?[-a 动作] ?[-r 替换] ?[-e 描述]
        删除敏感词 [词语]
        敏感词列表 ?[-p 页码]

    超级管理员额外命令
        添加正则敏感词 [正则] ?[-l 等级] ?[-a 动作] ?[-r 替换] ?[-e 描述]
        启用敏感词 [词语]
        禁用敏感词 [词语]
        清空敏感词

    等级: 1-低 2-中 3-高
    动作: 1-替换 2-拦截 3-封禁
    """.strip(),
    extra=PluginExtraData(
        admin_level=5,
        plugin_type=PluginType.SUPER_AND_ADMIN,
        superuser_help="""
        超级管理员额外命令
        添加正则敏感词 [正则] ?[-l 等级] ?[-a 动作] ?[-r 替换] ?[-e 描述]
        启用敏感词 [词语]
        禁用敏感词 [词语]
        清空敏感词
        """,
    ).to_dict(),
)

_add_matcher = on_alconna(
    Alconna(
        "添加敏感词",
        Args["word", str],
        Option("-l|--level", Args["level", int, 1], help_text="敏感等级 1-3"),
        Option(
            "-a|--action",
            Args["action", int, 1],
            help_text="处理方式 1-替换 2-拦截 3-封禁",
        ),
        Option(
            "-r|--replacement",
            Args["replacement", str, "*"],
            help_text="替换文本",
        ),
        Option(
            "-e|--desc",
            Args["description", str, ""],
            help_text="描述",
        ),
    ),
    rule=admin_check(5),
    priority=5,
    block=True,
)

_add_regex_matcher = on_alconna(
    Alconna(
        "添加正则敏感词",
        Args["word", str],
        Option(
            "-l|--level",
            Args["level", int, 1],
            help_text="敏感等级 1-3",
        ),
        Option(
            "-a|--action",
            Args["action", int, 1],
            help_text="处理方式 1-替换 2-拦截 3-封禁",
        ),
        Option(
            "-r|--replacement",
            Args["replacement", str, "*"],
            help_text="替换文本",
        ),
        Option(
            "-e|--desc",
            Args["description", str, ""],
            help_text="描述",
        ),
    ),
    permission=SUPERUSER,
    priority=5,
    block=True,
)

_remove_matcher = on_alconna(
    Alconna("删除敏感词", Args["word", str]),
    rule=admin_check(5),
    priority=5,
    block=True,
)

_list_matcher = on_alconna(
    Alconna("敏感词列表", Option("-p|--page", Args["page", int, 1], help_text="页码")),
    rule=admin_check(5),
    priority=5,
    block=True,
)

_enable_matcher = on_alconna(
    Alconna("启用敏感词", Args["word", str]),
    permission=SUPERUSER,
    priority=5,
    block=True,
)

_disable_matcher = on_alconna(
    Alconna("禁用敏感词", Args["word", str]),
    permission=SUPERUSER,
    priority=5,
    block=True,
)

_clear_matcher = on_alconna(
    Alconna("清空敏感词"),
    permission=SUPERUSER,
    priority=5,
    block=True,
)

PAGE_SIZE = 20


def _validate_level(level: int) -> int:
    """校验敏感等级范围

    参数:
        level: 敏感等级

    返回:
        int: 校验后的等级
    """
    return max(1, min(3, level))


def _validate_action(action: int) -> int:
    """校验处理方式范围

    参数:
        action: 处理方式

    返回:
        int: 校验后的处理方式
    """
    return max(1, min(3, action))


@_add_matcher.handle()
async def _(
    session: Uninfo,
    word: str,
    level: Match[int],
    action: Match[int],
    replacement: Match[str],
    description: Match[str],
):
    """添加普通敏感词"""
    _level = _validate_level(level.result) if level.available else 1
    _action = _validate_action(action.result) if action.available else 1
    _replacement = replacement.result if replacement.available else "*"
    _description = description.result if description.available else None

    result = await SensitiveWord.add_word(
        word=word,
        is_regex=False,
        level=_level,
        action=_action,
        replacement=_replacement,
        description=_description,
    )

    if result:
        action_map = _ACTION_MAP
        await MessageUtils.build_message(
            f"添加敏感词成功!\n"
            f"词语: {word}\n"
            f"等级: {_level}\n"
            f"动作: {action_map.get(_action, '未知')}"
        ).finish(reply_to=True)
    await MessageUtils.build_message(f"敏感词 {word} 已存在").finish(reply_to=True)


@_add_regex_matcher.handle()
async def _(
    session: Uninfo,
    word: str,
    level: Match[int],
    action: Match[int],
    replacement: Match[str],
    description: Match[str],
):
    """添加正则敏感词"""
    import re

    try:
        re.compile(word)
    except re.error as e:
        await MessageUtils.build_message(f"正则表达式无效: {e}").finish(reply_to=True)

    _level = _validate_level(level.result) if level.available else 1
    _action = _validate_action(action.result) if action.available else 1
    _replacement = replacement.result if replacement.available else "*"
    _description = description.result if description.available else None

    result = await SensitiveWord.add_word(
        word=word,
        is_regex=True,
        level=_level,
        action=_action,
        replacement=_replacement,
        description=_description,
    )

    if result:
        action_map = _ACTION_MAP
        await MessageUtils.build_message(
            f"添加正则敏感词成功!\n"
            f"正则: {word}\n"
            f"等级: {_level}\n"
            f"动作: {action_map.get(_action, '未知')}"
        ).finish(reply_to=True)
    await MessageUtils.build_message(f"正则敏感词 {word} 已存在").finish(reply_to=True)


@_remove_matcher.handle()
async def _(session: Uninfo, word: str):
    """删除敏感词"""
    if await SensitiveWord.remove_word(word):
        await MessageUtils.build_message(f"已删除敏感词: {word}").finish(reply_to=True)
    await MessageUtils.build_message(f"未找到敏感词: {word}").finish(reply_to=True)


@_list_matcher.handle()
async def _(session: Uninfo, page: Match[int]):
    """查看敏感词列表"""
    words = await SensitiveWord.filter().all()

    if not words:
        await MessageUtils.build_message("当前没有敏感词").finish(reply_to=True)

    _page = page.result if page.available else 1
    total = len(words)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    _page = max(1, min(_page, total_pages))

    start = (_page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_words = words[start:end]

    action_map = _ACTION_MAP
    lines = []
    for w in page_words:
        status = "启用" if w.status else "禁用"
        wtype = "正则" if w.is_regex else "普通"
        action_text = action_map.get(w.action, "未知")
        lines.append(f"[{status}] {w.word} ({wtype}, 等级{w.level}, {action_text})")

    msg = f"敏感词列表 (第{_page}/{total_pages}页, 共{total}条)\n" + "\n".join(lines)
    await MessageUtils.build_message(msg).finish(reply_to=True)


@_enable_matcher.handle()
async def _(session: Uninfo, word: str):
    """启用敏感词"""
    if await SensitiveWord.update_word(word, status=True):
        await MessageUtils.build_message(f"已启用敏感词: {word}").finish(reply_to=True)
    await MessageUtils.build_message(f"未找到敏感词: {word}").finish(reply_to=True)


@_disable_matcher.handle()
async def _(session: Uninfo, word: str):
    """禁用敏感词"""
    if await SensitiveWord.update_word(word, status=False):
        await MessageUtils.build_message(f"已禁用敏感词: {word}").finish(reply_to=True)
    await MessageUtils.build_message(f"未找到敏感词: {word}").finish(reply_to=True)


@_clear_matcher.handle()
async def _(session: Uninfo):
    """清空所有敏感词"""
    count = await SensitiveWord.filter().count()
    if count == 0:
        await MessageUtils.build_message("当前没有敏感词").finish(reply_to=True)

    await SensitiveWord.filter().delete()
    await SensitiveWord._invalidate_cache()
    await MessageUtils.build_message(f"已清空所有敏感词，共删除 {count} 条").finish(
        reply_to=True
    )
