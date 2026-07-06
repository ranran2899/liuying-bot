"""
床图HTTP服务配置类

提供HTTP服务自身的配置访问：URL生成、HTTPS/SSL、IP白名单等
"""

from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse

from liuying.configs.path_config import DATA_PATH

from ..config import get_config
from .utils import BedLayoutHttpUtils

_DEFAULT_ALLOWED_IPS: list[str] = ["127.0.0.1", "::1"]


class BedLayoutHttpConfig:
    """
    床图HTTP服务配置类

    封装HTTP服务自身的配置访问方法
    """

    SSL_DIR: ClassVar[Path] = DATA_PATH / "bed_layout" / "ssl"

    # region URL 构建

    @classmethod
    def get_base_url(cls) -> str:
        """获取服务基础URL"""
        protocol = "https" if cls.is_https_enabled() else "http"
        host = get_config("HOST", "127.0.0.1")
        port = get_config("PORT", 8088)
        return f"{protocol}://{host}:{port}"

    @classmethod
    def is_https_enabled(cls) -> bool:
        """是否启用HTTPS"""
        return get_config("ENABLE_HTTPS", False)

    @classmethod
    def is_public_address_enabled(cls) -> bool:
        """是否开启公网地址"""
        return get_config("PUBLIC_ADDRESS_ENABLED", False)

    @classmethod
    def get_public_address_base_url(cls) -> str:
        """
        获取公网地址基础URL

        支持多种配置格式:
        - 完整URL: https://example.com 或 https://example.com:8443
        - 仅域名: example.com (自动添加协议和端口)
        - 域名+端口: example.com:9999 (自动添加协议)
        """
        host = get_config("PUBLIC_ADDRESS_HOST", "")
        if not host:
            return cls.get_base_url()

        port = get_config("PUBLIC_ADDRESS_PORT")
        use_https = get_config("PUBLIC_ADDRESS_USE_HTTPS", False)

        parsed = urlparse(host)

        if parsed.scheme:
            host_part = parsed.hostname or parsed.netloc.split(":")[0]
            port_part = parsed.port or port
            match port_part:
                case None:
                    return f"{parsed.scheme}://{host_part}"
                case _:
                    return f"{parsed.scheme}://{host_part}:{port_part}"

        protocol = "https" if use_https else "http"
        match port:
            case None:
                default_port = 443 if use_https else 80
                match default_port:
                    case 80 | 443:
                        return f"{protocol}://{host}"
                    case _:
                        return f"{protocol}://{host}:{default_port}"
            case _:
                return f"{protocol}://{host}:{port}"

    @classmethod
    def get_server_host(cls) -> str:
        """获取服务监听地址"""
        return get_config("HOST", "127.0.0.1")

    @classmethod
    def get_server_port(cls) -> int:
        """获取服务监听端口"""
        return get_config("PORT", 8088)

    @classmethod
    def get_image_url(cls, filename: str) -> str:
        """
        获取本地存储图片的完整访问URL

        参数:
            filename: 图片文件名

        返回:
            str: 图片的完整访问URL
        """
        if cls.is_public_address_enabled():
            base = cls.get_public_address_base_url()
        else:
            base = cls.get_base_url()
        return f"{base}/images/{filename}"

    # endregion

    # region SSL

    @classmethod
    def ensure_ssl_dir(cls) -> None:
        """确保SSL证书目录存在"""
        cls.SSL_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_ssl_cert_file(cls) -> str:
        """获取SSL证书文件路径"""
        cert = get_config("SSL_CERT_FILE", "")
        return cert or str(cls.SSL_DIR / "cert.pem")

    @classmethod
    def get_ssl_key_file(cls) -> str:
        """获取SSL私钥文件路径"""
        key = get_config("SSL_KEY_FILE", "")
        return key or str(cls.SSL_DIR / "key.pem")

    # endregion

    # region IP白名单

    @classmethod
    def is_upload_ip_allowed(cls, ip_address: str) -> bool:
        """
        检查IP是否在允许上传的白名单中

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

    # endregion
