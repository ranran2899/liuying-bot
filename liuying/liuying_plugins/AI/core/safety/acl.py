"""AI 权限检查器

封装流萤本体 ACL 体系（超级用户/UserPermLevel等级），
为 AI 插件与 WebUI 提供只读权限检查接口。

注意：本模块仅提供权限检查，不提供管理操作（ban/unban/授权等）。
用户/群组黑名单（拉黑/封禁）已由流萤本体插件统一接管：
- 事件级拦截: liuying.liuying_plugins.hooks.auth.auth_ban
- ban/unban/黑名单查询: liuying.liuying_plugins.admin.ban
- 管理员等级设置: liuying.liuying_plugins.admin.bot_perm
- 插件开关: liuying.liuying_plugins.admin.plugin_switch

权限层级：
1. 超级用户（bot.config.superusers） - 最高权限，绕过所有检查
2. 管理员（UserPermLevel.user_perm >= level） - 等级鉴权
3. 普通用户 - 默认权限
"""

from dataclasses import dataclass

from liuying.models._user import UserPermLevel

__all__ = ["AclChecker", "PermissionResult"]


@dataclass(slots=True)
class PermissionResult:
    """权限检查结果

    Attributes:
        allowed: 是否允许
        reason: 拒绝原因，允许时为空
        user_level: 用户等级
        is_superuser: 是否超级用户
    """

    allowed: bool
    reason: str = ""
    user_level: int = 0
    is_superuser: bool = False


class AclChecker:
    """AI 权限检查器

    封装超级用户/管理员等级只读权限检查能力，
    通过类变量共享管理员等级常量，所有方法均为静态方法。
    """

    ADMIN_LEVEL_BASIC: int = 5
    """基础管理员等级（可执行开关/查询命令）"""

    ADMIN_LEVEL_HIGH: int = 7
    """高级管理员等级（可执行黑名单管理/重置命令）"""

    ADMIN_LEVEL_SUPER: int = 10
    """超级管理员等级（仅超级用户可达）"""

    @staticmethod
    async def check_superuser(user_id: str) -> bool:
        """检查用户是否超级用户

        参数:
            user_id: 用户ID

        返回:
            bool: 是否超级用户
        """
        return UserPermLevel.is_superuser(str(user_id))

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
        return await UserPermLevel.get_level(user_id, bot_id, group_id)

    @staticmethod
    async def check_permission(
        user_id: str,
        level: int | None = None,
        *,
        bot_id: str | None = None,
        group_id: str | None = None,
    ) -> PermissionResult:
        """综合权限检查

        依次检查：超级用户 → 管理员等级。

        参数:
            user_id: 用户ID
            level: 需要的管理员等级，None时用基础管理员等级
            bot_id: 机器人ID
            group_id: 群组ID

        返回:
            PermissionResult: 权限检查结果
        """
        if level is None:
            level = AclChecker.ADMIN_LEVEL_BASIC

        is_super = await AclChecker.check_superuser(user_id)
        if is_super:
            return PermissionResult(
                allowed=True,
                user_level=AclChecker.ADMIN_LEVEL_SUPER,
                is_superuser=True,
            )

        user_level = await AclChecker.get_user_level(
            user_id, bot_id, group_id
        )
        if user_level >= level:
            return PermissionResult(
                allowed=True,
                user_level=user_level,
                is_superuser=False,
            )

        return PermissionResult(
            allowed=False,
            reason=f"权限不足，需要等级{level}，当前{user_level}",
            user_level=user_level,
            is_superuser=False,
        )
