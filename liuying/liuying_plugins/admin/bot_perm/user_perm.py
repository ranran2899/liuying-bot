from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Arparma,
    At,
    Match,
    Option,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import PluginExtraData
from liuying.models._user import UserLevel
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

__plugin_meta__ = PluginMetadata(
    name="用户全局权限管理",
    description="设置用户全局权限",
    usage="""
    添加权限 [level] [@user/用户id] -g [群号]  # 添加指定群权限
    添加权限 [level] [@user/用户id] -g         # 添加当前群权限
    添加权限 [level] [@user/用户id]           # 添加用户个人权限

    删除权限 [@user/用户id] -g [群号]          # 删除指定群权限
    删除权限 [@user/用户id] -g                 # 删除当前群权限
    删除权限 [@user/用户id]                    # 删除用户个人权限
    """,
    extra=PluginExtraData(
        author="liuying",
        version="1.0",
        plugin_type=PluginType.SUPER_AND_ADMIN,
        admin_level=5,
    ).to_dict(),
)


_add_matcher = on_alconna(
    Alconna(
        "添加权限",
        Args["level", int]["uid", [str, At]],
        Option(
            "-g|--group",
            Args["gid", str],
            default=None,
            help_text="指定群组（不指定则为个人权限，不填群号则为当前群）",
        ),
    ),
    permission=SUPERUSER,
    priority=5,
    block=True,
)


_delete_matcher = on_alconna(
    Alconna(
        "删除权限",
        Args["uid", [str, At]],
        Option(
            "-g|--group",
            Args["gid", str],
            default=None,
            help_text="指定群组（不指定则为个人权限，不填群号则为当前群）",
        ),
    ),
    permission=SUPERUSER,
    priority=5,
    block=True,
)


def _resolve_group_and_type(
    session: Uninfo,
    gid: Match[str],
) -> tuple[str | None, str]:
    """解析群组ID和权限类型

    参数:
        session: 会话信息
        gid: 群组ID匹配结果

    返回:
        tuple[str | None, str]: (群组ID, 权限类型描述)
    """
    match (gid.available, session.group):
        case (True, _):
            return gid.result, "群组"
        case (_, group) if group:
            return group.id, "当前群组"
        case _:
            return None, "个人"


async def _get_current_level(uid: str, group_id: str | None) -> int:
    """获取当前权限等级

    参数:
        uid: 用户ID
        group_id: 群组ID

    返回:
        int: 当前权限等级
    """
    if group_id is None:
        return await UserLevel.get_user_level(uid)
    return await UserLevel.get_user_level(uid, group_id)


@_add_matcher.handle()
async def handle_add_permission(
    session: Uninfo,
    arparma: Arparma,
    level: int,
    uid: str | At,
    gid: Match[str],
):
    """处理添加权限指令

    参数:
        session: 会话信息
        arparma: 命令解析结果
        level: 权限等级
        uid: 用户ID或@对象
        gid: 群组ID（可选）
    """
    if isinstance(uid, At):
        uid = uid.target

    group_id, permission_type = _resolve_group_and_type(session, gid)
    current_level = await _get_current_level(uid, group_id)

    await UserLevel.set_level(uid, group_id, level=level, group_flag=1)

    logger.info(
        f"添加{permission_type}权限: 用户 {uid} 权限从 {current_level} -> {level}",
        arparma.header_result,
        session=session,
    )

    if session.group:
        await MessageUtils.build_message(
            [
                "成功为 ",
                At(flag="user", target=uid),
                f" 添加{permission_type}权限：{current_level} -> {level}",
            ]
        ).finish(reply_to=True)
    await MessageUtils.build_message(
        f"成功为用户 {uid} 添加{permission_type}权限：{current_level} -> {level}"
    ).finish()


@_delete_matcher.handle()
async def handle_delete_permission(
    session: Uninfo,
    arparma: Arparma,
    uid: str | At,
    gid: Match[str],
):
    """处理删除权限指令

    参数:
        session: 会话信息
        arparma: 命令解析结果
        uid: 用户ID或@对象
        gid: 群组ID（可选）
    """
    if isinstance(uid, At):
        uid = uid.target

    group_id, permission_type = _resolve_group_and_type(session, gid)
    current_level = await _get_current_level(uid, group_id)

    if current_level <= 0:
        await MessageUtils.build_message("用户没有权限可删除").finish(reply_to=True)

    await UserLevel.set_level(uid, group_id, level=0, group_flag=1)

    logger.info(
        f"删除{permission_type}权限: 用户 {uid} 权限从 {current_level} -> 0",
        arparma.header_result,
        session=session,
    )

    if session.group:
        await MessageUtils.build_message(
            [
                "成功删除 ",
                At(flag="user", target=uid),
                f" 的{permission_type}权限",
            ]
        ).finish(reply_to=True)
    await MessageUtils.build_message(
        f"成功删除用户 {uid} 的{permission_type}权限"
    ).finish()
