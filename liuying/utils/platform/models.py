from nonebot_plugin_uninfo.model import Member, User
from pydantic import BaseModel


class UserData(BaseModel):
    name: str
    """昵称"""
    card: str | None = None
    """名片/备注"""
    user_id: str
    """用户id"""
    group_id: str | None = None
    """群组id"""
    channel_id: str | None = None
    """频道id"""
    role: str | None = None
    """角色"""
    avatar_url: str | None = None
    """头像url"""
    join_time: int | None = None
    """加入时间"""


def build_user_data(
    user: User,
    member: Member | None,
    *,
    group_id: str | None = None,
    channel_id: str | None = None,
) -> UserData:
    """从 uniseg 的 user/member 构造统一的 UserData

    参数:
        user: 用户信息
        member: 成员信息（群/频道场景时存在）
        group_id: 群组id
        channel_id: 频道id

    返回:
        UserData: 统一的用户数据
    """
    return UserData(
        name=user.name or "",
        card=member.nick if member else None,
        user_id=user.id,
        group_id=group_id,
        channel_id=channel_id,
        role=member.role.id if member and member.role else None,
        join_time=(
            int(member.joined_at.timestamp())
            if member and member.joined_at
            else None
        ),
    )
