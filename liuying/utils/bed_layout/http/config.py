"""
床图HTTP服务配置类

提供HTTP服务自身的配置访问：URL生成、IP白名单等。
网络服务已迁移至 nonebot2 框架统一端口，不再需要独立 HOST/PORT/SSL 配置。
"""
from typing import ClassVar
from urllib.parse import urlparse

import nonebot

from ..config import get_config
from .utils import BedLayoutHttpUtils

_DEFAULT_ALLOWED_IPS: list[str] = ["127.0.0.1", "::1"]

# 路由前缀，避免与其他模块路由冲突
ROUTE_PREFIX: str = "/liuying/bed_layout"


class BedLayoutHttpConfig:
    """
    床图HTTP服务配置类

    封装基于 nonebot2 统一端口的 URL 构建和上传白名单访问方法
    """

    # 本地存储图片的路由路径前缀
    IMAGE_ROUTE: ClassVar[str] = f"{ROUTE_PREFIX}/images"

    @classmethod
    def is_public_address_enabled(cls) -> bool:
        """是否开启公网地址"""
        return get_config("PUBLIC_ADDRESS_ENABLED", False)

    @classmethod
    def get_public_address_base_url(cls) -> str:
        """获取公网地址基础URL

        支持多种配置格式:
        - 完整URL: https://example.com 或 https://example.com:8443
        - 仅域名: example.com (自动添加协议和端口)
        - 域名+端口: example.com:9999 (自动添加协议)

        返回:
            str: 公网地址基础URL，未配置时返回本地服务基础URL
        """
        host = get_config("PUBLIC_ADDRESS_HOST", "")
        if not host:
            return cls.get_local_base_url()

        port = get_config("PUBLIC_ADDRESS_PORT")
        use_https = get_config("PUBLIC_ADDRESS_USE_HTTPS", False)

        parsed = urlparse(host)
        if parsed.scheme:
            host_part = parsed.hostname or parsed.netloc.split(":")[0]
            port_part = parsed.port or port
            if port_part is None:
                return f"{parsed.scheme}://{host_part}"
            return f"{parsed.scheme}://{host_part}:{port_part}"

        protocol = "https" if use_https else "http"
        if port is None:
            return f"{protocol}://{host}"
        return f"{protocol}://{host}:{port}"

    @classmethod
    def get_local_base_url(cls) -> str:
        """获取本地服务基础URL

        基于 nonebot2 框架的 HOST/PORT 配置构建本地服务URL

        返回:
            str: 本地服务基础URL
        """
        config = nonebot.get_driver().config
        host = str(config.host)
        port = int(config.port)
        # 监听 0.0.0.0 或 :: 时，客户端需通过本机回环地址访问
        if host in ("0.0.0.0", "::"):
            host = "127.0.0.1"
        return f"http://{host}:{port}"

    @classmethod
    def get_image_url(cls, filename: str) -> str:
        """获取本地存储图片的完整访问URL

        参数:
            filename: 图片文件名

        返回:
            str: 图片的完整访问URL
        """
        if cls.is_public_address_enabled():
            base = cls.get_public_address_base_url()
        else:
            base = cls.get_local_base_url()
        return f"{base}{cls.IMAGE_ROUTE}/{filename}"

    @classmethod
    def is_upload_ip_allowed(cls, ip_address: str) -> bool:
        """检查IP是否在允许上传的白名单中

        参数:
            ip_address: 客户端IP地址

        返回:
            bool: 允许返回True
        """
        ips = get_config("ALLOWED_UPLOAD_IPS", _DEFAULT_ALLOWED_IPS)
        if not isinstance(ips, list):
            ips = _DEFAULT_ALLOWED_IPS
        ip_address = BedLayoutHttpUtils.normalize_ip(ip_address)
        return ip_address in ips
