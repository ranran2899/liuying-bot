"""
存储提供者管理

统一管理本地存储和云存储提供者的实例化和缓存。
"""
from typing import ClassVar

from liuying.utils.enum import StorageType

from .providers.aliyun import AliyunOssProvider
from .providers.baidu import BaiduBosProvider
from .providers.base import CloudStorageProvider
from .providers.huawei import HuaweiObsProvider
from .providers.local import LocalStorageProvider
from .providers.tencent import TencentCosProvider

# 存储类型到提供者类的映射表
_PROVIDER_CLASS_MAP: dict[StorageType, type[CloudStorageProvider]] = {
    StorageType.LOCAL: LocalStorageProvider,
    StorageType.TENCENT: TencentCosProvider,
    StorageType.BAIDU: BaiduBosProvider,
    StorageType.ALIYUN: AliyunOssProvider,
    StorageType.HUAWEI: HuaweiObsProvider,
}


class ProviderManager:
    """
    存储提供者管理类

    管理各存储提供者（本地和云端）的实例化和缓存。
    所有调用方通过本类获取存储提供者实例，避免直接依赖具体实现。
    """

    _providers: ClassVar[dict[StorageType, CloudStorageProvider]] = {}

    @classmethod
    def get_provider(
        cls, storage_type: StorageType
    ) -> CloudStorageProvider | None:
        """获取指定类型的存储提供者

        参数:
            storage_type: 存储类型

        返回:
            CloudStorageProvider | None: 存储提供者实例，未配置返回None
        """
        if storage_type not in cls._providers:
            provider_class = _PROVIDER_CLASS_MAP.get(storage_type)
            if provider_class is None:
                return None

            provider = provider_class()
            if provider.is_configured():
                cls._providers[storage_type] = provider
            else:
                return None

        return cls._providers.get(storage_type)

    @classmethod
    def clear_cache(cls) -> None:
        """清除提供者缓存"""
        cls._providers.clear()
