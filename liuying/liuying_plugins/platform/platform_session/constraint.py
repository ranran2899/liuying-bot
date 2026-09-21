"""适配器与平台范围约束"""

from enum import StrEnum


class SupportAdapter(StrEnum):
    """本插件支持的适配器"""

    onebot11 = "OneBot V11"
    """OneBot V11 适配器"""
    onebot12 = "OneBot V12"
    """OneBot V12 适配器"""
    qq = "QQ"
    """QQ 官方适配器"""
    minecraft = "Minecraft"
    """Minecraft 适配器"""


class SupportScope(StrEnum):
    """支持的平台范围，相比 adapter 更指向实际平台"""

    qq_client = "QQClient"
    """QQ 协议端"""
    qq_guild = "QQGuild"
    """QQ 用户频道，非官方接口"""
    qq_api = "QQAPI"
    """QQ 官方接口"""
    minecraft = "Minecraft"
    """Minecraft 平台"""

    onebot12_other = "Onebot12"
    """ob12 的其他平台"""

    unknown = "Unknown"
    """未知平台"""

    @staticmethod
    def ensure_ob12(platform: str) -> SupportScope:
        """根据 ob12 的 platform 字段推断平台范围"""
        return {
            "qq": SupportScope.qq_client,
            "qqguild": SupportScope.qq_guild,
        }.get(platform, SupportScope.onebot12_other)
