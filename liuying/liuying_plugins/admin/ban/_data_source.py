import time
from typing import Literal

from nonebot_plugin_uninfo import Uninfo

from liuying.models._user import UserPermLevel
from liuying.models.ban_console import BanConsole
from liuying.utils.image import BuildRankMat
from liuying.utils.log import logger

# AI Agent 会话上下文：工具被 LLM 调用时由 AgentRunner 绑定当前
# 对话的用户/群组，智能工具据此确定操作者与作用群组。
# 仅在 AI 插件的智能模式下存在，普通命令路径不读取。
from liuying_plugins.AI.agent.runtime.session_context import (
    get_current_group_id,
    get_current_session,
)

# 智能工具所需管理员等级（与 ban 命令 admin_check(5) 保持一致）
_SMART_BAN_LEVEL = 5


def _is_ban_active(data: BanConsole) -> bool:
    """判断封禁记录是否仍然有效"""
    return data.duration < 0 or (data.ban_time + data.duration) > time.time()


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
            query = query.filter(user_id=user_id)
        elif group_id:
            query = query.filter(group_id=group_id)
        elif filter_type == "user":
            query = query.where_null("group_id")
        elif filter_type == "group":
            query = query.where_null("user_id")

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

        title = cls._build_title(filter_type, user_id, group_id)

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

    @staticmethod
    def _build_title(
        filter_type: Literal["group", "user"] | None,
        user_id: str | None,
        group_id: str | None,
    ) -> str:
        """构建Ban列表标题"""
        match (filter_type, user_id, group_id):
            case ("user", _, _):
                return "【用户 Ban 列表】"
            case ("group", _, _):
                return "【群组 Ban 列表】"
            case (_, uid, _) if uid:
                return f"【用户 {user_id} Ban 记录】"
            case (_, _, gid) if gid:
                return f"【群组 {group_id} Ban 记录】"
            case _:
                return "【Ban / UnBan 列表】"

    @classmethod
    async def is_ban(cls, user_id: str, group_id: str | None) -> bool:
        """判断用户是否被ban

        参数:
            user_id: 用户id
            group_id: 群组id

        返回:
            bool: 是否被ban
        """
        data = await BanConsole._get_data(user_id=user_id)
        if data:
            if _is_ban_active(data):
                return True
            await BanConsole.unban(user_id, None)

        if group_id:
            data = await BanConsole._get_data(user_id=user_id, group_id=group_id)
            if data:
                if _is_ban_active(data):
                    return True
                await BanConsole.unban(user_id, group_id)

            data = await BanConsole._get_data(user_id=None, group_id=group_id)
            if data:
                if _is_ban_active(data):
                    return True
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
        if is_group:
            user_id, group_id = None, target_id
        else:
            user_id = target_id
            group_id = session.group.id if session and session.group else None

        operator = session.user.id if session else "system"

        if existing := await BanConsole._get_data(user_id, group_id):
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

    @staticmethod
    async def _check_smart_operator() -> tuple[str, str]:
        """校验智能工具的调用者权限与上下文

        读取 AI Agent 会话上下文中的操作者与群组，
        校验操作者具备管理员等级或为超级用户。

        返回:
            tuple[str, str]: (操作者用户ID, 群组ID)

        异常:
            PermissionError: 缺少会话上下文或权限不足时抛出
        """
        session = get_current_session()
        if session is None:
            raise PermissionError("缺少会话上下文，无法确定操作者")
        operator = session.user.id
        if not operator:
            raise PermissionError("缺少会话上下文，无法确定操作者")
        if operator == session.self_id:
            raise PermissionError("操作者是机器人本体，禁止执行封禁操作")
        level = await UserPermLevel.get_level(operator)
        if level < _SMART_BAN_LEVEL:
            raise PermissionError(
                f"权限不足，封禁操作需要管理员等级{_SMART_BAN_LEVEL}以上"
            )
        group_id = session.scene.id if session.scene.is_group else ""
        return operator, group_id

    @classmethod
    async def smart_ban_user(
        cls, user_id: str, duration: int | None = None
    ) -> str:
        """智能模式封禁用户（admin.ban 插件的 AI 工具入口）

        由 AI Agent 智能调用，操作者与作用群组取自当前会话上下文，
        委托 BanManage.ban 写入 BanConsole。

        参数:
            user_id: 被封禁的用户ID
            duration: 封禁时长（分钟），None表示永久

        返回:
            str: 执行结果文本
        """
        target = (user_id or "").strip()
        if not target:
            return "请提供要封禁的用户ID"
        operator, _ = await cls._check_smart_operator()
        if target == operator:
            return "不能封禁自己"
        ban_time = duration if duration and int(duration) > 0 else -1
        try:
            await cls.ban(
                target,
                session=None,
                ban_level=1,
                duration=ban_time,
                is_group=False,
            )
        except Exception as e:
            logger.warning(
                f"智能封禁失败: operator={operator} target={target}: {e}",
                command="ban",
                e=e,
            )
            return f"封禁失败: {e}"
        duration_str = "永久" if ban_time < 0 else f"{ban_time}分钟"
        return f"已成功将用户 {target} 拉黑，时长: {duration_str}"

    @classmethod
    async def smart_unban_user(cls, user_id: str) -> str:
        """智能模式解禁用户（admin.ban 插件的 AI 工具入口）

        由 AI Agent 智能调用，操作者与作用群组取自当前会话上下文，
        解除用户在群内/全局的封禁记录。

        参数:
            user_id: 被解禁的用户ID

        返回:
            str: 执行结果文本
        """
        target = (user_id or "").strip()
        if not target:
            return "请提供要解禁的用户ID"
        await cls._check_smart_operator()
        try:
            ok, msg = await cls.unban(target, get_current_group_id(), session=None)
        except Exception as e:
            logger.warning(
                f"智能解禁失败: target={target}: {e}", command="ban", e=e
            )
            return f"解禁失败: {e}"
        return msg if ok else f"用户 {target} 未被封禁"
