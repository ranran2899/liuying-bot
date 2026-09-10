"""群成员获取集成

完全基于 GroupInfoUser 数据库获取群成员信息（由本体定期更新）：
- 提供群成员列表/单成员信息/名称模糊查找等接口
- 群成员列表快照带本地缓存，避免频繁查库
- 注册为Agent工具供AI调用
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from liuying.models._group import GroupInfoUser
from liuying.services.cache import CacheDict
from liuying.utils.platform import PlatformUtils

_CACHE_TTL_SECONDS = 300
"""群成员列表缓存TTL（秒），与本体5分钟更新周期对齐"""

_MAX_CACHE_GROUPS = 50
"""最大缓存群组数"""

_MAX_LIST_MEMBERS = 500
"""单次加载成员列表上限"""


@dataclass(slots=True)
class GroupMemberInfo:
    """群成员信息

    Attributes:
        user_id: 用户ID
        user_name: 用户昵称
        user_nickname: 自定义用户名称（一般为用户在群内的备注）
        group_id: 群组ID
        role: 角色（owner/admin/member）
        user_bot: 是否为机器人
        uid: 用户uid
        avatar_url: 头像URL
        join_time: 入群时间
        platform: 平台
    """

    user_id: str = ""
    user_name: str = ""
    user_nickname: str = ""
    group_id: str = ""
    role: str = "member"
    user_bot: bool | None = None
    uid: int | None = None
    avatar_url: str = ""
    join_time: datetime | None = None
    platform: str = ""

    def display_name(self) -> str:
        """获取显示名称（自定义名称 > 用户昵称 > 用户ID）

        返回:
            str: 显示名称
        """
        return self.user_nickname or self.user_name or self.user_id

    def to_brief(self) -> dict[str, Any]:
        """导出简要信息

        返回:
            dict: 简要信息字典
        """
        return {
            "user_id": self.user_id,
            "name": self.display_name(),
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
                "user_name": self.user_name,
                "user_nickname": self.user_nickname,
                "group_id": self.group_id,
                "user_bot": self.user_bot,
                "uid": self.uid,
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
        members: 成员列表（最多加载500条）
        total: 成员总数（COUNT聚合的真实总数，可能大于列表长度）
        update_time: 快照时间
    """

    group_id: str = ""
    members: list[GroupMemberInfo] = field(default_factory=list)
    total: int = 0
    update_time: datetime | None = None


class GroupMemberService:
    """群成员服务

    完全基于 GroupInfoUser 数据库（由本体定期更新），
    提供群成员查询、缓存与统计能力。
    """

    @staticmethod
    def _db_row_to_member(m: GroupInfoUser) -> GroupMemberInfo:
        """将 GroupInfoUser 转为 GroupMemberInfo

        参数:
            m: GroupInfoUser 实例

        返回:
            GroupMemberInfo: 群成员信息
        """
        platform = m.platform or ""
        return GroupMemberInfo(
            user_id=m.user_id,
            user_name=m.user_name,
            user_nickname=m.user_nickname,
            group_id=m.group_id,
            role=m.user_role or "member",
            user_bot=m.user_bot,
            uid=m.uid,
            avatar_url=(
                PlatformUtils.get_user_avatar_url(m.user_id, platform) or ""
            ),
            join_time=m.user_join_time,
            platform=platform,
        )

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

    async def get_members(
        self, group_id: str, *, use_cache: bool = True
    ) -> GroupMemberSnapshot:
        """从数据库获取群成员（带缓存）

        members 列表最多加载 _MAX_LIST_MEMBERS 条，
        total 使用 COUNT 聚合取真实总数，
        大群不再恒报列表上限值。

        参数:
            group_id: 群组ID
            use_cache: 是否使用缓存

        返回:
            GroupMemberSnapshot: 群成员快照
        """
        if use_cache:
            cached = self._cache_get(group_id)
            if cached is not None:
                return cached

        base_query = GroupInfoUser.filter(group_id=group_id)
        total = await base_query.count()
        members_data = await base_query.limit(
            _MAX_LIST_MEMBERS
        ).all()
        members = [
            GroupMemberService._db_row_to_member(m) for m in members_data
        ]
        snapshot = GroupMemberSnapshot(
            group_id=group_id,
            members=members,
            total=total,
            update_time=datetime.now(),
        )
        if snapshot.total > 0:
            self._cache_set(group_id, snapshot)
        return snapshot

    async def get_member(
        self, group_id: str, user_id: str
    ) -> GroupMemberInfo | None:
        """从数据库获取单个群成员信息

        参数:
            group_id: 群组ID
            user_id: 用户ID

        返回:
            GroupMemberInfo | None: 成员信息或None
        """
        if user := await GroupInfoUser.filter(
            user_id=user_id, group_id=group_id
        ).first():
            return GroupMemberService._db_row_to_member(user)
        return None

    async def find_members_by_name(
        self,
        group_id: str,
        name: str,
        limit: int = 10,
    ) -> list[GroupMemberInfo]:
        """按名称模糊查找群成员（匹配自定义名称/用户昵称/用户ID）

        参数:
            group_id: 群组ID
            name: 名称关键词
            limit: 返回上限

        返回:
            list[GroupMemberInfo]: 匹配的成员列表
        """
        if not name:
            return []
        cond = (
            GroupInfoUser.user_nickname.icontains(name)
            | GroupInfoUser.user_name.icontains(name)
            | GroupInfoUser.user_id.contains(name)
        )
        rows = await GroupInfoUser.filter(
            GroupInfoUser.group_id == group_id, cond
        ).limit(limit).all()
        return [
            GroupMemberService._db_row_to_member(m) for m in rows
        ]


group_member_service = GroupMemberService()
"""群成员服务单例"""
