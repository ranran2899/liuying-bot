"""AI ACL 检查器

封装流萤本体 ACL 体系（超级用户/UserLevel等级/BanConsole黑名单），
为 AI 插件提供统一的只读权限检查接口。

注意：本模块仅提供权限检查，不提供管理操作（ban/unban/授权等）。
管理操作请直接使用流萤本体插件：
- ban/unban/黑名单查询: liuying.liuying_plugins.admin.ban
- 管理员等级设置: liuying.liuying_plugins.admin.bot_perm
- 插件开关: liuying.liuying_plugins.admin.plugin_switch

权限层级：
1. 超级用户（bot.config.superusers） - 最高权限，绕过所有检查
2. 管理员（UserLevel.user_level >= level） - 等级鉴权
3. 普通用户 - 默认权限

黑名单检查：
- BanConsole.is_ban(user_id, group_id) - 用户级拉黑
- BanConsole.is_ban(None, group_id) - 群组级拉黑
"""

from dataclasses import dataclass
from typing import Any

from liuying.models._user import UserLevel
from liuying.models.ban_console import BanConsole

__all__ = ["AclChecker", "PermissionResult", "acl_checker"]


@dataclass(slots=True)
class PermissionResult:
    """权限检查结果

    Attributes:
        allowed: 是否允许
        reason: 拒绝原因，允许时为空
        user_level: 用户等级
        is_superuser: 是否超级用户
        is_blacklisted: 是否在黑名单
    """

    allowed: bool
    reason: str = ""
    user_level: int = 0
    is_superuser: bool = False
    is_blacklisted: bool = False


class AclChecker:
    """AI ACL 检查器

    封装超级用户/管理员等级/黑名单三类只读权限检查能力，
    通过类变量共享管理员等级常量，所有方法均为静态方法。
    """

    ADMIN_LEVEL_BASIC: int = 5
    """基础管理员等级（可执行开关/查询命令）"""

    ADMIN_LEVEL_HIGH: int = 7
    """高级管理员等级（可执行黑名单管理/重置命令）"""

    ADMIN_LEVEL_SUPER: int = 10
    """超级管理员等级（仅超级用户可达）"""

    @staticmethod
    async def check_superuser(
        user_id: str,
        bot: Any = None,
    ) -> bool:
        """检查用户是否超级用户

        参数:
            user_id: 用户ID
            bot: Bot对象，此参数仅保留兼容性，不再使用

        返回:
            bool: 是否超级用户
        """
        return UserLevel.is_superuser(str(user_id))

    @staticmethod
    async def get_user_level(
        user_id: str,
        bot_id: str | None = None,
        group_id: str | None = None,
    ) -> int:
        """获取用户权限等级

        参数:
            user_id: 用户ID
            bot_id: 机器人ID
            group_id: 群组ID

        返回:
            int: 权限等级（0为普通用户）
        """
        return await UserLevel.get_level(user_id, bot_id, group_id)

    @staticmethod
    async def check_admin(
        user_id: str,
        level: int | None = None,
        *,
        bot: Any = None,
        bot_id: str | None = None,
        group_id: str | None = None,
    ) -> bool:
        """检查用户是否具有指定管理员等级

        超级用户直接通过。

        参数:
            user_id: 用户ID
            level: 需要的管理员等级，None时用基础管理员等级
            bot: Bot对象
            bot_id: 机器人ID
            group_id: 群组ID

        返回:
            bool: 是否通过
        """
        if level is None:
            level = AclChecker.ADMIN_LEVEL_BASIC
        if await AclChecker.check_superuser(user_id, bot):
            return True
        user_level = await AclChecker.get_user_level(
            user_id, bot_id, group_id
        )
        return user_level >= level

    @staticmethod
    async def check_blacklist(
        user_id: str,
        group_id: str | None = None,
    ) -> bool:
        """检查用户/群组是否在黑名单

        参数:
            user_id: 用户ID
            group_id: 群组ID

        返回:
            bool: 是否在黑名单（True表示被拉黑）
        """
        if await BanConsole.is_ban(user_id, group_id):
            return True
        if group_id and await BanConsole.is_ban(None, group_id):
            return True
        return False

    @staticmethod
    async def check_permission(
        user_id: str,
        level: int | None = None,
        *,
        bot: Any = None,
        bot_id: str | None = None,
        group_id: str | None = None,
        check_blacklist_flag: bool = True,
    ) -> PermissionResult:
        """综合权限检查

        依次检查：黑名单 → 超级用户 → 管理员等级。

        参数:
            user_id: 用户ID
            level: 需要的管理员等级，None时用基础管理员等级
            bot: Bot对象
            bot_id: 机器人ID
            group_id: 群组ID
            check_blacklist_flag: 是否检查黑名单

        返回:
            PermissionResult: 权限检查结果
        """
        if level is None:
            level = AclChecker.ADMIN_LEVEL_BASIC
        is_blacklisted = False
        if check_blacklist_flag:
            is_blacklisted = await AclChecker.check_blacklist(
                user_id, group_id
            )
            if is_blacklisted:
                return PermissionResult(
                    allowed=False,
                    reason="用户/群组在黑名单中",
                    user_level=0,
                    is_superuser=False,
                    is_blacklisted=True,
                )

        is_super = await AclChecker.check_superuser(user_id, bot)
        if is_super:
            return PermissionResult(
                allowed=True,
                reason="",
                user_level=AclChecker.ADMIN_LEVEL_SUPER,
                is_superuser=True,
                is_blacklisted=False,
            )

        user_level = await AclChecker.get_user_level(
            user_id, bot_id, group_id
        )
        if user_level >= level:
            return PermissionResult(
                allowed=True,
                reason="",
                user_level=user_level,
                is_superuser=False,
                is_blacklisted=False,
            )

        return PermissionResult(
            allowed=False,
            reason=f"权限不足，需要等级{level}，当前{user_level}",
            user_level=user_level,
            is_superuser=False,
            is_blacklisted=False,
        )


acl_checker = AclChecker()
"""AI ACL 检查器单例"""
