"""消息内容提取器

图片二进制获取工具，多平台消息内容解析统一由
nonebot_plugin_alconna 的 UniMessage 提供。
"""

import anyio

from liuying.utils.http.http_utils import AsyncHttpx
from liuying.utils.log import logger

__all__ = ["MessageExtractor"]


class MessageExtractor:
    """消息内容提取器

    提供图片二进制获取能力，按 raw > path > url 的优先级读取。
    """

    @staticmethod
    async def fetch_image_bytes(
        url: str = "",
        path: str = "",
        raw: bytes | None = None,
    ) -> bytes | None:
        """获取图片二进制数据

        优先级: raw > path > url

        参数:
            url: 图片URL
            path: 本地路径
            raw: 原始字节

        返回:
            bytes | None: 图片数据，失败返回None
        """
        if raw:
            return raw

        if path:
            try:
                # anyio.Path 提供异步文件操作，避免阻塞事件循环
                file_path = anyio.Path(path)
                if await file_path.exists():
                    return await file_path.read_bytes()
            except Exception as e:
                logger.debug(
                    f"读取本地图片失败: {e}", command="AI", e=e
                )

        if url:
            try:
                return await AsyncHttpx.get_content(url)
            except Exception as e:
                logger.debug(
                    f"下载网络图片失败: {e}", command="AI", e=e
                )

        return None
