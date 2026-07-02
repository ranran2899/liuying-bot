"""群成员获取集成

深度整合流萤本体群成员能力：
- 优先使用 GroupInfoUser 数据库缓存（每5分钟由本体自动更新）
- 回退到 PlatformUtils.get_group_member_list 实时获取
- 提供群成员列表/单成员信息/在线检查/昵称查询等接口
- 注册为Agent工具供AI调用
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from liuying.models._group import GroupInfoUser
from liuying.services.cache import CacheDict
from liuying.utils.log import logger
from liuying.utils.platform import PlatformUtils, UserData

_CACHE_TTL_SECONDS = 300
"""群成员列表缓存TTL（秒），与本体5分钟更新周期对齐"""

_MAX_CACHE_GROUPS = 50
"""最大缓存群组数"""


@dataclass(slots=True)
class GroupMemberInfo:
    """群成员信息

    Attributes:
        user_id: 用户ID
        nickname: 群昵称
        username: 用户名
        group_id: 群组ID
        role: 角色（owner/admin/member）
        avatar_url: 头像URL
        join_time: 入群时间
        platform: 平台
    """

    user_id: str = ""
    nickname: str = ""
    username: str = ""
    group_id: str = ""
    role: str = "member"
    avatar_url: str = ""
    join_time: datetime | None = None
    platform: str = ""

    def to_brief(self) -> dict[str, Any]:
        """导出简要信息

        返回:
            dict: 简要信息字典
        """
        return {
            "user_id": self.user_id,
            "nickname": self.nickname or self.username,
            "role": self.role,
        }

    def to_full(self) -> dict[str, Any]:
        """导出完整信息

        返回:
            dict: 完整信息字典
        """
        brief = self.to_brief()
        brief.update(
            {
                "username": self.username,
                "group_id": self.group_id,
                "avatar_url": self.avatar_url,
                "join_time": (
                    self.join_time.strftime("%Y-%m-%d %H:%M")
                    if self.join_time
                    else ""
                ),
                "platform": self.platform,
            }
        )
        return brief


@dataclass(slots=True)
class GroupMemberSnapshot:
    """群成员快照

    Attributes:
        group_id: 群组ID
        members: 成员列表
        total: 成员总数
        update_time: 快照时间
        source: 数据来源（db/realtime）
    """

    group_id: str = ""
    members: list[GroupMemberInfo] = field(default_factory=list)
    total: int = 0
    update_time: datetime | None = None
    source: str = "db"


def _user_data_to_member(
    user: UserData, group_id: str
) -> GroupMemberInfo:
    """将 UserData 转为 GroupMemberInfo

    参数:
        user: UserData 实例
        group_id: 群组ID

    返回:
        GroupMemberInfo: 群成员信息
    """
    return GroupMemberInfo(
        user_id=str(getattr(user, "user_id", "") or ""),
        nickname=getattr(user, "card", "") or getattr(user, "name", ""),
        username=getattr(user, "name", ""),
        group_id=group_id,
        role=getattr(user, "role", "member") or "member",
        avatar_url=getattr(user, "avatar_url", "") or "",
        join_time=getattr(user, "join_time", None),
        platform="",
    )


class GroupMemberService:
    """群成员服务

    整合 GroupInfoUser 数据库与 PlatformUtils 实时接口，
    提供群成员查询、缓存与统计能力。
    """

    def __init__(self) -> None:
        """初始化群成员服务"""
        self._cache = CacheDict(
            "AI_GROUP_MEMBERS",
            expire=_CACHE_TTL_SECONDS,
            max_size=_MAX_CACHE_GROUPS,
        )
        """群成员快照缓存：group_id -> snapshot（300秒TTL，最多50个群）"""

    def _cache_get(
        self, group_id: str
    ) -> GroupMemberSnapshot | None:
        """从缓存获取

        参数:
            group_id: 群组ID

        返回:
            GroupMemberSnapshot | None: 快照或None
        """
        return self._cache.get(group_id)

    def _cache_set(
        self, group_id: str, snapshot: GroupMemberSnapshot
    ) -> None:
        """设置缓存

        参数:
            group_id: 群组ID
            snapshot: 快照
        """
        self._cache.set(group_id, snapshot)

    def invalidate_cache(self, group_id: str | None = None) -> None:
        """清空缓存

        参数:
            group_id: 指定群组ID，None时清空全部
        """
        if group_id is None:
            self._cache.clear()
        else:
            self._cache.pop(group_id, None)

    async def get_members_from_db(
        self, group_id: str
    ) -> GroupMemberSnapshot:
        """从数据库（GroupInfoUser）获取群成员

        参数:
            group_id: 群组ID

        返回:
            GroupMemberSnapshot: 群成员快照
        """
        try:
            members_data = await GroupInfoUser.filter(
                group_id=group_id
            ).limit(500).all()
            members: list[GroupMemberInfo] = []
            for m in members_data:
                members.append(
                    GroupMemberInfo(
                        user_id=m.user_id,
                        nickname=m.nickname or m.user_name,
                        username=m.user_name,
                        group_id=group_id,
                        role="member",
                        platform=m.platform or "",
                        join_time=m.user_join_time,
                    )
                )
            return GroupMemberSnapshot(
                group_id=group_id,
                members=members,
                total=len(members),
                update_time=datetime.now(),
                source="db",
            )
        except Exception as e:
            logger.debug(
                f"从数据库获取群成员失败: {e}",
                command="AI",
                e=e,
            )
            return GroupMemberSnapshot(
                group_id=group_id, source="db"
            )

    async def get_members_realtime(
        self, bot: Any, group_id: str
    ) -> GroupMemberSnapshot:
        """实时获取群成员（通过 PlatformUtils）

        参数:
            bot: Bot对象
            group_id: 群组ID

        返回:
            GroupMemberSnapshot: 群成员快照
        """
        try:
            users = await PlatformUtils.get_group_member_list(
                bot, group_id
            )
            members: list[GroupMemberInfo] = [
                _user_data_to_member(u, group_id) for u in users
            ]
            snapshot = GroupMemberSnapshot(
                group_id=group_id,
                members=members,
                total=len(members),
                update_time=datetime.now(),
                source="realtime",
            )
            return snapshot
        except Exception as e:
            logger.debug(
                f"实时获取群成员失败: {e}",
                command="AI",
                e=e,
            )
            return GroupMemberSnapshot(
                group_id=group_id, source="realtime"
            )

    async def get_members(
        self,
        group_id: str,
        bot: Any = None,
        *,
        use_cache: bool = True,
        prefer_realtime: bool = False,
    ) -> GroupMemberSnapshot:
        """获取群成员（优先缓存，回退到数据库，再回退到实时）

        参数:
            group_id: 群组ID
            bot: Bot对象（提供时支持实时获取）
            use_cache: 是否使用缓存
            prefer_realtime: 是否优先实时获取

        返回:
            GroupMemberSnapshot: 群成员快照
        """
        if use_cache:
            cached = self._cache_get(group_id)
            if cached is not None:
                return cached

        if prefer_realtime and bot is not None:
            snapshot = await self.get_members_realtime(
                bot, group_id
            )
            if snapshot.total > 0:
                self._cache_set(group_id, snapshot)
                return snapshot

        snapshot = await self.get_members_from_db(group_id)
        if snapshot.total == 0 and bot is not None:
            realtime = await self.get_members_realtime(
                bot, group_id
            )
            if realtime.total > 0:
                self._cache_set(group_id, realtime)
                return realtime

        if snapshot.total > 0:
            self._cache_set(group_id, snapshot)
        return snapshot

    async def get_member(
        self,
        group_id: str,
        user_id: str,
        bot: Any = None,
    ) -> GroupMemberInfo | None:
        """获取单个群成员信息

        参数:
            group_id: 群组ID
            user_id: 用户ID
            bot: Bot对象

        返回:
            GroupMemberInfo | None: 成员信息或None
        """
        snapshot = await self.get_members(group_id, bot=bot)
        for m in snapshot.members:
            if m.user_id == user_id:
                return m

        if bot is not None:
            try:
                user = await PlatformUtils.get_user(
                    bot, user_id, group_id=group_id
                )
                if user:
                    return _user_data_to_member(user, group_id)
            except Exception as e:
                logger.debug(
                    f"获取单个群成员失败: {e}",
                    command="AI",
                    e=e,
                )
        return None

    async def is_member(
        self,
        group_id: str,
        user_id: str,
        bot: Any = None,
    ) -> bool:
        """检查用户是否为群成员

        参数:
            group_id: 群组ID
            user_id: 用户ID
            bot: Bot对象

        返回:
            bool: 是否为群成员
        """
        snapshot = await self.get_members(group_id, bot=bot)
        return any(
            m.user_id == user_id for m in snapshot.members
        )

    async def get_member_nickname(
        self,
        group_id: str,
        user_id: str,
        bot: Any = None,
    ) -> str:
        """获取群成员昵称

        参数:
            group_id: 群组ID
            user_id: 用户ID
            bot: Bot对象

        返回:
            str: 昵称（无则返回空串）
        """
        try:
            nickname = await GroupInfoUser.get_user_nickname(
                user_id, group_id
            )
            if nickname:
                return nickname
        except Exception as e:
            logger.debug(
                f"获取群成员昵称失败: {e}",
                command="AI",
                e=e,
            )

        member = await self.get_member(
            group_id, user_id, bot=bot
        )
        if member:
            return member.nickname or member.username
        return ""

    async def get_group_stats(
        self,
        group_id: str,
        bot: Any = None,
    ) -> dict[str, Any]:
        """获取群成员统计

        参数:
            group_id: 群组ID
            bot: Bot对象

        返回:
            dict: 统计字典（含total/admin_count/owner等）
        """
        snapshot = await self.get_members(group_id, bot=bot)
        admin_count = sum(
            1 for m in snapshot.members if m.role == "admin"
        )
        owner_count = sum(
            1 for m in snapshot.members if m.role == "owner"
        )
        return {
            "group_id": group_id,
            "total": snapshot.total,
            "admin_count": admin_count,
            "owner_count": owner_count,
            "member_count": snapshot.total
            - admin_count
            - owner_count,
            "source": snapshot.source,
            "update_time": (
                snapshot.update_time.strftime("%Y-%m-%d %H:%M")
                if snapshot.update_time
                else ""
            ),
        }

    async def find_members_by_name(
        self,
        group_id: str,
        name: str,
        bot: Any = None,
        limit: int = 10,
    ) -> list[GroupMemberInfo]:
        """按名称模糊查找群成员

        参数:
            group_id: 群组ID
            name: 名称关键词
            bot: Bot对象
            limit: 返回上限

        返回:
            list[GroupMemberInfo]: 匹配的成员列表
        """
        if not name:
            return []
        snapshot = await self.get_members(group_id, bot=bot)
        name_lower = name.lower()
        results: list[GroupMemberInfo] = []
        for m in snapshot.members:
            if (
                name_lower in (m.nickname or "").lower()
                or name_lower in (m.username or "").lower()
                or name_lower in m.user_id.lower()
            ):
                results.append(m)
                if len(results) >= limit:
                    break
        return results


group_member_service = GroupMemberService()
"""群成员服务单例"""
