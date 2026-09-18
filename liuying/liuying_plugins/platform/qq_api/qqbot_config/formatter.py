"""QQ机器人配置信息格式化"""

from typing import Any


class ConfigFormatter:
    """QQ机器人配置信息格式化器

    封装配置查询/意图/适配器状态等消息文本的统一构建
    """

    @staticmethod
    def format_single(bot: dict[str, Any], online: bool) -> str:
        """格式化单个配置信息

        参数:
            bot: QQ_BOTS格式的单个机器人配置
            online: 是否在线

        返回:
            str: 格式化后的配置信息字符串
        """
        lines = [
            f"机器人ID: {bot['id']}",
            f"连接状态: {'在线' if online else '离线'}",
            f"Secret: {bot['secret'][:10]}...",
            f"WebSocket: {'启用' if bot['use_websocket'] else '禁用'}",
        ]
        enabled = [k for k, v in bot.get("intent", {}).items() if v]
        if enabled:
            lines.append(f"启用意图: {', '.join(enabled)}")
        return "\n".join(lines)

    @staticmethod
    def format_list(bots: list[dict[str, Any]], online_ids: set[str]) -> str:
        """格式化配置列表信息

        参数:
            bots: QQ_BOTS格式的配置列表
            online_ids: 在线机器人ID集合

        返回:
            str: 格式化后的配置列表字符串
        """
        parts = [f"共有 {len(bots)} 个QQ机器人配置:\n"]
        for i, b in enumerate(bots, 1):
            online_icon = "O" if b["id"] in online_ids else "X"
            parts.append(f"{i}. [{online_icon}] {b['id']}")
        return "\n".join(parts)

    @staticmethod
    def format_intent(
        intent: dict[str, bool], descriptions: dict[str, str]
    ) -> str:
        """格式化意图配置列表

        参数:
            intent: 意图配置字典
            descriptions: 字段描述映射

        返回:
            str: 格式化后的意图配置字符串
        """
        lines = ["意图配置:"]
        for field, value in intent.items():
            desc = descriptions.get(field, "")
            status = "启用" if value else "禁用"
            lines.append(f"  {field} ({desc}): {status}")
        return "\n".join(lines)

    @staticmethod
    def format_intent_fields(descriptions: dict[str, str]) -> str:
        """格式化可用意图字段列表

        参数:
            descriptions: 字段描述映射

        返回:
            str: 格式化后的可用字段字符串
        """
        lines = ["可用意图字段:"]
        lines.extend(f"  {f}: {desc}" for f, desc in descriptions.items())
        return "\n".join(lines)

    @staticmethod
    def format_status(status: dict[str, Any]) -> str:
        """格式化适配器状态信息

        参数:
            status: 适配器状态字典

        返回:
            str: 格式化后的状态字符串
        """
        parts = ["QQ适配器状态:\n"]

        connected = status["connected_bots"]
        if connected:
            parts.append(f"已连接机器人 ({len(connected)}个):")
            parts.extend(
                f"  - {bot['id']} ({bot['adapter']})" for bot in connected
            )
        else:
            parts.append("已连接机器人: 无")

        configured = status["configured_bots"]
        if configured:
            parts.append(f"\n已配置机器人 ({len(configured)}个):")
            parts.extend(
                f"  - {bot['id']} [{'WS' if bot['use_websocket'] else 'Webhook'}]"
                for bot in configured
            )
        else:
            parts.append("\n已配置机器人: 无")

        return "\n".join(parts)
