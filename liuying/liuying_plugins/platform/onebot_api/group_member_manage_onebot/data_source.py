from nonebot.adapters import Bot

from liuying.utils.log import logger

_ADMIN_ROLES = frozenset({"admin", "owner"})


async def _check_bot_admin(bot: Bot, group_id: str, action: str) -> str | None:
    """检查bot是否有管理员权限

    参数:
        bot: Bot实例
        group_id: 群组ID
        action: 操作名称，用于提示信息

    返回:
        str | None: 无权限时返回提示信息，有权限返回None
    """
    bot_info = await bot.get_group_member_info(
        group_id=group_id,
        user_id=bot.self_id,
    )
    if bot_info["role"] not in _ADMIN_ROLES:
        return f"我还没有管理员权限，无法{action}"
    return None


class GroupMemberManage:
    """OneBot群成员管理，提供禁言/解禁/踢出操作"""

    @classmethod
    async def mute_user(
        cls,
        bot: Bot,
        group_id: str,
        user_id: str,
        duration: int,
        operator_id: str,
    ) -> str:
        """禁言用户

        参数:
            bot: Bot实例
            group_id: 群组ID
            user_id: 用户ID
            duration: 禁言时长(分钟)
            operator_id: 操作者ID

        返回:
            str: 操作结果信息
        """
        try:
            if error := await _check_bot_admin(bot, group_id, "禁言用户"):
                return error

            await bot.set_group_ban(
                group_id=group_id,
                user_id=user_id,
                duration=duration * 60,
            )

            logger.info(
                f"管理员 {operator_id} 在群 {group_id} 禁言用户 {user_id}"
                f" {duration} 分钟",
                "群成员管理",
                session=operator_id,
                group_id=group_id,
            )
            return f"已将用户 {user_id} 禁言 {duration} 分钟"

        except Exception as e:
            logger.error(
                "禁言用户失败",
                "群成员管理",
                session=operator_id,
                group_id=group_id,
                e=e,
            )
            return f"禁言用户失败: {e!s}"

    @classmethod
    async def unmute_user(
        cls,
        bot: Bot,
        group_id: str,
        user_id: str,
        operator_id: str,
    ) -> str:
        """解除用户禁言

        参数:
            bot: Bot实例
            group_id: 群组ID
            user_id: 用户ID
            operator_id: 操作者ID

        返回:
            str: 操作结果信息
        """
        try:
            if error := await _check_bot_admin(bot, group_id, "解除禁言"):
                return error

            await bot.set_group_ban(
                group_id=group_id,
                user_id=user_id,
                duration=0,
            )

            logger.info(
                f"管理员 {operator_id} 在群 {group_id} 解除用户 {user_id} 的禁言",
                "群成员管理",
                session=operator_id,
                group_id=group_id,
            )
            return f"已解除用户 {user_id} 的禁言"

        except Exception as e:
            logger.error(
                "解除用户禁言失败",
                "群成员管理",
                session=operator_id,
                group_id=group_id,
                e=e,
            )
            return f"解除用户禁言失败: {e!s}"

    @classmethod
    async def kick_user(
        cls,
        bot: Bot,
        group_id: str,
        user_id: str,
        operator_id: str,
    ) -> str:
        """踢出用户

        参数:
            bot: Bot实例
            group_id: 群组ID
            user_id: 用户ID
            operator_id: 操作者ID

        返回:
            str: 操作结果信息
        """
        try:
            if error := await _check_bot_admin(bot, group_id, "踢出用户"):
                return error

            await bot.set_group_kick(
                group_id=group_id,
                user_id=user_id,
                reject_add_request=False,
            )

            logger.info(
                f"管理员 {operator_id} 在群 {group_id} 踢出用户 {user_id}",
                "群成员管理",
                session=operator_id,
                group_id=group_id,
            )
            return f"已将用户 {user_id} 踢出群聊"

        except Exception as e:
            logger.error(
                "踢出用户失败",
                "群成员管理",
                session=operator_id,
                group_id=group_id,
                e=e,
            )
            return f"踢出用户失败: {e!s}"
