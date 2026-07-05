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

# 向后兼容别名：将散落函数名指向 GroupMuteTracker 静态方法
get_group_mute_until = GroupMuteTracker.get_group_mute_until
is_group_muted = GroupMuteTracker.is_group_muted
refresh_bot_group_mute_state = (
    GroupMuteTracker.refresh_bot_group_mute_state
)
set_group_mute_until = GroupMuteTracker.set_group_mute_until
update_group_mute_from_notice = (
    GroupMuteTracker.update_group_mute_from_notice
)

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
    "get_group_mute_until",
    "group_member_service",
    "group_mute_tracker",
    "group_profile",
    "group_social",
    "is_group_muted",
    "profile_service",
    "refresh_bot_group_mute_state",
    "repeat_follow",
    "set_group_mute_until",
    "summarize_conversation",
    "update_group_mute_from_notice",
]
