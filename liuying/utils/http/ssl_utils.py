"""SSL证书工具模块

提供自签名SSL证书生成和管理功能
"""
from datetime import UTC, datetime, timedelta
import ipaddress
from pathlib import Path
import ssl
from typing import ClassVar

from liuying.utils.log import logger

try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    _HAS_CRYPTOGRAPHY = True
except ImportError:
    _HAS_CRYPTOGRAPHY = False


class SSLUtils:
    """SSL证书工具类

    提供自签名证书生成、SSL上下文创建以及证书信息查询等功能。
    """

    _HAS_CRYPTO: ClassVar[bool] = _HAS_CRYPTOGRAPHY

    @classmethod
    def _check_cryptography_installed(cls) -> bool:
        """检查cryptography库是否已安装

        返回:
            bool: 是否已安装
        """
        if not cls._HAS_CRYPTO:
            logger.error(
                "SSL证书功能需要安装 cryptography 库，请运行: "
                "pip install cryptography",
                command="SSLUtils",
            )
            return False
        return True

    @classmethod
    def generate_self_signed_cert(
        cls,
        cert_path: str | Path,
        key_path: str | Path,
        common_name: str = "localhost",
        organization: str = "SelfSigned",
        country: str = "CN",
        state: str = "Local",
        locality: str = "Local",
        validity_days: int = 365,
        key_size: int = 2048,
        additional_sans: list[str] | None = None,
    ) -> bool:
        """生成自签名SSL证书

        参数:
            cert_path: 证书文件保存路径
            key_path: 私钥文件保存路径
            common_name: 证书通用名称(CN)
            organization: 组织名称
            country: 国家代码
            state: 省份/州
            locality: 城市
            validity_days: 证书有效期(天)
            key_size: 密钥大小(位)
            additional_sans: 额外的Subject Alternative Names

        返回:
            bool: 是否生成成功
        """
        if not cls._check_cryptography_installed():
            return False

        try:
            cert_path = Path(cert_path)
            key_path = Path(key_path)

            logger.info("正在生成SSL私钥...", command="SSLUtils")
            key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=key_size,
                backend=default_backend()
            )

            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, country),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, state),
                x509.NameAttribute(NameOID.LOCALITY_NAME, locality),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
                x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            ])

            san_list = [
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            ]

            if additional_sans:
                for san in additional_sans:
                    try:
                        ip = ipaddress.ip_address(san)
                        san_list.append(x509.IPAddress(ip))
                    except ValueError:
                        san_list.append(x509.DNSName(san))

            logger.info("正在生成SSL证书...", command="SSLUtils")
            now = datetime.now(UTC)
            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now)
                .not_valid_after(now + timedelta(days=validity_days))
                .add_extension(
                    x509.SubjectAlternativeName(san_list),
                    critical=False,
                )
                .sign(key, hashes.SHA256(), default_backend())
            )

            cert_path.parent.mkdir(parents=True, exist_ok=True)

            logger.info("正在保存SSL私钥...", command="SSLUtils")
            with open(key_path, "wb") as f:
                f.write(key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()
                ))

            logger.info("正在保存SSL证书...", command="SSLUtils")
            with open(cert_path, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))

            logger.info(
                f"SSL证书生成成功: {cert_path} (有效期: {validity_days}天)",
                command="SSLUtils",
            )
            return True

        except Exception as e:
            logger.error(f"生成SSL证书失败: {e}", command="SSLUtils", e=e)
            return False

    @classmethod
    def create_ssl_context(
        cls,
        cert_path: str | Path,
        key_path: str | Path,
        auto_generate: bool = True,
        **generate_kwargs
    ) -> ssl.SSLContext | None:
        """创建SSL上下文

        参数:
            cert_path: 证书文件路径
            key_path: 私钥文件路径
            auto_generate: 证书不存在时是否自动生成
            **generate_kwargs: 传递给generate_self_signed_cert的参数

        返回:
            ssl.SSLContext | None: SSL上下文对象，失败返回None
        """
        cert_path = Path(cert_path)
        key_path = Path(key_path)

        if not cert_path.exists() or not key_path.exists():
            if auto_generate:
                logger.info(
                    "SSL证书不存在，正在自动生成...", command="SSLUtils"
                )
                if not cls.generate_self_signed_cert(
                    cert_path, key_path, **generate_kwargs
                ):
                    return None
            else:
                logger.error("SSL证书文件不存在", command="SSLUtils")
                return None

        try:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(str(cert_path), str(key_path))
            logger.info("SSL证书加载成功", command="SSLUtils")
            return ssl_context
        except Exception as e:
            logger.error(f"加载SSL证书失败: {e}", command="SSLUtils", e=e)
            return None

    @classmethod
    def get_cert_info(cls, cert_path: str | Path) -> dict | None:
        """获取证书信息

        参数:
            cert_path: 证书文件路径

        返回:
            dict | None: 证书信息字典，失败返回None
        """
        if not cls._check_cryptography_installed():
            return None

        try:
            cert_path = Path(cert_path)
            if not cert_path.exists():
                return None

            with open(cert_path, "rb") as f:
                cert_data = f.read()

            cert = x509.load_pem_x509_certificate(cert_data, default_backend())

            return {
                "subject": cert.subject.rfc4514_string(),
                "issuer": cert.issuer.rfc4514_string(),
                "not_valid_before": cert.not_valid_before_utc,
                "not_valid_after": cert.not_valid_after_utc,
                "serial_number": cert.serial_number,
            }
        except Exception as e:
            logger.error(f"读取证书信息失败: {e}", command="SSLUtils", e=e)
            return None

    @classmethod
    def is_cert_valid(cls, cert_path: str | Path) -> bool:
        """检查证书是否有效（未过期）

        参数:
            cert_path: 证书文件路径

        返回:
            bool: 证书是否有效
        """
        info = cls.get_cert_info(cert_path)
        if not info:
            return False
        now = datetime.now(UTC)
        before = info["not_valid_before"].replace(tzinfo=None)
        after = info["not_valid_after"].replace(tzinfo=None)
        return before <= now.replace(tzinfo=None) <= after
