"""百度搜索插件

将百度千帆 AI 搜索客户端注册到 LLM 网络搜索模块，
支持 web_search/chat/web_summary 三种搜索模式。

本插件为服务型插件，不提供主动触发命令，仅在后台注册搜索客户端。
配置项通过流萤配置系统管理，在 plugins2config.yaml 的 BAIDU_SEARCH 模块下。
"""
from nonebot.plugin import PluginMetadata

from liuying.configs.utils import PluginExtraData, RegisterConfig
from liuying.utils.enum import PluginType

from . import baidu  # noqa: F401

__plugin_meta__ = PluginMetadata(
    name="百度搜索",
    description="百度千帆 AI 搜索客户端，支持 web_search/chat/web_summary 三种模式",
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
                help="百度千帆 API 密钥",
                default_value="",
                type=str,
            ),
            RegisterConfig(
                key="BASE_URL",
                value="https://qianfan.baidubce.com",
                help="百度千帆 API 基础地址",
                default_value="https://qianfan.baidubce.com",
                type=str,
            ),
            RegisterConfig(
                key="DEFAULT_MODE",
                value="web_search",
                help="默认搜索模式：web_search/chat/web_summary",
                default_value="web_search",
                type=str,
            ),
            RegisterConfig(
                key="CHAT_MODEL",
                value="ernie-4.5-turbo-32k",
                help="chat 模式使用的大模型名称",
                default_value="ernie-4.5-turbo-32k",
                type=str,
            ),
            RegisterConfig(
                key="DAILY_LIMIT",
                value=100,
                help="chat/web_summary 模式每日免费额度",
                default_value=100,
                type=int,
            ),
        ],
    ).to_dict(),
)
