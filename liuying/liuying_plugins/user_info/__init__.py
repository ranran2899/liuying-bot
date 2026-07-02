"""
用户信息插件
"""
from nonebot.plugin import PluginMetadata

from liuying.configs.utils import Command, PluginExtraData
from liuying.liuying_plugins.user_info.user_info import user_info_cmd

__plugin_meta__ = PluginMetadata(
    name="用户信息",
    description="查看用户基本信息",
    usage="""
    查看用户基本信息
    指令:
        我的信息
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.2",
        commands=[
            Command(command="我的信息"),
        ],
    ).to_dict(),
)

__all__ = ["user_info_cmd"]
