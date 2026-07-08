"""群组智能

提供群组成员管理、社交分析、群风格画像、禁言状态、
复读跟随与画像服务。
"""

from .members import (
    GroupMemberInfo,
    GroupMemberService,
    GroupMemberSnapshot,
    group_member_service,
)
from .mute import GroupMuteTracker, group_mute_tracker
from .profile import (
    build_group_style_prompt_block,
    extract_group_knowledge,
    extract_group_style,
    group_profile,
    summarize_conversation,
)
from .profile_service import ProfileService, profile_service
from .repeat_follow import (
    RepeatContext,
    RepeatFollow,
    RepeatTracker,
    repeat_follow,
)
from .social import GroupSocialService, group_social

__all__ = [
    "GroupMemberInfo",
    "GroupMemberService",
    "GroupMemberSnapshot",
    "GroupMuteTracker",
    "GroupSocialService",
    "ProfileService",
    "RepeatContext",
    "RepeatFollow",
    "RepeatTracker",
    "build_group_style_prompt_block",
    "extract_group_knowledge",
    "extract_group_style",
    "group_member_service",
    "group_mute_tracker",
    "group_profile",
    "group_social",
    "profile_service",
    "repeat_follow",
    "summarize_conversation",
]
