"""消息内容提取器

统一从 NoneBot 消息事件中提取文本、图片等多媒体内容，
屏蔽不同适配器消息段差异，供 AI 插件各模块复用。
"""
import base64
from pathlib import Path
from typing import Any

from nonebot.adapters import Event

from liuying.utils.http.http_utils import AsyncHttpx
from liuying.utils.log import logger

__all__ = ["MessageExtractor", "message_extractor"]


class MessageExtractor:
    """消息内容提取器

    封装从消息事件提取文本/图片段与获取图片字节的能力，
    所有方法均为静态方法，屏蔽不同适配器消息段差异。
    """

    @staticmethod
    def extract_message_text(event: Event) -> str:
        """从事件消息中提取纯文本内容

        遍历消息段，仅保留 text 类型段的文本并拼接。

        参数:
            event: 消息事件

        返回:
            str: 提取并清理后的文本
        """
        message = getattr(event, "message", None)
        if not message:
            return ""

        texts: list[str] = []
        for seg in message:
            seg_type = str(getattr(seg, "type", "")).lower()
            if seg_type != "text":
                continue
            data = getattr(seg, "data", None) or {}
            if isinstance(data, dict):
                seg_text = str(data.get("text") or "")
            else:
                seg_text = str(getattr(data, "text", "") or "")
            texts.append(seg_text)

        return "".join(texts).strip()

    @staticmethod
    def extract_image_segments(
        event: Event,
    ) -> list[dict[str, Any]]:
        """从事件消息中提取图片段信息

        兼容 image/attachment 类型消息段，适配不同协议适配器。

        参数:
            event: 消息事件

        返回:
            list[dict]: 图片信息列表（含 url/path/raw）
        """
        message = getattr(event, "message", None)
        if not message:
            return []

        results: list[dict[str, Any]] = []
        for seg in message:
            seg_type = str(getattr(seg, "type", "")).lower()
            if seg_type not in ("image", "attachment"):
                continue
            data = getattr(seg, "data", None) or {}
            url = str(data.get("url") or data.get("image") or "")
            path = str(data.get("file") or data.get("path") or "")
            raw = data.get("data") or None
            if isinstance(raw, str) and raw.startswith("base64://"):
                raw = base64.b64decode(raw[9:])
            results.append({"url": url, "path": path, "raw": raw})

        return results

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
                file_path = Path(path)
                if file_path.exists():
                    return file_path.read_bytes()
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


message_extractor = MessageExtractor()
"""消息内容提取器单例"""
