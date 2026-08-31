"""
存储提供者统一接口契约与注册中心

定义所有存储提供者（本地与云存储）必须遵循的统一接口标准，
并提供基于装饰器的主动注册机制。

扩展自定义存储提供者：

    from liuying.utils.bed_layout.base import (
        ProviderRegistry,
        StorageProvider,
    )

    @ProviderRegistry.register("my_storage")
    class MyStorageProvider(StorageProvider):
        ...  # 实现全部抽象方法

    # DEFAULT_STORAGE 配置为 "my_storage" 即可启用，
    # 或在调用 BedLayout.upload 等方法时显式传入 storage_type="my_storage"

注意：自定义提供者所在模块必须在被使用前完成导入，
装饰器才会触发注册（内置提供者由 providers/__init__.py 统一导入）。
"""
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, ClassVar

from liuying.utils.enum import StorageType
from liuying.utils.http.http_utils import AsyncHttpx
from liuying.utils.log import logger

from .config import get_provider_config
from .interfaces import generate_filename, validate_extension


class StorageProvider(ABC):
    """存储提供者抽象基类

    所有具体存储实现（本地数据库、各云存储、自定义存储）
    都必须继承本类并实现全部抽象方法，确保对外接口一致。
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """提供者名称，用于日志记录"""

    @abstractmethod
    async def upload(
        self,
        file_data: bytes,
        filename: str,
        content_type: str | None = None,
        **kwargs: Any,
    ) -> str:
        """上传文件到存储

        参数:
            file_data: 文件二进制数据
            filename: 文件名
            content_type: MIME类型
            **kwargs: 扩展元数据（如 source/category/tags/original_url）

        返回:
            str: 文件访问URL
        """

    @abstractmethod
    async def delete(self, filename: str) -> bool:
        """删除存储中的文件

        参数:
            filename: 文件名

        返回:
            bool: 删除成功返回True
        """

    @abstractmethod
    async def get_url(self, filename: str) -> str:
        """获取文件访问URL

        参数:
            filename: 文件名

        返回:
            str: 文件访问URL
        """

    @abstractmethod
    def is_configured(self) -> bool:
        """检查当前提供者是否已正确配置"""

    async def download_image(
        self,
        url: str,
        filename: str | None = None,
        extension: str = ".png",
        content_type: str | None = None,
        timeout: float = 30.0,
        **kwargs: Any,
    ) -> tuple[str | None, str]:
        """从URL下载图片并保存到当前存储

        参数:
            url: 图片URL
            filename: 自定义文件名，不指定则自动生成UUID
            extension: 图片扩展名，默认.png
            content_type: MIME类型
            timeout: 请求超时时间（秒）
            **kwargs: 上传时透传的扩展元数据

        返回:
            tuple[str | None, str]: (图片访问URL, 错误信息)，
            成功时错误信息为空字符串
        """
        validate_extension(extension)
        filename = generate_filename(filename, extension)

        try:
            file_data = await AsyncHttpx.get_content(
                url,
                timeout=timeout,
                follow_redirects=True,
            )
        except Exception as e:
            error_msg = f"下载图片失败: {e}"
            self._log_error("下载", url, e)
            return None, error_msg

        try:
            url_result = await self.upload(
                file_data=file_data,
                filename=filename,
                content_type=content_type,
                original_url=url,
                **kwargs,
            )
        except Exception as e:
            error_msg = f"保存图片失败: {e}"
            self._log_error("保存", filename, e)
            return None, error_msg

        logger.success(f"下载并保存图片成功: {url_result}", self.provider_name)
        return url_result, ""

    def _log_error(self, action: str, filename: str, error: Exception) -> None:
        """记录操作错误日志

        参数:
            action: 操作类型描述
            filename: 文件名
            error: 异常对象
        """
        logger.error(f"{action}图片失败: {filename}", self.provider_name, e=error)


class CloudStorageProvider(StorageProvider):
    """云存储提供者模板基类

    统一封装配置读取、必要项校验与客户端懒加载，
    子类只需声明 _config_key 与 _required_fields，并实现
    _create_client 与 upload/delete/get_url 三个具体操作。
    """

    _config_key: ClassVar[str]
    """该云存储在床图模块中的配置键名"""
    _required_fields: ClassVar[tuple[str, ...]]
    """配置字典中必须非空的字段名"""

    _client: ClassVar[object | None] = None

    @classmethod
    def _get_config(cls) -> dict[str, Any]:
        """读取该云存储的配置字典"""
        return get_provider_config(cls._config_key)

    @property
    def _bucket(self) -> str:
        """配置的存储桶名称"""
        return self._get_config().get("bucket_name", "")

    @classmethod
    def _get_client(cls) -> object:
        """获取存储客户端实例（懒加载，仅初始化一次）"""
        if cls._client is None:
            cls._client = cls._create_client()
        return cls._client

    @classmethod
    @abstractmethod
    def _create_client(cls) -> object:
        """创建云存储客户端实例（由子类实现具体初始化逻辑）"""

    @staticmethod
    def _strip_scheme(endpoint: str) -> str:
        """去除endpoint中的协议前缀，用于拼接访问URL"""
        return endpoint.removeprefix("https://").removeprefix("http://")

    def is_configured(self) -> bool:
        """检查必要配置项是否全部非空"""
        config = self._get_config()
        return all(config.get(field) for field in self._required_fields)


class ProviderRegistry:
    """存储提供者注册中心

    维护存储类型标识到提供者类的映射，
    内置与自定义提供者均通过 register 装饰器主动注册。
    """

    _registry: ClassVar[dict[str, type[StorageProvider]]] = {}

    @classmethod
    def register[P: StorageProvider](
        cls, storage_type: str
    ) -> Callable[[type[P]], type[P]]:
        """注册存储提供者的装饰器

        参数:
            storage_type: 存储类型标识（如 StorageType.TENCENT 或自定义字符串）

        返回:
            Callable: 装饰器，原样返回被注册的提供者类
        """

        def decorator(provider_cls: type[P]) -> type[P]:
            cls._registry[str(storage_type)] = provider_cls
            return provider_cls

        return decorator

    @classmethod
    def get(cls, storage_type: StorageType | str) -> StorageProvider | None:
        """获取指定类型的存储提供者实例

        参数:
            storage_type: 存储类型标识

        返回:
            StorageProvider | None: 提供者实例，未注册或未配置返回None
        """
        provider_cls = cls._registry.get(str(storage_type))
        if provider_cls is None:
            return None
        provider = provider_cls()
        return provider if provider.is_configured() else None
