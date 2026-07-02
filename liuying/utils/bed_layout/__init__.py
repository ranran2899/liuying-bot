"""
本地床图模块

提供本地HTTP服务器用于图片存储和访问，支持数据库存储和云存储。

公共接口层：
- BedLayout: 床图核心业务API（上传/删除/获取URL等）
- BedLayoutServer: 本地HTTP服务器
- BedLayoutUtils: 定时删除任务管理工具
- StorageType: 存储类型枚举
- LocalStorageProvider: 本地数据库存储提供者（供需要本地直连的调用方使用）
- ImageInfo/StorageStats: 元信息载体
- convert_image_format/resize_image: 图片格式转换与缩放工具
"""
from liuying.utils.enum import StorageType

from .api import BedLayout
from .http import BedLayoutServer
from .interfaces import ImageInfo, StorageStats
from .provider_manager import ProviderManager
from .providers.local import LocalStorageProvider
from .utils import BedLayoutUtils, convert_image_format, resize_image

__all__ = [
    "BedLayout",
    "BedLayoutServer",
    "BedLayoutUtils",
    "ImageInfo",
    "LocalStorageProvider",
    "ProviderManager",
    "StorageStats",
    "StorageType",
    "convert_image_format",
    "resize_image",
]
