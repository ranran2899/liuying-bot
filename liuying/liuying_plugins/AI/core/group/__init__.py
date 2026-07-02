"""群组智能

提供群组成员管理、社交分析、群风格画像、禁言状态、
同伴感知、复读跟随、热聊保护与画像服务。
"""

from .hot_chat import HotChatProtector, hot_chat_protector
from .members import (
    GroupMemberInfo,
    GroupMemberService,
    GroupMemberSnapshot,
    group_member_service,
)
from .mute import (
    get_group_mute_until,
    is_group_muted,
    refresh_bot_group_mute_state,
    set_group_mute_until,
    update_group_mute_from_notice,
)
from .peer_awareness import PeerAwareness, peer_awareness
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
    "GroupSocialService",
    "HotChatProtector",
    "PeerAwareness",
    "ProfileService",
    "RepeatContext",
    "RepeatFollow",
    "RepeatTracker",
    "build_group_style_prompt_block",
    "extract_group_knowledge",
    "extract_group_style",
    "get_group_mute_until",
    "group_member_service",
    "group_profile",
    "group_social",
    "hot_chat_protector",
    "is_group_muted",
    "peer_awareness",
    "profile_service",
    "refresh_bot_group_mute_state",
    "repeat_follow",
    "set_group_mute_until",
    "summarize_conversation",
    "update_group_mute_from_notice",
]
