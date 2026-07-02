"""
请求处理器模块

封装HTTP请求处理和响应构建。
"""
import mimetypes
from pathlib import Path
import uuid

from aiohttp import multipart, web

from liuying.models._bot import BedLayoutImage
from liuying.utils.bed_layout.config import get_config
from liuying.utils.bed_layout.http.utils import BedLayoutHttpUtils
from liuying.utils.bed_layout.interfaces import validate_extension
from liuying.utils.bed_layout.providers.local import LocalStorageProvider
from liuying.utils.log import logger

from .security import SecurityGuard

# 图片响应安全头
_SECURITY_HEADERS = {
    "Cache-Control": "public, max-age=86400",
    "Access-Control-Allow-Origin": "*",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
}


class BedLayoutHandlers:
    """
    床图HTTP请求处理器

    封装所有HTTP接口的处理逻辑和响应构建。
    """

    @staticmethod
    def _image_response(data: bytes, content_type: str) -> web.Response:
        """构建图片响应（带安全头）"""
        return web.Response(
            body=data,
            content_type=content_type,
            headers=_SECURITY_HEADERS,
        )

    @staticmethod
    def _error_response(status: int, message: str) -> web.Response:
        """构建错误响应"""
        return web.Response(status=status, text=message)

    @staticmethod
    async def serve_image(request: web.Request) -> web.Response:
        """提供图片访问服务（公开只读接口）

        参数:
            request: HTTP请求对象

        返回:
            web.Response: 图片响应或错误响应
        """
        filename = request.match_info.get("filename", "")
        if not filename:
            return BedLayoutHandlers._error_response(400, "缺少文件名")

        image = await BedLayoutImage.get_image_by_filename(filename)
        if image:
            content_type = image.content_type or "application/octet-stream"
            return BedLayoutHandlers._image_response(image.file_data, content_type)

        return BedLayoutHandlers._error_response(404, "图片不存在")

    @staticmethod
    async def upload_image(request: web.Request) -> web.Response:
        """处理图片上传（需认证的写操作接口）

        参数:
            request: HTTP请求对象

        返回:
            web.Response: 上传结果响应
        """
        allowed, reason, status = await SecurityGuard.check_protection(request)
        match allowed:
            case False:
                return BedLayoutHandlers._error_response(
                    status, f"访问被拒绝: {reason}"
                )

        try:
            reader = await request.multipart()

            async for field in reader:
                match field.name:
                    case "image":
                        return await BedLayoutHandlers._handle_upload_field(
                            request, field
                        )

            return BedLayoutHandlers._error_response(400, "未找到上传的图片")

        except web.HTTPException:
            raise
        except Exception as e:
            logger.error(f"图片上传失败: {e}", "BedLayoutServer", e=e)
            return BedLayoutHandlers._error_response(500, "服务器内部错误")

    @staticmethod
    async def _handle_upload_field(
        request: web.Request,
        field: multipart.BodyPartReader,
    ) -> web.Response:
        """处理上传字段

        参数:
            request: HTTP请求对象
            field: multipart字段

        返回:
            web.Response: 上传结果响应
        """
        original_filename = field.filename or f"{uuid.uuid4().hex}"
        ext = Path(original_filename).suffix.lower()

        try:
            validate_extension(ext)
        except ValueError:
            client_ip = BedLayoutHttpUtils.get_client_ip(request)
            logger.warning(
                f"不支持的文件类型: {ext} | IP={client_ip}",
                "BedLayoutServer",
            )
            return BedLayoutHandlers._error_response(400, f"不支持的文件类型: {ext}")

        filename = f"{uuid.uuid4().hex}{ext}"
        chunks: list[bytes] = []
        size = 0
        max_size = get_config("MAX_FILE_SIZE", 10485760)

        while True:
            chunk = await field.read_chunk()
            if not chunk:
                break
            size += len(chunk)
            if size > max_size:
                client_ip = BedLayoutHttpUtils.get_client_ip(request)
                logger.warning(
                    f"文件大小超限: {size}>{max_size}字节 | IP={client_ip}",
                    "BedLayoutServer",
                )
                return BedLayoutHandlers._error_response(
                    413,
                    f"文件大小超过限制 ({max_size // 1024 // 1024}MB)",
                )
            chunks.append(chunk)

        file_data = b"".join(chunks)
        content_type, _ = mimetypes.guess_type(original_filename)

        provider = LocalStorageProvider()
        url = await provider.upload(file_data, filename, content_type)

        return web.json_response(
            {
                "success": True,
                "filename": filename,
                "original_filename": original_filename,
                "url": url,
                "size": size,
                "storage": "local",
            }
        )

    @staticmethod
    async def health_check(request: web.Request) -> web.Response:
        """健康检查接口（公开只读）

        参数:
            request: HTTP请求对象

        返回:
            web.Response: 健康状态响应
        """
        return web.json_response(
            {
                "status": "healthy",
                "service": "bed_layout",
                "version": "2.0.0",
                "security_features": {
                    "api_key_enabled": bool(get_config("API_KEY", "")),
                    "rate_limiting": True,
                    "ip_banning": True,
                },
                "storage": {
                    "type": "database",
                    "db_name": get_config("DB_NAME", "bed_layout_db"),
                },
            }
        )

    @staticmethod
    async def get_stats(request: web.Request) -> web.Response:
        """获取统计信息（需认证）

        参数:
            request: HTTP请求对象

        返回:
            web.Response: 统计信息响应
        """
        allowed, reason, status = await SecurityGuard.check_protection(request)
        match allowed:
            case False:
                return BedLayoutHandlers._error_response(
                    status, f"访问被拒绝: {reason}"
                )

        count = await BedLayoutImage.get_image_count()
        total_size = await BedLayoutImage.get_total_size()
        return web.json_response(
            {
                "storage_type": "database",
                "image_count": count,
                "total_size": total_size,
                "total_size_mb": round(total_size / 1024 / 1024, 2),
            }
        )
