"""文件发送功能

发送本地文件或URL文件到群/私聊。
优先使用 OneBot 协议的文件上传API，
不支持时回退为发送文本提示。
"""

from pathlib import Path
from typing import Any

from liuying.utils.log import logger

from ..config import get_config


class FileSender:
    """文件发送器

    支持本地文件与URL文件发送，自动区分群聊/私聊。
    """

    async def send_file(
        self,
        bot: Any,
        event: Any,
        file_path: str,
        file_name: str = "",
    ) -> bool:
        """发送文件到当前会话

        参数:
            bot: Bot实例
            event: 事件对象
            file_path: 文件路径或URL
            file_name: 显示文件名，空时从路径推断

        返回:
            bool: 是否发送成功
        """
        if not get_config("FILE_SEND_ENABLED", True):
            logger.debug(
                "文件发送未启用", command="AI"
            )
            return False
        if not file_path:
            return False
        name = file_name or self._infer_name(file_path)
        group_id = self._get_group_id(event)
        try:
            if group_id:
                return await self._send_to_group(
                    bot, group_id, file_path, name
                )
            user_id = self._get_user_id(event)
            if user_id:
                return await self._send_to_private(
                    bot, user_id, file_path, name
                )
            logger.warning(
                "无法确定发送目标", command="AI"
            )
            return False
        except Exception as e:
            logger.warning(
                f"文件发送失败: {e}", command="AI", e=e
            )
            return False

    async def _send_to_group(
        self,
        bot: Any,
        group_id: str,
        file_path: str,
        file_name: str,
    ) -> bool:
        """发送文件到群聊

        参数:
            bot: Bot实例
            group_id: 群号
            file_path: 文件路径或URL
            file_name: 显示文件名

        返回:
            bool: 是否发送成功
        """
        try:
            await bot.call_api(
                "upload_group_file",
                group_id=int(group_id),
                file=file_path,
                name=file_name,
            )
            logger.debug(
                f"群文件发送成功: group={group_id} "
                f"name={file_name}",
                command="AI",
            )
            return True
        except Exception as e:
            logger.debug(
                f"群文件上传API不可用，回退文本: {e}",
                command="AI",
                e=e,
            )
            return await self._fallback_send(
                bot, group_id, file_path, file_name, True
            )

    async def _send_to_private(
        self,
        bot: Any,
        user_id: str,
        file_path: str,
        file_name: str,
    ) -> bool:
        """发送文件到私聊

        参数:
            bot: Bot实例
            user_id: 用户QQ
            file_path: 文件路径或URL
            file_name: 显示文件名

        返回:
            bool: 是否发送成功
        """
        try:
            await bot.call_api(
                "upload_private_file",
                user_id=int(user_id),
                file=file_path,
                name=file_name,
            )
            logger.debug(
                f"私聊文件发送成功: user={user_id} "
                f"name={file_name}",
                command="AI",
            )
            return True
        except Exception as e:
            logger.debug(
                f"私聊文件上传API不可用，回退文本: {e}",
                command="AI",
                e=e,
            )
            return await self._fallback_send(
                bot, user_id, file_path, file_name, False
            )

    async def _fallback_send(
        self,
        bot: Any,
        target_id: str,
        file_path: str,
        file_name: str,
        is_group: bool,
    ) -> bool:
        """回退为发送文本提示

        参数:
            bot: Bot实例
            target_id: 目标ID
            file_path: 文件路径或URL
            file_name: 显示文件名
            is_group: 是否群聊

        返回:
            bool: 是否发送成功
        """
        text = f"[文件] {file_name}\n{file_path}"
        try:
            if is_group:
                await bot.call_api(
                    "send_group_msg",
                    group_id=int(target_id),
                    message=text,
                )
            else:
                await bot.call_api(
                    "send_private_msg",
                    user_id=int(target_id),
                    message=text,
                )
            return True
        except Exception as e:
            logger.warning(
                f"回退文本发送失败: {e}",
                command="AI",
                e=e,
            )
            return False

    def _infer_name(self, file_path: str) -> str:
        """从路径推断文件名

        参数:
            file_path: 文件路径或URL

        返回:
            str: 推断的文件名
        """
        if not file_path:
            return "file"
        if "://" in file_path:
            tail = file_path.split("?", 1)[0].rsplit("/", 1)[-1]
            return tail or "file"
        return Path(file_path).name or "file"

    def _get_group_id(self, event: Any) -> str:
        """从事件获取群号

        参数:
            event: 事件对象

        返回:
            str: 群号字符串，私聊返回空串
        """
        group_id = getattr(event, "group_id", None)
        if group_id is None:
            group_id = getattr(event, "channel_id", None)
        return str(group_id) if group_id else ""

    def _get_user_id(self, event: Any) -> str:
        """从事件获取用户ID

        参数:
            event: 事件对象

        返回:
            str: 用户ID字符串
        """
        user_id = getattr(event, "user_id", None)
        if user_id is None:
            try:
                user_id = event.get_user_id()
            except Exception:
                return ""
        return str(user_id) if user_id else ""


file_sender = FileSender()
"""文件发送器单例"""
