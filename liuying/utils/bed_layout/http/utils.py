"""
床图HTTP服务工具类

提供与HTTP请求处理相关的纯工具方法，不直接访问配置
"""

from aiohttp import web


class BedLayoutHttpUtils:
    """
    床图HTTP服务工具类

    封装不依赖配置的HTTP辅助方法
    """

    @staticmethod
    def get_client_ip(request: web.Request) -> str:
        """
        获取客户端真实IP地址

        优先从反向代理头中提取真实IP，回退到连接远程地址。

        参数:
            request: HTTP请求对象

        返回:
            str: 客户端IP地址
        """
        match request.headers:
            case {"X-Forwarded-For": forwarded}:
                return forwarded.split(",")[0].strip()
            case {"X-Real-IP": real_ip}:
                return real_ip.strip()
            case _:
                return request.remote or "unknown"

    @staticmethod
    def normalize_ip(ip_address: str) -> str:
        """
        规范化IPv4映射的IPv6地址

        参数:
            ip_address: 原始IP地址

        返回:
            str: 规范化后的IP地址
        """
        return ip_address.removeprefix("::ffff:")
