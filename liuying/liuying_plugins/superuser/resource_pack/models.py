from pydantic import BaseModel


class ResourcePackInfo(BaseModel):
    """资源包索引信息"""

    name: str
    """资源包名称"""
    version: str
    """资源包版本号"""
    download_url: str
    """压缩包下载链接"""
    description: str | None = None
    """资源包说明"""
