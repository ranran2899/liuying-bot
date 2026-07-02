"""安全与访问控制

提供权限校验、LLM 回复安全过滤、独立内容审核、
用户对话 token 额度管理、交叉验证与响应审查。
"""

from .acl import (
    ADMIN_LEVEL_BASIC,
    ADMIN_LEVEL_HIGH,
    ADMIN_LEVEL_SUPER,
    PermissionResult,
    check_admin,
    check_blacklist,
    check_permission,
    check_superuser,
    get_user_level,
)
from .cross_verify import CrossVerifier, cross_verifier
from .filter import (
    SafetyRefusalError,
    build_prompt_injection_guard,
    detect_api_block,
    detect_refusal,
    sanitize_or_retry,
)
from .moderation import ContentModerator, content_moderator
from .response_review import (
    ResponseReviewer,
    ReviewResult,
    response_reviewer,
)
from .token_quota import (
    QuotaCheckResult,
    TokenQuotaService,
    token_quota_service,
)

__all__ = [
    "ADMIN_LEVEL_BASIC",
    "ADMIN_LEVEL_HIGH",
    "ADMIN_LEVEL_SUPER",
    "ContentModerator",
    "CrossVerifier",
    "PermissionResult",
    "QuotaCheckResult",
    "ResponseReviewer",
    "ReviewResult",
    "SafetyRefusalError",
    "TokenQuotaService",
    "build_prompt_injection_guard",
    "check_admin",
    "check_blacklist",
    "check_permission",
    "check_superuser",
    "content_moderator",
    "cross_verifier",
    "detect_api_block",
    "detect_refusal",
    "get_user_level",
    "response_reviewer",
    "sanitize_or_retry",
    "token_quota_service",
]
