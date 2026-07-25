"""本地图库管理插件核心功能实现"""

from datetime import datetime

from nonebot_plugin_uninfo import Uninfo

from liuying.models._bot.bed_layout_image import BedLayoutImage
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

PAGE_SIZE = 20


class BedLayoutGalleryHandler:
    """图库命令处理器"""

    @staticmethod
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

    @staticmethod
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

    @classmethod
    def _format_image_line(cls, idx: int, img: BedLayoutImage) -> str:
        """格式化单条图片信息行

        参数:
            idx: 序号
            img: 图片模型实例

        返回:
            str: 格式化的图片信息行
        """
        original = img.original_filename or "无"
        size_text = cls._format_size(img.file_size)
        time_text = cls._format_time(img.create_time)
        return (
            f"{idx}. {img.filename}\n"
            f"   原始名: {original} | 大小: {size_text} | {time_text}"
        )

    @classmethod
    async def stats(cls, session: Uninfo) -> None:
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
            f"总存储大小: {cls._format_size(total_size)} "
            f"({stats['total_size_mb']} MB)\n"
            f"按MIME类型分类:\n{content_type_lines}\n"
            f"按扩展名分类:\n{extension_lines}"
        )
        await MessageUtils.build_message(msg).finish(reply_to=True)

    @classmethod
    async def list_images(cls, session: Uninfo, page: int) -> None:
        """处理图库列表请求

        参数:
            session: 会话信息
            page: 页码参数
        """
        logger.info(
            f"用户 {session.user.id} 查看图库列表 第{page}页",
            "图库列表",
            session=session,
        )

        images, total_pages, total = await BedLayoutImage.get_images_paginated(
            page=page, per_page=PAGE_SIZE
        )

        if not images:
            await MessageUtils.build_message("图库当前为空，暂无图片").finish(
                reply_to=True
            )

        lines = [
            cls._format_image_line(idx, img)
            for idx, img in enumerate(images, start=1)
        ]
        msg = f"图库列表 (第{page}/{total_pages}页, 共{total}张)\n" + "\n".join(
            lines
        )
        await MessageUtils.build_message(msg).finish(reply_to=True)

    @classmethod
    async def search(cls, session: Uninfo, keyword: str) -> None:
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

        lines = [
            cls._format_image_line(idx, img)
            for idx, img in enumerate(images, start=1)
        ]
        msg = f"搜索 '{keyword}' 结果 (共{len(images)}条):\n" + "\n".join(lines)
        await MessageUtils.build_message(msg).finish(reply_to=True)

    @classmethod
    async def view(cls, session: Uninfo, filename: str) -> None:
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
            f"大小: {cls._format_size(image.file_size)}\n"
            f"MIME: {image.content_type or '未知'}\n"
            f"创建时间: {cls._format_time(image.create_time)}"
        ).finish()
