"""
NoneBot 天气插件
"""
from .weather import weather_cmd, districts_cmd
from .api import WeatherAPI

from nonebot.plugin import PluginMetadata
from liuying.configs.utils import RegisterConfig, PluginExtraData, PluginCdBlock, Command

__plugin_meta__ = PluginMetadata(
    name="天气",
    description="查询天气信息",
    usage="""
    查询天气信息
    指令:
        天气 北京
        天气 广东-广州
        支持区县 河北
    """
    .strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        menu_type="实用工具",
        is_show=True,
        commands=[
            Command(command="天气"),
            Command(command="支持区县"),
        ],
        configs=[],
    ).to_dict(),
)


# 导出插件命令和API
export = [weather_cmd, districts_cmd, WeatherAPI]