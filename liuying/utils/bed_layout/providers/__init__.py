"""
存储提供者模块

统一导出本地存储与云存储提供者实现。
接口契约与注册中心见顶包 base 模块。
模块导入时各提供者通过 ProviderRegistry.register 装饰器完成主动注册。
"""
from ..base import CloudStorageProvider, ProviderRegistry, StorageProvider
from .aliyun import AliyunOssProvider
from .baidu import BaiduBosProvider
from .huawei import HuaweiObsProvider
from .local import LocalStorageProvider
from .tencent import TencentCosProvider

__all__ = [
    "AliyunOssProvider",
    "BaiduBosProvider",
    "CloudStorageProvider",
    "HuaweiObsProvider",
    "LocalStorageProvider",
    "ProviderRegistry",
    "StorageProvider",
    "TencentCosProvider",
]
