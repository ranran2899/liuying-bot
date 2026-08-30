from nonebot_plugin_alconna import At, Match
from nonebot_plugin_uninfo import Uninfo

from liuying.models._user import UserPermLevel
from liuying.utils.log import logger


class PermManage:
    """用户权限管理核心逻辑"""

    @staticmethod
    def _resolve_uid(uid: str | At) -> str:
        """解析用户ID，At对象取target"""
        return uid.target if isinstance(uid, At) else uid

    @staticmethod
    def _resolve_group(session: Uninfo, gid: Match[str]) -> tuple[str | None, str]:
        """解析群组ID和权限类型描述

        优先取 -g 参数，其次当前群，最后为全局个人权限。

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
                return None, "全局"

    @staticmethod
    def _build_result(
        session: Uninfo, uid: str, perm_type: str, detail: str
    ) -> list[str | At]:
        """构造权限变更结果消息，群聊自动@目标用户

        参数:
            session: 会话信息
            uid: 目标用户id
            perm_type: 权限类型描述
            detail: 权限变化详情

        返回:
            list[str | At]: 消息段列表
        """
        target: At | str = (
            At(flag="user", target=uid) if session.group else f"用户 {uid}"
        )
        return ["已将 ", target, f" 的{perm_type}权限{detail}"]

    @classmethod
    async def add_permission(
        cls, session: Uninfo, uid: str | At, level: int, gid: Match[str]
    ) -> str | list[str | At]:
        """添加用户权限

        参数:
            session: 会话信息
            uid: 用户ID或@对象
            level: 权限等级
            gid: 群组ID匹配结果

        返回:
            MESSAGE_TYPE: 结果消息
        """
        uid = cls._resolve_uid(uid)
        platform = session.adapter
        group_id, perm_type = cls._resolve_group(session, gid)
        old_level = await UserPermLevel.get_scoped_level(
            uid, group_id=group_id, platform=platform
        )

        await UserPermLevel.set_level(
            uid, group_id, level=level, group_flag=1, platform=platform
        )

        logger.info(
            f"添加{perm_type}权限: 用户 {uid} 权限从 {old_level} -> {level}",
            "添加权限",
            session=session,
        )

        return cls._build_result(
            session, uid, perm_type, f"从 {old_level} 修改为 {level}"
        )

    @classmethod
    async def delete_permission(
        cls, session: Uninfo, uid: str | At, gid: Match[str]
    ) -> str | list[str | At]:
        """删除用户权限

        参数:
            session: 会话信息
            uid: 用户ID或@对象
            gid: 群组ID匹配结果

        返回:
            MESSAGE_TYPE: 结果消息
        """
        uid = cls._resolve_uid(uid)
        platform = session.adapter
        group_id, perm_type = cls._resolve_group(session, gid)
        old_level = await UserPermLevel.get_scoped_level(
            uid, group_id=group_id, platform=platform
        )

        if old_level <= 0:
            return "用户没有权限可删除"

        await UserPermLevel.set_level(
            uid, group_id, level=0, group_flag=1, platform=platform
        )

        logger.info(
            f"删除{perm_type}权限: 用户 {uid} 权限从 {old_level} -> 0",
            "删除权限",
            session=session,
        )

        return cls._build_result(session, uid, perm_type, f"从 {old_level} 修改为 0")

    @classmethod
    async def add_bot_permission(
        cls, session: Uninfo, bot_id: str, uid: str | At, level: int
    ) -> str:
        """添加指定机器人的用户权限

        参数:
            session: 会话信息
            bot_id: 机器人ID
            uid: 用户ID或@对象
            level: 权限等级

        返回:
            MESSAGE_TYPE: 结果消息
        """
        uid = cls._resolve_uid(uid)
        old_level = await UserPermLevel.get_scoped_level(
            uid, bot_id=bot_id, platform=session.adapter
        )

        await UserPermLevel.set_bot_level(
            bot_id, uid, level, platform=session.adapter
        )

        logger.info(
            f"添加机器人用户权限: 机器人 {bot_id} 用户 {uid} "
            f"权限从 {old_level} -> {level}",
            "bot添加权限",
            session=session,
        )

        return f"已将机器人 {bot_id} 的用户 {uid} 权限从 {old_level} 修改为 {level}"

    @classmethod
    async def delete_bot_permission(
        cls, session: Uninfo, bot_id: str, uid: str | At
    ) -> str:
        """删除指定机器人的用户权限

        参数:
            session: 会话信息
            bot_id: 机器人ID
            uid: 用户ID或@对象

        返回:
            MESSAGE_TYPE: 结果消息
        """
        uid = cls._resolve_uid(uid)
        old_level = await UserPermLevel.get_scoped_level(
            uid, bot_id=bot_id, platform=session.adapter
        )

        if old_level <= 0:
            return f"用户 {uid} 在机器人 {bot_id} 没有权限可删除"

        await UserPermLevel.delete_bot_level(bot_id, uid)

        logger.info(
            f"删除机器人用户权限: 机器人 {bot_id} 用户 {uid} "
            f"权限从 {old_level} -> 0",
            "bot删除权限",
            session=session,
        )

        return f"已删除机器人 {bot_id} 的用户 {uid} 的权限（原等级 {old_level}）"

    @classmethod
    async def query_bot_permission(
        cls, session: Uninfo, bot_id: str, uid: str | At
    ) -> str:
        """查询用户在指定机器人的权限

        参数:
            session: 会话信息
            bot_id: 机器人ID
            uid: 用户ID或@对象

        返回:
            MESSAGE_TYPE: 结果消息
        """
        uid = cls._resolve_uid(uid)
        level = await UserPermLevel.get_scoped_level(
            uid, bot_id=bot_id, platform=session.adapter
        )

        return f"机器人 {bot_id} 的用户 {uid} 当前权限等级：{level}"
