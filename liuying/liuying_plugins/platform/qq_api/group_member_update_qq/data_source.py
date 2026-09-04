"""QQ官方适配器群成员信息更新

适配器未封装群成员API,直接调用QQ开放平台接口实现:
- GET /v2/groups/{group_openid}/members 获取群成员列表(分页,单页最多30条)
- GET /v2/groups/{group_openid}/members/{member_openid} 获取群成员信息
该能力为内邀接口,未开通权限时平台返回错误码11253(应用无接口访问权限)
"""

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any

from nonebot.adapters import Bot
from nonebot.drivers import Request

from liuying.configs.config import Config
from liuying.models._group import GroupInfoUser
from liuying.models._user import UserPermLevel
from liuying.utils.log import logger


@dataclass(slots=True)
class QQGroupMember:
    """QQ开放平台群成员信息"""

    member_openid: str
    username: str = ""
    member_role: str = "member"
    bot: bool = False
    joined_at: datetime | None = None
    union_openid: str = ""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "QQGroupMember":
        """从接口响应解析成员信息

        参数:
            data: 接口返回的成员字典

        返回:
            QQGroupMember: 成员信息对象
        """
        joined_at = data.get("joined_at")
        return cls(
            member_openid=data["member_openid"],
            username=data.get("username") or "",
            member_role=data.get("member_role") or "member",
            bot=bool(data.get("bot")),
            joined_at=(
                # 去掉时区信息,与数据库DateTime字段保持一致
                datetime.fromisoformat(joined_at).replace(tzinfo=None)
                if joined_at
                else None
            ),
            union_openid=data.get("union_openid") or "",
        )


class MemberUpdateManage:
    """QQ官方群成员信息更新管理"""

    @classmethod
    async def _get(cls, bot: Bot, path: str, params: dict[str, str] | None = None):
        """调用QQ开放平台GET接口

        复用适配器的请求管道,自动携带QQBot鉴权头并处理token过期刷新

        参数:
            bot: Bot实例
            path: 接口路径(相对api_base)
            params: 查询参数

        返回:
            Any: 接口响应解析结果
        """
        request = Request(
            "GET",
            bot.adapter.get_api_base().joinpath(path),
            params=params,
        )
        return await bot._request(request)

    @classmethod
    async def get_group_members(
        cls, bot: Bot, group_openid: str
    ) -> list[QQGroupMember]:
        """获取群成员列表,自动翻页

        参数:
            bot: Bot实例
            group_openid: 群openid

        返回:
            list[QQGroupMember]: 群成员列表
        """
        members: list[QQGroupMember] = []
        cursor = ""
        while True:
            data = await cls._get(
                bot,
                f"v2/groups/{group_openid}/members",
                {"cursor": cursor} if cursor else None,
            )
            members.extend(
                QQGroupMember.from_api(item) for item in data.get("members", [])
            )
            cursor = data.get("next_cursor") or ""
            if not cursor:
                return members

    @classmethod
    async def get_group_member_info(
        cls, bot: Bot, group_openid: str, member_openid: str
    ) -> QQGroupMember:
        """获取单个群成员信息

        参数:
            bot: Bot实例
            group_openid: 群openid
            member_openid: 成员openid

        返回:
            QQGroupMember: 成员信息对象
        """
        data = await cls._get(
            bot, f"v2/groups/{group_openid}/members/{member_openid}"
        )
        return QQGroupMember.from_api(data)

    @classmethod
    async def update_group_member(cls, bot: Bot, group_id: str) -> str:
        """更新群组成员信息

        参数:
            bot: Bot实例
            group_id: 群openid

        返回:
            str: 返回消息
        """
        if not group_id:
            logger.warning(f"bot: {bot.self_id}，group_id为空，无法更新群成员信息...")
            return "群组id为空..."

        # 外部HTTP接口调用,失败时降级返回提示
        try:
            members = await cls.get_group_members(bot, group_id)
        except Exception as e:
            logger.error(
                "获取群成员列表失败",
                "更新群组成员信息",
                target=group_id,
                e=e,
            )
            return "更新群组失败，获取群成员列表失败..."

        platform = "qq"
        db_user = await GroupInfoUser.filter(group_id=group_id).all()
        db_user_map: dict[str, list[GroupInfoUser]] = {}
        for u in db_user:
            db_user_map.setdefault(u.user_id, []).append(u)

        default_auth = Config.get_config("admin_watch", "ADMIN_DEFAULT_AUTH")
        data_list: tuple[list, list, list] = ([], [], [])
        exist_member_ids: set[str] = set()

        for member in members:
            nickname = re.sub(
                r"[\x00-\x09\x0b-\x1f\x7f-\x9f]", "", member.username
            )
            if member.member_role in ("owner", "admin") and default_auth:
                if not await UserPermLevel.is_group_flag(
                    member.member_openid, group_id
                ):
                    level = (
                        default_auth + 1
                        if member.member_role == "owner"
                        else default_auth
                    )
                    await UserPermLevel.set_level(
                        member.member_openid, group_id, level
                    )

            users = db_user_map.get(member.member_openid, [])
            if users:
                if len(users) > 1:
                    for u in users[1:]:
                        data_list[2].append(u.id)
                if nickname != users[0].user_name:
                    users[0].user_name = nickname
                    data_list[1].append(users[0])
            else:
                data_list[0].append(
                    GroupInfoUser(
                        user_id=member.member_openid,
                        group_id=group_id,
                        user_name=nickname,
                        user_role=member.member_role,
                        user_bot=member.bot,
                        user_identifier=member.union_openid,
                        user_join_time=member.joined_at or datetime.now(),
                        platform=platform,
                    )
                )
            exist_member_ids.add(member.member_openid)

        if data_list[0]:
            await GroupInfoUser.filter().bulk_create(data_list[0])
            logger.debug(
                f"创建用户数据 {len(data_list[0])} 条",
                "更新群组成员信息",
                target=group_id,
            )
        if data_list[1]:
            await GroupInfoUser.batch_update_user_name(data_list[1])
            logger.debug(
                f"更新用户数据 {len(data_list[1])} 条",
                "更新群组成员信息",
                target=group_id,
            )
        if data_list[2]:
            await GroupInfoUser.delete_by_ids(data_list[2])
            logger.debug(f"删除重复数据 Ids: {data_list[2]}", "更新群组成员信息")

        if delete_member_list := [
            uid for uid in db_user_map if uid not in exist_member_ids
        ]:
            await GroupInfoUser.delete_members(delete_member_list, group_id)
            logger.info(
                f"删除已退群用户 {len(delete_member_list)} 条",
                "更新群组成员信息",
                group_id=group_id,
                platform=platform,
            )

        return "群组成员信息更新完成!"
