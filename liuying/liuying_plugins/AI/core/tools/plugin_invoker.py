"""插件命令调用器

代为执行其他插件的命令，通过 nonebot matcher 触发。
"""

from typing import Any

import nonebot

from liuying.utils.log import logger

_MAX_INVOKE_ARGS_LEN = 500
"""调用参数最大长度"""


class PluginInvoker:
    """插件命令调用器

    通过查找已加载插件的 matcher 列表，触发指定命令。
    当前实现为命令触发预留接口，实际执行依赖 nonebot 运行时。
    """

    async def invoke(
        self,
        plugin_name: str,
        command: str,
        args: str,
    ) -> str:
        """代为执行其他插件命令

        通过 nonebot matcher 触发指定插件命令。

        参数:
            plugin_name: 插件模块名
            command: 命令名（不含前缀）
            args: 命令参数

        返回:
            str: 执行结果文本
        """
        if not plugin_name or not command:
            return "插件名和命令名不能为空"
        if len(args) > _MAX_INVOKE_ARGS_LEN:
            return "参数过长"

        try:
            matcher = self._find_matcher(plugin_name, command)
            if matcher is None:
                return (
                    f"未找到插件 {plugin_name} 的命令 {command}"
                )
            return await self._dispatch(matcher, args)
        except Exception as e:
            logger.warning(
                f"调用插件 {plugin_name}.{command} 失败: {e}",
                command="AI",
                e=e,
            )
            return f"调用失败: {e}"

    def _find_matcher(
        self, plugin_name: str, command: str
    ) -> Any | None:
        """查找插件matcher

        参数:
            plugin_name: 插件模块名
            command: 命令名

        返回:
            Any | None: matcher或None
        """
        try:
            plugin = nonebot.get_plugin(plugin_name)
            if plugin is None:
                return None
            cmd_lower = command.lower()
            for matcher in plugin.matcher:
                cmd_str = self._extract_cmd(matcher)
                if cmd_str and cmd_str.lower() == cmd_lower:
                    return matcher
            return None
        except Exception as e:
            logger.debug(
                f"查找matcher失败: {e}",
                command="AI",
                e=e,
            )
            return None

    def _extract_cmd(self, matcher: Any) -> str:
        """提取matcher的命令字符串

        参数:
            matcher: matcher对象

        返回:
            str: 命令字符串
        """
        try:
            cmd = getattr(matcher, "command", None)
            if cmd:
                if isinstance(cmd, list | tuple):
                    return " ".join(str(c) for c in cmd)
                return str(cmd)
            state_default = getattr(matcher, "state", {})
            if isinstance(state_default, dict):
                prefix = state_default.get("_prefix", {})
                if isinstance(prefix, dict):
                    cmd_val = prefix.get("command")
                    if cmd_val:
                        if isinstance(cmd_val, list | tuple):
                            return " ".join(
                                str(c) for c in cmd_val
                            )
                        return str(cmd_val)
            return ""
        except Exception:
            return ""

    async def _dispatch(
        self, matcher: Any, args: str
    ) -> str:
        """分发命令执行

        参数:
            matcher: matcher对象
            args: 命令参数

        返回:
            str: 执行结果
        """
        logger.info(
            f"插件命令触发: {matcher} args={args[:80]}",
            command="AI",
        )
        try:
            event = self._build_event(args)
            await matcher.test(event)
            return f"命令已触发: {args}"
        except Exception as e:
            logger.debug(
                f"命令分发失败: {e}",
                command="AI",
                e=e,
            )
            return f"命令触发失败: {e}"

    def _build_event(self, args: str) -> dict[str, Any]:
        """构造命令触发上下文

        参数:
            args: 命令参数

        返回:
            dict: 上下文字典
        """
        return {
            "post_type": "message",
            "raw_message": args,
            "message_type": "private",
            "user_id": 0,
            "self_id": 0,
            "text": args,
            "_prefix": {"command": args.split()[0] if args else ""},
        }


plugin_invoker = PluginInvoker()
"""插件命令调用器单例"""
