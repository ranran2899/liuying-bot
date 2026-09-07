"""群社交智能

基于实时互动统计构建群级社交上下文：
记录群消息中的回复与@关系，为对话注入当前用户的主要互动关系。
"""

from dataclasses import dataclass, field
from datetime import datetime

_MAX_TRACKED_USERS = 100
"""单群最大跟踪用户数"""


@dataclass(slots=True)
class UserInteraction:
    """用户互动统计

    Attributes:
        user_id: 用户ID
        message_count: 消息数
        reply_count: 回复他人次数
        mentioned_count: 被@次数
        mention_others_count: @他人次数
        last_active: 最后活跃时间
        interacted_with: 互动对象计数
    """

    user_id: str = ""
    message_count: int = 0
    reply_count: int = 0
    mentioned_count: int = 0
    mention_others_count: int = 0
    last_active: datetime | None = None
    interacted_with: dict[str, int] = field(default_factory=dict)


class GroupSocialService:
    """群社交智能服务

    维护群内用户互动统计，提供群关系摘要与社交上下文prompt块。
    """

    def __init__(self) -> None:
        """初始化群社交服务"""
        self._interactions: dict[str, dict[str, UserInteraction]] = {}
        """群ID -> (用户ID -> 互动统计)"""

    def record_message(
        self,
        group_id: str,
        user_id: str,
        text: str,
        *,
        reply_to: str | None = None,
        mentioned_users: list[str] | None = None,
    ) -> None:
        """记录一条群消息

        参数:
            group_id: 群组ID
            user_id: 用户ID
            text: 消息文本
            reply_to: 回复目标用户ID
            mentioned_users: 被@的用户列表
        """
        if not group_id or not user_id:
            return

        group_interactions = self._interactions.setdefault(
            group_id, {}
        )
        if (
            len(group_interactions) >= _MAX_TRACKED_USERS
            and user_id not in group_interactions
        ):
            return

        interaction = group_interactions.setdefault(
            user_id, UserInteraction(user_id=user_id)
        )
        interaction.message_count += 1
        interaction.last_active = datetime.now()

        if reply_to:
            interaction.reply_count += 1
            interaction.interacted_with[reply_to] = (
                interaction.interacted_with.get(reply_to, 0) + 1
            )

        if mentioned_users:
            interaction.mention_others_count += len(
                mentioned_users
            )
            for mentioned_id in mentioned_users:
                if mentioned_id == user_id:
                    continue
                mentioned = group_interactions.setdefault(
                    mentioned_id,
                    UserInteraction(user_id=mentioned_id),
                )
                mentioned.mentioned_count += 1
                mentioned.interacted_with[user_id] = (
                    mentioned.interacted_with.get(user_id, 0) + 1
                )

    def get_relationship_summary(
        self,
        group_id: str,
        user_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """获取群关系摘要

        参数:
            group_id: 群组ID
            user_id: 指定用户ID，None时返回群级关系
            limit: 返回上限

        返回:
            list[dict]: 关系列表
        """
        interactions = self._interactions.get(group_id, {})
        if not interactions:
            return []

        if user_id:
            interaction = interactions.get(user_id)
            if not interaction:
                return []
            sorted_pairs = sorted(
                interaction.interacted_with.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:limit]
            return [
                {
                    "user_id": user_id,
                    "target_id": target_id,
                    "interaction_count": count,
                }
                for target_id, count in sorted_pairs
            ]

        edge_counter: dict[tuple[str, str], int] = {}
        for uid, interaction in interactions.items():
            for target_id, count in interaction.interacted_with.items():
                key = tuple(sorted([uid, target_id]))
                edge_counter[key] = (
                    edge_counter.get(key, 0) + count
                )
        sorted_edges = sorted(
            edge_counter.items(), key=lambda x: x[1], reverse=True
        )[:limit]
        return [
            {
                "user_a": pair[0],
                "user_b": pair[1],
                "interaction_count": count,
            }
            for pair, count in sorted_edges
        ]

    def build_social_prompt_block(
        self,
        group_id: str,
        user_id: str | None = None,
    ) -> str:
        """构建群社交上下文prompt块

        基于实时互动统计输出当前用户的主要互动关系，
        帮助AI理解群内人物关系。

        参数:
            group_id: 群组ID
            user_id: 当前用户ID

        返回:
            str: prompt文本，无互动数据时返回空串
        """
        if not user_id:
            return ""
        relationships = self.get_relationship_summary(
            group_id, user_id, limit=3
        )
        if not relationships:
            return ""
        parts = [
            "\n\n[群社交上下文]",
            f"{user_id}的互动关系:",
        ]
        for rel in relationships:
            parts.append(
                f"- 与 {rel['target_id']} "
                f"互动 {rel['interaction_count']} 次"
            )
        return "\n".join(parts)


group_social = GroupSocialService()
"""群社交智能服务单例"""
