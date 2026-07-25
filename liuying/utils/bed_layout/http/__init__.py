"""
床图HTTP服务模块

通过 nonebot2 框架统一端口提供图片存储和访问HTTP接口
"""

from .server import BedLayoutServer

__all__ = ["BedLayoutServer"]
