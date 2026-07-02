from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Arparma,
    At,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import PluginExtraData
from liuying.models._user import UserLevel
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

__plugin_meta__ = PluginMetadata(
    name="机器人用户权限管理",
    description="设置指定机器人的用户权限",
    usage="""
    bot添加权限 [bot_id] [level] [@user/用户id]  # 为指定机器人添加用户权限
    bot删除权限 [bot_id] [@user/用户id]          # 删除指定机器人的用户权限
    bot查询权限 [bot_id] [@user/用户id]          # 查询用户在指定机器人的权限
    """,
    extra=PluginExtraData(
        author="liuying",
        version="1.0",
        plugin_type=PluginType.SUPERUSER,
    ).to_dict(),
)


_add_matcher = on_alconna(
    Alconna(
        "bot添加权限",
        Args["bot_id", str],
        Args["level", int],
        Args["uid", [str, At]],
    ),
    permission=SUPERUSER,
    priority=5,
    block=True,
)


_delete_matcher = on_alconna(
    Alconna(
        "bot删除权限",
        Args["bot_id", str],
        Args["uid", [str, At]],
    ),
    permission=SUPERUSER,
    priority=5,
    block=True,
)


_query_matcher = on_alconna(
    Alconna(
        "bot查询权限",
        Args["bot_id", str],
        Args["uid", [str, At]],
    ),
    permission=SUPERUSER,
    priority=5,
    block=True,
)


@_add_matcher.handle()
async def handle_add_permission(
    session: Uninfo,
    arparma: Arparma,
    bot_id: str,
    level: int,
    uid: str | At,
):
    """
    处理添加机器人用户权限指令

    参数:
        session: 会话信息
        arparma: 命令解析结果
        bot_id: 机器人ID
        level: 权限等级
        uid: 用户ID或@对象
    """
    if isinstance(uid, At):
        uid = uid.target

    current_level = await UserLevel.get_bot_level(bot_id, uid)

    await UserLevel.set_bot_level(bot_id, uid, level)

    logger.info(
        f"添加机器人用户权限: 机器人 {bot_id} 用户 {uid} "
        f"权限从 {current_level} -> {level}",
        arparma.header_result,
        session=session,
    )

    await MessageUtils.build_message(
        f"成功为机器人 {bot_id} 的用户 {uid} 添加权限：{current_level} -> {level}"
    ).finish()


@_delete_matcher.handle()
async def handle_delete_permission(
    session: Uninfo,
    arparma: Arparma,
    bot_id: str,
    uid: str | At,
):
    """
    处理删除机器人用户权限指令

    参数:
        session: 会话信息
        arparma: 命令解析结果
        bot_id: 机器人ID
        uid: 用户ID或@对象
    """
    if isinstance(uid, At):
        uid = uid.target

    current_level = await UserLevel.get_bot_level(bot_id, uid)

    if current_level <= 0:
        await MessageUtils.build_message(
            f"用户 {uid} 在机器人 {bot_id} 没有权限可删除"
        ).finish()

    await UserLevel.delete_bot_level(bot_id, uid)

    logger.info(
        f"删除机器人用户权限: 机器人 {bot_id} 用户 {uid} "
        f"权限从 {current_level} -> 0",
        arparma.header_result,
        session=session,
    )

    await MessageUtils.build_message(
        f"成功删除机器人 {bot_id} 的用户 {uid} 的权限"
    ).finish()


@_query_matcher.handle()
async def handle_query_permission(
    session: Uninfo,
    arparma: Arparma,
    bot_id: str,
    uid: str | At,
):
    """
    处理查询机器人用户权限指令

    参数:
        session: 会话信息
        arparma: 命令解析结果
        bot_id: 机器人ID
        uid: 用户ID或@对象
    """
    if isinstance(uid, At):
        uid = uid.target

    current_level = await UserLevel.get_bot_level(bot_id, uid)

    await MessageUtils.build_message(
        f"机器人 {bot_id} 的用户 {uid} 当前权限等级：{current_level}"
    ).finish()
