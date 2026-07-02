"""本地图库管理插件

提供图库存储统计、图片列表、按名称搜索、查看图片等管理功能。
仅限管理员使用。
"""
from datetime import datetime

from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Match, Option, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import Command, PluginExtraData
from liuying.models._bot.bed_layout_image import BedLayoutImage
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.utils.rules import admin_check

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

PAGE_SIZE = 20


def _format_size(size_bytes: int) -> str:
    """格式化文件大小为人类可读字符串

    参数:
        size_bytes: 文件大小（字节）

    返回:
        str: 格式化后的大小字符串
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _format_time(create_time: datetime | None) -> str:
    """格式化创建时间

    参数:
        create_time: 创建时间对象

    返回:
        str: 格式化后的时间字符串，无值时返回 "未知"
    """
    if create_time is None:
        return "未知"
    return create_time.strftime("%Y-%m-%d %H:%M")


@_stats_matcher.handle()
async def _handle_stats(session: Uninfo):
    """处理图库统计请求

    参数:
        session: 会话信息
    """
    logger.info(
        f"用户 {session.user.id} 查询图库统计", "图库统计", session=session
    )

    stats = await BedLayoutImage.get_stats()

    image_count = stats["image_count"]
    if image_count == 0:
        await MessageUtils.build_message("图库当前为空，暂无图片").finish(
            reply_to=True
        )

    total_size = stats["total_size"]
    content_type_lines = "\n".join(
        f"  - {ct}: {count} 张"
        for ct, count in sorted(
            stats["by_content_type"].items(),
            key=lambda x: x[1],
            reverse=True,
        )
    )
    extension_lines = "\n".join(
        f"  - {ext}: {count} 张"
        for ext, count in sorted(
            stats["by_extension"].items(),
            key=lambda x: x[1],
            reverse=True,
        )
    )

    msg = (
        f"图库统计信息\n"
        f"图片总数: {image_count} 张\n"
        f"总存储大小: {_format_size(total_size)} "
        f"({stats['total_size_mb']} MB)\n"
        f"按MIME类型分类:\n{content_type_lines}\n"
        f"按扩展名分类:\n{extension_lines}"
    )
    await MessageUtils.build_message(msg).finish(reply_to=True)


@_list_matcher.handle()
async def _handle_list(session: Uninfo, page: Match[int]):
    """处理图库列表请求

    参数:
        session: 会话信息
        page: 页码参数
    """
    current_page = page.result if page.available else 1
    logger.info(
        f"用户 {session.user.id} 查看图库列表 第{current_page}页",
        "图库列表",
        session=session,
    )

    images, total_pages, total = await BedLayoutImage.get_images_paginated(
        page=current_page, per_page=PAGE_SIZE
    )

    if not images:
        await MessageUtils.build_message("图库当前为空，暂无图片").finish(
            reply_to=True
        )

    lines = []
    for idx, img in enumerate(images, start=1):
        original = img.original_filename or "无"
        size_text = _format_size(img.file_size)
        time_text = _format_time(img.create_time)
        lines.append(
            f"{idx}. {img.filename}\n"
            f"   原始名: {original} | 大小: {size_text} | {time_text}"
        )

    msg = (
        f"图库列表 (第{current_page}/{total_pages}页, 共{total}张)\n"
        + "\n".join(lines)
    )
    await MessageUtils.build_message(msg).finish(reply_to=True)


@_search_matcher.handle()
async def _handle_search(session: Uninfo, keyword: str):
    """处理图库搜索请求

    参数:
        session: 会话信息
        keyword: 搜索关键词
    """
    logger.info(
        f"用户 {session.user.id} 搜索图库图片: {keyword}",
        "图库搜索",
        session=session,
    )

    images = await BedLayoutImage.search_by_name(keyword, limit=PAGE_SIZE)

    if not images:
        await MessageUtils.build_message(
            f"未找到包含 '{keyword}' 的图片"
        ).finish(reply_to=True)

    lines = []
    for idx, img in enumerate(images, start=1):
        original = img.original_filename or "无"
        size_text = _format_size(img.file_size)
        time_text = _format_time(img.create_time)
        lines.append(
            f"{idx}. {img.filename}\n"
            f"   原始名: {original} | 大小: {size_text} | {time_text}"
        )

    msg = f"搜索 '{keyword}' 结果 (共{len(images)}条):\n" + "\n".join(lines)
    await MessageUtils.build_message(msg).finish(reply_to=True)


@_view_matcher.handle()
async def _handle_view(session: Uninfo, filename: str):
    """处理图库查看请求

    参数:
        session: 会话信息
        filename: 图片文件名
    """
    logger.info(
        f"用户 {session.user.id} 查看图库图片: {filename}",
        "图库查看",
        session=session,
    )

    image = await BedLayoutImage.get_image_by_filename(filename)

    if image is None or not image.file_data:
        await MessageUtils.build_message(
            f"未找到图片: {filename}"
        ).finish(reply_to=True)

    try:
        await MessageUtils.build_message(image.file_data).send(reply_to=True)
    except Exception as e:
        logger.error(f"发送图片失败: {filename}, {e}", "图库查看")
        return

    await MessageUtils.build_message(
        f"文件名: {image.filename}\n"
        f"原始名: {image.original_filename or '无'}\n"
        f"大小: {_format_size(image.file_size)}\n"
        f"MIME: {image.content_type or '未知'}\n"
        f"创建时间: {_format_time(image.create_time)}"
    ).finish()
