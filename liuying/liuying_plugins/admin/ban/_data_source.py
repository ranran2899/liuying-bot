import time
from typing import Literal

from nonebot_plugin_uninfo import Uninfo

from liuying.models.ban_console import BanConsole
from liuying.utils.image import BuildRankMat
from liuying.utils.log import logger


class BanManage:
    @classmethod
    async def build_ban_image(
        cls,
        filter_type: Literal["group", "user"] | None,
        user_id: str | None = None,
        group_id: str | None = None,
    ) -> bytes | None:
        """构造Ban列表图片

        参数:
            filter_type: 过滤类型
            user_id: 用户id
            group_id: 群组id

        返回:
            bytes | None: 图片字节数据
        """
        query = BanConsole.filter()

        if user_id:
            query = query.filter(BanConsole.user_id == user_id)
        elif group_id:
            query = query.filter(BanConsole.group_id == group_id)
        elif filter_type == "user":
            query = query.filter(BanConsole.group_id.is_(None))
        elif filter_type == "group":
            query = query.filter(BanConsole.user_id.is_(None))

        data_list = await query.all()

        if not data_list:
            return None

        num = len(data_list)
        height = 120 + num * 45
        rank_mat = BuildRankMat(
            width=1000,
            height=height,
            font_size=18,
            colors={"background": "#F5F5F5", "header": "#2C3E50"},
        )

        user_ids = []
        data_values = []

        for data in data_list:
            if data.duration < 0:
                duration_str = "永久"
            else:
                remaining = int((data.ban_time + data.duration - time.time()) / 60)
                duration_str = f"{remaining}分钟" if remaining > 0 else "已过期"

            user_ids.append(str(data.id))
            data_values.append(
                [
                    data.user_id or "-",
                    data.group_id or "-",
                    str(data.ban_level),
                    duration_str,
                    data.operator,
                ]
            )

        match (filter_type, user_id, group_id):
            case ("user", _, _):
                title = "【用户 Ban 列表】"
            case ("group", _, _):
                title = "【群组 Ban 列表】"
            case (_, uid, _) if uid:
                title = f"【用户 {user_id} Ban 记录】"
            case (_, _, gid) if gid:
                title = f"【群组 {group_id} Ban 记录】"
            case _:
                title = "【Ban / UnBan 列表】"

        header_texts = [
            "#",
            "ID",
            "用户ID",
            "群组ID",
            "BAN LEVEL",
            "剩余时长(分钟)",
            "操作员",
        ]
        column_widths = [50, 60, 170, 170, 100, 150, 200]

        await rank_mat.generate_multi_rank(
            user_ids=user_ids,
            user_data_list=data_values,
            rank_name=title,
            header_texts=header_texts,
            column_widths=column_widths,
            num=num,
        )

        return rank_mat.pic2bytes()

    @classmethod
    async def is_ban(cls, user_id: str, group_id: str | None) -> bool:
        """判断用户是否被ban

        参数:
            user_id: 用户id
            group_id: 群组id

        返回:
            bool: 是否被ban
        """

        def _check_expired(data: BanConsole) -> bool:
            return data.duration < 0 or (data.ban_time + data.duration) > time.time()

        data = await BanConsole._get_data(user_id=user_id)
        if data and _check_expired(data):
            return True
        if data:
            await BanConsole.unban(user_id, None)

        if group_id:
            data = await BanConsole._get_data(user_id=user_id, group_id=group_id)
            if data and _check_expired(data):
                return True
            if data:
                await BanConsole.unban(user_id, group_id)

            data = await BanConsole._get_data(group_id=group_id)
            if data and _check_expired(data):
                return True
            if data:
                await BanConsole.unban(None, group_id)

        return False

    @classmethod
    async def ban(
        cls,
        target_id: str,
        session: Uninfo,
        ban_level: int = 1,
        duration: int = -1,
        is_group: bool = False,
    ) -> tuple[bool, str]:
        """ban目标用户或群组

        参数:
            target_id: 用户id或群组id
            session: Uninfo
            ban_level: ban等级
            duration: 时长，-1为永久
            is_group: 是否为群组

        返回:
            tuple[bool, str]: 是否成功，提示信息
        """
        user_id = None if is_group else target_id
        group_id = (
            target_id
            if is_group
            else (session.group.id if session.group else None)
            if session
            else None
        )
        operator = session.user.id if session else "system"

        existing = await BanConsole._get_data(user_id, group_id)

        if existing:
            existing.ban_level = ban_level
            existing.ban_time = int(time.time())
            existing.duration = duration
            existing.operator = operator
            await existing.save()
        else:
            await BanConsole.create(
                user_id=user_id,
                group_id=group_id,
                ban_level=ban_level,
                ban_time=int(time.time()),
                duration=duration,
                operator=operator,
            )

        target_type = "群组" if is_group else "用户"
        duration_str = "永久" if duration < 0 else f"{duration}分钟"
        logger.info(
            f"{operator} 对 {target_type} {target_id} 执行Ban操作，时长: {duration_str}"
        )

        return True, f"已成功将{target_type} {target_id} 拉黑，时长: {duration_str}"

    @classmethod
    async def unban(
        cls,
        user_id: str | None,
        group_id: str | None,
        session: Uninfo,
        idx: int | None = None,
        is_superuser: bool = False,
    ) -> tuple[bool, str]:
        """unban目标用户或群组

        参数:
            user_id: 用户id
            group_id: 群组id
            session: Uninfo
            idx: 指定id
            is_superuser: 是否为超级用户操作

        返回:
            tuple[bool, str]: 是否成功，提示信息
        """
        if idx is not None and is_superuser:
            data = await BanConsole.filter(id=idx).first()
        else:
            if not user_id and not group_id:
                return False, "请指定要解除的用户或群组"
            data = await BanConsole._get_data(user_id, group_id)

        if not data:
            return False, "未找到对应的封禁记录"

        await data.delete()

        operator = session.user.id if session else "system"
        target_type = "群组" if data.group_id and not data.user_id else "用户"
        target_id = data.user_id if data.user_id else data.group_id
        logger.info(f"{operator} 对 {target_type} {target_id} 执行Unban操作")

        return True, f"已成功将{target_type} {target_id} 从黑名单中移除"
