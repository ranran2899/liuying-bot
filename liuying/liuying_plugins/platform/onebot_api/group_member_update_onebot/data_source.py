from datetime import datetime
import re

import nonebot
from nonebot.adapters import Bot
from nonebot_plugin_uninfo import Member, SceneType, get_interface

from liuying.configs.config import Config
from liuying.models._group import GroupInfoUser
from liuying.models._user import UserPermLevel
from liuying.utils.log import logger
from liuying.utils.platform import PlatformUtils


class MemberUpdateManage:
    @classmethod
    async def _handle_user(
        cls,
        member: Member,
        db_user_map: dict[str, list[GroupInfoUser]],
        group_id: str,
        data_list: tuple[list, list, list],
        platform: str | None,
        default_auth: int | None,
    ):
        """处理单个成员信息更新

        参数:
            member: 成员对象
            db_user_map: 按user_id分组的数据库成员映射
            group_id: 群组id
            data_list: (新增列表, 更新列表, 删除列表)
            platform: 平台
            default_auth: 管理员默认权限等级
        """
        driver = nonebot.get_driver()
        nickname = re.sub(
            r"[\x00-\x09\x0b-\x1f\x7f-\x9f]", "", member.nick or member.user.name or ""
        )
        role = member.role

        if member.id in driver.config.superusers:
            await UserPermLevel.set_level(member.id, group_id, 9)
        elif role and default_auth:
            if role.id != "MEMBER" and not await UserPermLevel.is_group_flag(
                member.id, group_id
            ):
                level = default_auth + 1 if role.id == "OWNER" else default_auth
                await UserPermLevel.set_level(member.id, group_id, level)

        users = db_user_map.get(member.id, [])
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
                    user_id=member.id,
                    group_id=group_id,
                    user_name=nickname,
                    user_join_time=member.joined_at or datetime.now(),
                    platform=platform,
                )
            )

    @classmethod
    async def update_group_member(cls, bot: Bot, group_id: str) -> str:
        """更新群组成员信息

        参数:
            bot: Bot
            group_id: 群组id

        返回:
            str: 返回消息
        """
        if not group_id:
            logger.warning(f"bot: {bot.self_id}，group_id为空，无法更新群成员信息...")
            return "群组id为空..."

        if not (interface := get_interface(bot)):
            return "更新群组失败，无法获取接口..."

        scenes = await interface.get_scenes()
        platform = PlatformUtils.get_platform(bot)
        group_list = [s for s in scenes if s.is_group and s.id == group_id]
        if not group_list:
            logger.warning(
                f"bot: {bot.self_id}，group_id: {group_id}，群组不存在，"
                "无法更新群成员信息..."
            )
            return "更新群组失败，群组不存在..."

        members = await interface.get_members(SceneType.GROUP, group_list[0].id)
        db_user = await GroupInfoUser.filter(group_id=group_id).all()
        db_user_map: dict[str, list[GroupInfoUser]] = {}
        for u in db_user:
            db_user_map.setdefault(u.user_id, []).append(u)

        default_auth = Config.get_config("admin_watch", "ADMIN_DEFAULT_AUTH")
        data_list: tuple[list, list, list] = ([], [], [])
        exist_member_ids: set[str] = set()

        for member in members:
            logger.debug(f"即将更新群组成员: {member}", "更新群组成员信息")
            await cls._handle_user(
                member, db_user_map, group_id, data_list, platform, default_auth
            )
            exist_member_ids.add(member.id)

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
                platform=platform or "unknown",
            )

        return "群组成员信息更新完成!"
