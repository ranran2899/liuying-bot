"""
本地床图模块

提供本地HTTP服务用于图片存储和访问，支持数据库存储、云存储和自定义注册存储。
网络服务通过 nonebot2 框架统一端口提供，不再启动独立服务器。

公共接口层：
- BedLayout: 床图核心业务API（上传/删除/获取URL等）
- base: 存储契约与注册中心
  - StorageProvider: 存储提供者统一接口契约
  - CloudStorageProvider: 云存储提供者模板基类
  - ProviderRegistry: 注册中心（自定义存储通过其 register 装饰器注册）
- providers/: 内置存储提供者实现（local/aliyun/baidu/huawei/tencent）
- http/: nonebot2 统一端口承载的HTTP服务（路由/安全/URL构建）
- BedLayoutServer: HTTP路由注册器（挂载至nonebot2统一端口）
- BedLayoutUtils: 定时删除任务管理工具
- StorageType: 内置存储类型枚举
- LocalStorageProvider: 本地数据库存储提供者（供需要本地直连的调用方使用）
"""
from liuying.utils.enum import StorageType

from .api import BedLayout
from .base import CloudStorageProvider, ProviderRegistry, StorageProvider
from .http import BedLayoutServer
from .providers import LocalStorageProvider
from .utils import BedLayoutUtils

__all__ = [
    "BedLayout",
    "BedLayoutServer",
    "BedLayoutUtils",
    "CloudStorageProvider",
    "LocalStorageProvider",
    "ProviderRegistry",
    "StorageProvider",
    "StorageType",
]
