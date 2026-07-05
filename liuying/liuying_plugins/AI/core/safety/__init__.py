"""安全与访问控制

提供权限校验、LLM 回复安全过滤、用户对话 token 额度管理。
"""

from .acl import AclChecker, PermissionResult, acl_checker
from .filter import SafetyFilter, SafetyRefusalError
from .token_quota import (
    QuotaCheckResult,
    TokenQuotaService,
    token_quota_service,
)

# 向后兼容别名：管理员等级常量指向 AclChecker 类变量
ADMIN_LEVEL_BASIC = AclChecker.ADMIN_LEVEL_BASIC
ADMIN_LEVEL_HIGH = AclChecker.ADMIN_LEVEL_HIGH
ADMIN_LEVEL_SUPER = AclChecker.ADMIN_LEVEL_SUPER

# 向后兼容别名：散落函数名指向 AclChecker 静态方法
check_admin = AclChecker.check_admin
check_blacklist = AclChecker.check_blacklist
check_permission = AclChecker.check_permission
check_superuser = AclChecker.check_superuser
get_user_level = AclChecker.get_user_level

__all__ = [
    "ADMIN_LEVEL_BASIC",
    "ADMIN_LEVEL_HIGH",
    "ADMIN_LEVEL_SUPER",
    "AclChecker",
    "PermissionResult",
    "QuotaCheckResult",
    "SafetyFilter",
    "SafetyRefusalError",
    "TokenQuotaService",
    "acl_checker",
    "check_admin",
    "check_blacklist",
    "check_permission",
    "check_superuser",
    "get_user_level",
    "token_quota_service",
]
