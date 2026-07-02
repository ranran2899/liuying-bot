"""群社交智能

整合群关系图谱、群成员角色识别、复读跟随决策。
作为AI插件社交智能的核心模块，为对话提供群级社交上下文。
复读检测逻辑委托给 RepeatTracker。
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
from typing import Any

from liuying.utils.log import logger

from ...models.group_context import GroupContextSnapshot
from .repeat_follow import RepeatTracker

_INTERACTION_WINDOW_HOURS = 24
"""互动统计时间窗口（小时）"""

_ROLE_UPDATE_INTERVAL_HOURS = 6
"""角色更新间隔（小时）"""

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


@dataclass(slots=True)
class UserRole:
    """用户角色

    Attributes:
        user_id: 用户ID
        role: 角色标签
        activity_score: 活跃度评分（0-1）
        influence_score: 影响力评分（0-1）
        last_update: 最后更新时间
    """

    user_id: str = ""
    role: str = "member"
    activity_score: float = 0.0
    influence_score: float = 0.0
    last_update: datetime | None = None


class GroupSocialService:
    """群社交智能服务

    维护群内用户互动统计与角色识别，
    复读检测委托给 RepeatTracker。
    提供群关系图谱与复读跟随决策。
    """

    def __init__(self) -> None:
        """初始化群社交服务"""
        self._interactions: dict[str, dict[str, UserInteraction]] = {}
        """群ID -> (用户ID -> 互动统计)"""
        self._roles: dict[str, dict[str, UserRole]] = {}
        """群ID -> (用户ID -> 角色)"""
        self._repeat_tracker = RepeatTracker()
        """复读追踪器"""
        self._last_role_update: dict[str, datetime] = {}
        """群ID -> 最后角色更新时间"""

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

        self._repeat_tracker.record(group_id, user_id, text)

    def should_follow_repeat(
        self,
        group_id: str,
        text: str,
        *,
        bot_user_id: str = "",
    ) -> tuple[bool, str]:
        """决策是否跟随复读

        参数:
            group_id: 群组ID
            text: 当前消息文本
            bot_user_id: 机器人用户ID

        返回:
            tuple[bool, str]: (是否跟随, 复读文本)
        """
        return self._repeat_tracker.should_follow(
            group_id, text, bot_user_id=bot_user_id
        )

    def get_user_role(
        self,
        group_id: str,
        user_id: str,
    ) -> UserRole:
        """获取用户角色

        参数:
            group_id: 群组ID
            user_id: 用户ID

        返回:
            UserRole: 用户角色
        """
        group_roles = self._roles.get(group_id, {})
        return group_roles.get(
            user_id,
            UserRole(
                user_id=user_id,
                last_update=datetime.now(),
            ),
        )

    async def update_roles(
        self, group_id: str
    ) -> dict[str, UserRole]:
        """更新群成员角色识别

        基于互动统计计算活跃度与影响力，分配角色标签。

        参数:
            group_id: 群组ID

        返回:
            dict[str, UserRole]: 用户ID -> 角色
        """
        last = self._last_role_update.get(group_id)
        if (
            last
            and (datetime.now() - last).total_seconds()
            < _ROLE_UPDATE_INTERVAL_HOURS * 3600
        ):
            return self._roles.get(group_id, {})

        interactions = self._interactions.get(group_id, {})
        if not interactions:
            return {}

        message_counts = [
            (uid, i.message_count)
            for uid, i in interactions.items()
        ]
        if not message_counts:
            return {}
        max_messages = max(c for _, c in message_counts) or 1

        cutoff = datetime.now() - timedelta(
            hours=_INTERACTION_WINDOW_HOURS
        )
        active_counts = {
            uid: (
                1 if i.last_active and i.last_active > cutoff else 0
            )
            for uid, i in interactions.items()
        }

        roles: dict[str, UserRole] = {}
        for uid, interaction in interactions.items():
            activity_score = (
                interaction.message_count / max_messages
            )
            influence_score = min(
                1.0,
                (
                    interaction.mentioned_count * 0.3
                    + interaction.reply_count * 0.1
                    + sum(
                        interaction.interacted_with.values()
                    )
                    * 0.05
                ),
            )

            role = "member"
            if (
                activity_score > 0.7
                and interaction.message_count >= 10
            ):
                role = "active"
            elif interaction.mentioned_count >= 5:
                role = "leader"
            elif (
                interaction.message_count <= 2
                and (
                    not interaction.last_active
                    or interaction.last_active < cutoff
                )
            ):
                role = "lurker"
            elif active_counts[uid] == 0:
                role = "inactive"

            roles[uid] = UserRole(
                user_id=uid,
                role=role,
                activity_score=round(activity_score, 3),
                influence_score=round(influence_score, 3),
                last_update=datetime.now(),
            )

        self._roles[group_id] = roles
        self._last_role_update[group_id] = datetime.now()
        return roles

    def get_relationship_summary(
        self,
        group_id: str,
        user_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
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

        参数:
            group_id: 群组ID
            user_id: 当前用户ID

        返回:
            str: prompt文本
        """
        roles = self._roles.get(group_id, {})
        if not roles:
            return ""

        parts: list[str] = ["\n\n[群社交上下文]"]

        active_users = [
            (uid, r)
            for uid, r in roles.items()
            if r.role in ("active", "leader")
        ][:5]
        if active_users:
            parts.append("活跃成员:")
            for uid, r in active_users:
                parts.append(
                    f"- {uid}（{r.role}, "
                    f"活跃度{r.activity_score:.2f}）"
                )

        if user_id:
            relationships = self.get_relationship_summary(
                group_id, user_id, limit=3
            )
            if relationships:
                parts.append(f"{user_id}的互动关系:")
                for rel in relationships:
                    parts.append(
                        f"- 与 {rel['target_id']} "
                        f"互动 {rel['interaction_count']} 次"
                    )

        return "\n".join(parts) if len(parts) > 1 else ""

    def prune_stale(self, days: int = 7) -> int:
        """清理过期的群社交数据

        参数:
            days: 保留天数

        返回:
            int: 清理的群组数
        """
        cutoff = datetime.now() - timedelta(days=days)
        pruned = 0
        for group_id in list(self._interactions.keys()):
            interactions = self._interactions[group_id]
            has_recent = any(
                i.last_active and i.last_active > cutoff
                for i in interactions.values()
            )
            if not has_recent:
                self._interactions.pop(group_id, None)
                self._roles.pop(group_id, None)
                self._repeat_tracker.prune_group(group_id)
                self._last_role_update.pop(group_id, None)
                pruned += 1
        return pruned

    async def persist_to_snapshot(
        self, group_id: str
    ) -> None:
        """持久化群社交数据到GroupContextSnapshot

        参数:
            group_id: 群组ID
        """
        try:
            roles = self._roles.get(group_id, {})
            if not roles:
                return
            snapshot = await GroupContextSnapshot.get_or_create(
                group_id
            )
            relationships = self.get_relationship_summary(
                group_id, limit=20
            )
            extra_data: dict[str, Any] = {
                "roles": {
                    uid: {
                        "role": r.role,
                        "activity": r.activity_score,
                        "influence": r.influence_score,
                    }
                    for uid, r in roles.items()
                },
                "relationships": relationships,
            }
            existing_extra: dict[str, Any] = {}
            try:
                existing_extra = json.loads(
                    snapshot.extra or "{}"
                )
            except (json.JSONDecodeError, TypeError):
                existing_extra = {}
            existing_extra["social"] = extra_data
            snapshot.extra = json.dumps(
                existing_extra, ensure_ascii=False
            )
            snapshot.last_activity_time = datetime.now()
            await snapshot.save(
                update_fields=["extra", "last_activity_time"]
            )
        except Exception as e:
            logger.debug(
                f"持久化群社交数据失败: {e}",
                command="AI",
                e=e,
            )


group_social = GroupSocialService()
"""群社交智能服务单例"""
