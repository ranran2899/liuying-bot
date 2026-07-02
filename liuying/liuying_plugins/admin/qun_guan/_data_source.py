from nonebot.adapters import Bot

from liuying.utils.log import logger

_ADMIN_ROLES = frozenset({"admin", "owner"})


async def _check_bot_admin(bot: Bot, group_id: str) -> str | None:
    """检查bot是否有管理员权限

    参数:
        bot: Bot实例
        group_id: 群组ID

    返回:
        str | None: 无权限时返回提示信息，有权限返回None
    """
    bot_info = await bot.get_group_member_info(
        group_id=group_id,
        user_id=bot.self_id,
    )
    if bot_info["role"] not in _ADMIN_ROLES:
        return "没有管理员权限，无法执行此操作"
    return None


class QunGuanManage:
    """群管功能管理类"""

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
            if error := await _check_bot_admin(bot, group_id):
                return error.replace("执行此操作", "禁言用户")

            await bot.set_group_ban(
                group_id=group_id,
                user_id=user_id,
                duration=duration * 60,
            )

            logger.info(
                f"管理员 {operator_id} 在群 {group_id} 禁言用户 {user_id} "
                f"{duration} 分钟"
            )
            return f"已成功禁言用户 {user_id}，时长: {duration} 分钟"

        except Exception as e:
            logger.error(f"禁言用户失败: {e}")
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
            if error := await _check_bot_admin(bot, group_id):
                return error.replace("执行此操作", "解除用户禁言")

            await bot.set_group_ban(
                group_id=group_id,
                user_id=user_id,
                duration=0,
            )

            logger.info(
                f"管理员 {operator_id} 在群 {group_id} 解除用户 {user_id} 的禁言"
            )
            return f"已成功解除用户 {user_id} 的禁言"

        except Exception as e:
            logger.error(f"解除用户禁言失败: {e}")
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
            if error := await _check_bot_admin(bot, group_id):
                return error.replace("执行此操作", "踢出用户")

            await bot.set_group_kick(
                group_id=group_id,
                user_id=user_id,
                reject_add_request=False,
            )

            logger.info(f"管理员 {operator_id} 在群 {group_id} 踢出用户 {user_id}")
            return f"已成功踢出用户 {user_id}"

        except Exception as e:
            logger.error(f"踢出用户失败: {e}")
            return f"踢出用户失败: {e!s}"
