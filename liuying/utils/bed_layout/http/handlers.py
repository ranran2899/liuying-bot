"""
请求处理器模块

基于 FastAPI 路由封装HTTP请求处理和响应构建。
所有处理器通过 APIRouter 注册到 nonebot2 框架统一端口。
"""
import mimetypes

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from liuying.models._bot import BedLayoutImage
from liuying.utils.enum import StorageType
from liuying.utils.log import logger

from ..base import ProviderRegistry
from ..config import get_config
from ..interfaces import generate_filename, validate_extension
from .security import SecurityGuard
from .utils import BedLayoutHttpUtils

# 图片响应安全头
_SECURITY_HEADERS = {
    "Cache-Control": "public, max-age=86400",
    "Access-Control-Allow-Origin": "*",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
}

# 床图HTTP路由器，挂载到 nonebot2 统一端口
router: APIRouter = APIRouter()


def _image_response(data: bytes, content_type: str) -> Response:
    """构建图片响应（带安全头）"""
    return Response(
        content=data,
        media_type=content_type,
        headers=_SECURITY_HEADERS,
    )


@router.get("/images/{filename:path}", name="bed_layout_serve_image")
async def serve_image(filename: str) -> Response:
    """提供图片访问服务（公开只读接口）

    参数:
        filename: 图片文件名

    返回:
        Response: 图片响应或错误响应
    """
    if not filename:
        raise HTTPException(status_code=400, detail="缺少文件名")

    image = await BedLayoutImage.get_image_by_filename(filename)
    if image is None:
        raise HTTPException(status_code=404, detail="图片不存在")

    content_type = image.content_type or "application/octet-stream"
    return _image_response(image.file_data, content_type)


@router.post("/upload", name="bed_layout_upload_image")
async def upload_image(
    request: Request,
    image: UploadFile = File(..., description="上传的图片文件"),
) -> JSONResponse:
    """处理图片上传（需认证的写操作接口）

    参数:
        request: FastAPI 请求对象
        image: 上传的图片文件

    返回:
        JSONResponse: 上传结果响应
    """
    await SecurityGuard.check_protection(request)

    original_filename = image.filename or ""
    ext = (
        "." + original_filename.rsplit(".", 1)[-1].lower()
        if "." in original_filename
        else ""
    )

    try:
        validate_extension(ext)
    except ValueError:
        client_ip = BedLayoutHttpUtils.get_client_ip(request)
        logger.warning(
            f"不支持的文件类型: {ext} | IP={client_ip}",
            "BedLayoutServer",
        )
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {ext}",
        ) from None

    max_size = get_config("MAX_FILE_SIZE", 10485760)
    file_data = await image.read()
    size = len(file_data)

    if size > max_size:
        client_ip = BedLayoutHttpUtils.get_client_ip(request)
        logger.warning(
            f"文件大小超限: {size}>{max_size}字节 | IP={client_ip}",
            "BedLayoutServer",
        )
        raise HTTPException(
            status_code=413,
            detail=f"文件大小超过限制 ({max_size // 1024 // 1024}MB)",
        )

    filename = generate_filename(None, ext)
    content_type, _ = mimetypes.guess_type(original_filename)
    # 经注册中心获取本地提供者，避免直接依赖 providers 包形成循环导入
    provider = ProviderRegistry.get(StorageType.LOCAL)
    url = await provider.upload(file_data, filename, content_type)

    return JSONResponse(
        {
            "success": True,
            "filename": filename,
            "original_filename": original_filename,
            "url": url,
            "size": size,
            "storage": "local",
        }
    )


@router.get("/health", name="bed_layout_health_check")
async def health_check() -> JSONResponse:
    """健康检查接口（公开只读）

    返回:
        JSONResponse: 健康状态响应
    """
    return JSONResponse(
        {
            "status": "healthy",
            "service": "bed_layout",
            "version": "3.1.0",
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


@router.get("/stats", name="bed_layout_get_stats")
async def get_stats(request: Request) -> JSONResponse:
    """获取统计信息（需认证）

    参数:
        request: FastAPI 请求对象

    返回:
        JSONResponse: 统计信息响应
    """
    await SecurityGuard.check_protection(request)

    count = await BedLayoutImage.get_image_count()
    total_size = await BedLayoutImage.get_total_size()
    return JSONResponse(
        {
            "storage_type": "database",
            "image_count": count,
            "total_size": total_size,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
        }
    )
