"""基于统一会话的权限判断"""

from collections.abc import Callable

from nonebot.permission import Permission

from .model import Session
from .params import UniSession

_UniSession = UniSession()


async def _private(sess: Session | None = _UniSession) -> bool:
    if not sess:
        return False
    return sess.scene.is_private


PRIVATE: Permission = Permission(_private)
"""匹配任意私聊类型事件"""


async def _group(sess: Session | None = _UniSession) -> bool:
    if not sess:
        return False
    return sess.scene.is_group


GROUP: Permission = Permission(_group)
"""匹配任意群聊类型事件"""


async def _guild(sess: Session | None = _UniSession) -> bool:
    if not sess:
        return False
    return sess.scene.is_guild or sess.scene.is_channel


GUILD: Permission = Permission(_guild)
"""匹配任意频道消息类型事件"""


def ROLE_IN(role_id: str, *role_ids: str) -> Permission:
    """检查成员是否在指定角色组中"""

    async def _role_in(sess: Session | None = _UniSession) -> bool:
        if not sess or not sess.member or not sess.member.roles:
            return False
        member_role_ids = {role.id for role in sess.member.roles}
        _role_ids = {role_id, *role_ids}
        return not member_role_ids.isdisjoint(_role_ids)

    return Permission(_role_in)


def ROLE_NOT_IN(role_id: str, *role_ids: str) -> Permission:
    """检查成员是否不在指定角色组中"""

    async def _role_not_in(sess: Session | None = _UniSession) -> bool:
        if not sess or not sess.member or not sess.member.roles:
            return True
        member_role_ids = {role.id for role in sess.member.roles}
        _role_ids = {role_id, *role_ids}
        return member_role_ids.isdisjoint(_role_ids)

    return Permission(_role_not_in)


def MEMBER() -> Permission:
    """匹配普通成员"""
    return ROLE_NOT_IN("CHANNEL_ADMINISTRATOR", "ADMINISTRATOR", "OWNER")


def ADMIN() -> Permission:
    """匹配管理员及以上角色"""
    return ROLE_IN("ADMINISTRATOR", "OWNER")


def OWNER() -> Permission:
    """匹配群主/创建者角色"""
    return ROLE_IN("OWNER")


def ROLE_LEVEL(checker: Callable[[int], bool]) -> Permission:
    """检查用户角色等级"""

    async def _level(sess: Session | None = _UniSession) -> bool:
        if not sess or not sess.member or not sess.member.roles:
            return False
        max_level = max((role.level for role in sess.member.roles), default=0)
        return checker(max_level)

    return Permission(_level)


def USER_IN(user_id: str, *user_ids: str) -> Permission:
    """检查用户是否在指定用户中"""

    async def _user_in(sess: Session | None = _UniSession) -> bool:
        if not sess:
            return False
        return sess.user.id in (user_id, *user_ids)

    return Permission(_user_in)


def USER_NOT_IN(user_id: str, *user_ids: str) -> Permission:
    """检查用户是否不在指定用户中"""

    async def _user_not_in(sess: Session | None = _UniSession) -> bool:
        if not sess:
            return True
        return sess.user.id not in (user_id, *user_ids)

    return Permission(_user_not_in)


def SCENE_IN(scene_id: str, *scene_ids: str) -> Permission:
    """检查场景是否在指定场景中"""

    async def _scene_in(sess: Session | None = _UniSession) -> bool:
        if not sess:
            return False
        return sess.scene.id in (scene_id, *scene_ids)

    return Permission(_scene_in)


def SCENE_NOT_IN(scene_id: str, *scene_ids: str) -> Permission:
    """检查场景是否不在指定场景中"""

    async def _scene_not_in(sess: Session | None = _UniSession) -> bool:
        if not sess:
            return True
        return sess.scene.id not in (scene_id, *scene_ids)

    return Permission(_scene_not_in)
