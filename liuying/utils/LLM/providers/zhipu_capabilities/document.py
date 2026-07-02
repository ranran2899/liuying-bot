"""智谱 AI 文档解析能力实现"""
import os
from typing import Any

from liuying.utils.LLM.zhi_pu.client import ZhipuClient


class ZhipuDocumentCapability:
    """智谱 AI 文档解析能力（智能文档理解）"""

    def __init__(self, client: ZhipuClient | None = None):
        """初始化文档解析能力

        Args:
            client: 智谱客户端实例
        """
        self._client = client or ZhipuClient()

    async def parse(
        self,
        file: bytes | str,
        file_name: str = "",
        model: str = "document-parser",
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """解析文档

        Args:
            file: 文件字节数据或 URL
            file_name: 文件名（字节模式下必须）
            model: 解析模型名称
            options: 额外选项

        Returns:
            解析结果字典
        """
        if isinstance(file, bytes):
            if not file_name:
                raise ValueError("字节模式下必须提供 file_name")
            files = {
                "file": (file_name, file, self._get_mime_type(file_name))
            }
            data: dict[str, Any] = {"model": model}
            if options:
                data.update(options)
            return await self._client.post_multipart(
                "document/parser", files, data, timeout=300
            )

        request_data: dict[str, Any] = {"model": model, "url": file}
        if options:
            request_data.update(options)
        return await self._client.post(
            "document/parser", request_data, timeout=300
        )

    async def extract_text(
        self,
        file: bytes | str,
        file_name: str = "",
        options: dict[str, Any] | None = None,
    ) -> str:
        """提取文档纯文本内容

        Args:
            file: 文件字节数据或 URL
            file_name: 文件名
            options: 额外选项

        Returns:
            提取的文本内容
        """
        result = await self.parse(file, file_name, options=options)
        return result.get("text", "")

    async def extract_structured(
        self,
        file: bytes | str,
        file_name: str = "",
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """提取文档结构化内容

        Args:
            file: 文件字节数据或 URL
            file_name: 文件名
            options: 额外选项

        Returns:
            结构化数据字典
        """
        result = await self.parse(file, file_name, options=options)
        return {
            "text": result.get("text", ""),
            "paragraphs": result.get("paragraphs", []),
            "tables": result.get("tables", []),
            "images": result.get("images", []),
            "metadata": result.get("metadata", {}),
        }

    @staticmethod
    def _get_mime_type(file_name: str) -> str:
        """根据文件名获取 MIME 类型

        Args:
            file_name: 文件名

        Returns:
            MIME 类型字符串
        """
        mime_map: dict[str, str] = {
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": (
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".tiff": "image/tiff",
            ".xls": "application/vnd.ms-excel",
            ".xlsx": (
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
        }

        ext = os.path.splitext(file_name)[1].lower()
        return mime_map.get(ext, "application/octet-stream")


__all__ = ["ZhipuDocumentCapability"]
