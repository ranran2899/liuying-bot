"""博查搜索插件

将博查 AI 搜索客户端注册到 LLM 网络搜索模块，
支持网页与图片搜索结果。

本插件为服务型插件，不提供主动触发命令，仅在后台注册搜索客户端。
配置项通过流萤配置系统管理，在 plugins2config.yaml 的 BOCHA_SEARCH 模块下。
"""
from nonebot.plugin import PluginMetadata

from liuying.configs.utils import PluginExtraData, RegisterConfig
from liuying.utils.enum import PluginType

from . import bocha  # noqa: F401

__plugin_meta__ = PluginMetadata(
    name="博查搜索",
    description="博查 AI 搜索客户端，支持网页与图片结果",
    usage="服务型插件，无需手动调用，自动注册到 LLM 网络搜索模块",
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        plugin_type=PluginType.DEPENDANT,
        menu_type="服务",
        is_show=False,
        configs=[
            RegisterConfig(
                key="API_KEY",
                value="",
                help="博查 AI 搜索 API 密钥",
                default_value="",
                type=str,
            ),
            RegisterConfig(
                key="BASE_URL",
                value="https://api.bochaai.com/v1",
                help="博查 API 基础地址",
                default_value="https://api.bochaai.com/v1",
                type=str,
            ),
        ],
    ).to_dict(),
)
