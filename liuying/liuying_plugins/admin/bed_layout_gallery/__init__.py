"""本地图库管理插件

提供图库存储统计、图片列表、按名称搜索、查看图片等管理功能。
仅限管理员使用。
"""

from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Match, Option, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import Command, PluginExtraData
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.rules import admin_check

from .data_source import BedLayoutGalleryHandler

__plugin_meta__ = PluginMetadata(
    name="本地图库管理",
    description="管理本地床图图库：统计、搜索、查看图片",
    usage="""
    管理员命令
        格式:
        图库统计                : 查看图库存储统计
        图库列表 ?[-p 页码]     : 查看图库图片列表
        图库搜索 [名称]         : 按名称搜索图片
        图库查看 [文件名]       : 查看指定图片

    示例:
        图库统计
        图库列表 -p 2
        图库搜索 头像
        图库查看 abc123.png
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        admin_level=7,
        plugin_type=PluginType.SUPER_AND_ADMIN,
        commands=[
            Command(command="图库统计"),
            Command(command="图库列表"),
            Command(command="图库搜索"),
            Command(command="图库查看"),
        ],
    ).to_dict(),
)

_stats_matcher = on_alconna(
    Alconna("图库统计"),
    rule=admin_check(7),
    priority=5,
    block=True,
)

_list_matcher = on_alconna(
    Alconna("图库列表", Option("-p|--page", Args["page", int, 1], help_text="页码")),
    rule=admin_check(7),
    priority=5,
    block=True,
)

_search_matcher = on_alconna(
    Alconna("图库搜索", Args["keyword", str]),
    rule=admin_check(7),
    priority=5,
    block=True,
)

_view_matcher = on_alconna(
    Alconna("图库查看", Args["filename", str]),
    rule=admin_check(7),
    priority=5,
    block=True,
)


@_stats_matcher.handle()
async def _(session: Uninfo):
    """处理图库统计命令"""
    logger.info("查询图库统计", command="图库统计", session=session)
    await BedLayoutGalleryHandler.stats(session)


@_list_matcher.handle()
async def _(session: Uninfo, page: Match[int]):
    """处理图库列表命令"""
    current_page = page.result if page.available else 1
    logger.info(
        f"查看图库列表 第{current_page}页",
        command="图库列表",
        session=session,
    )
    await BedLayoutGalleryHandler.list_images(session, current_page)


@_search_matcher.handle()
async def _(session: Uninfo, keyword: str):
    """处理图库搜索命令"""
    logger.info(f"搜索图库图片: {keyword}", command="图库搜索", session=session)
    await BedLayoutGalleryHandler.search(session, keyword)


@_view_matcher.handle()
async def _(session: Uninfo, filename: str):
    """处理图库查看命令"""
    logger.info(f"查看图库图片: {filename}", command="图库查看", session=session)
    await BedLayoutGalleryHandler.view(session, filename)
