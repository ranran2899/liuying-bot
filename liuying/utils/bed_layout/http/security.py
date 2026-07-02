"""
安全模块：频率限制、IP封禁、认证验证

使用本地缓存系统持久化存储IP封禁信息，支持服务重启后恢复封禁状态。
"""

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import time

from aiohttp import web

from liuying.services.cache import Cache
from liuying.utils.apscheduler import task_manager
from liuying.utils.bed_layout.config import get_config
from liuying.utils.bed_layout.http.config import BedLayoutHttpConfig
from liuying.utils.bed_layout.http.utils import BedLayoutHttpUtils
from liuying.utils.log import logger

_RATE_LIMITS = {
    "global": {"requests": 100, "window": 60},
    "per_ip": {"requests": 30, "window": 60},
    "upload": {"requests": 5, "window": 60},
    "auth_fail": {"requests": 3, "window": 60},
}

_BAN_CONFIG = {
    "max_failures": 5,
    "ban_duration": 300,
    "cleanup_interval": 600,
}


@dataclass(slots=True)
class BanInfo:
    """IP封禁信息"""

    ban_until: float = 0.0
    """封禁结束时间"""
    failure_count: int = 0
    """失败次数"""


class _RateLimiter:
    """
    请求频率限制器

    使用滑动窗口算法实现多级别限流，
    通过定时任务定期清理不再活跃的记录防止内存泄漏
    """

    def __init__(self) -> None:
        self._global_requests: list[float] = []
        self._ip_requests: dict[str, list[float]] = defaultdict(list)
        self._endpoint_requests: dict[str, list[float]] = defaultdict(list)

    def _clean_old_requests(self, requests: list[float], window: float) -> list[float]:
        """清理过期的请求记录"""
        cutoff = time.time() - window
        idx = bisect_right(requests, cutoff)
        return requests[idx:]

    def cleanup_stale(self) -> None:
        """清理不再活跃的IP和接口记录，防止内存泄漏"""
        # 取最大窗口作为过期判断标准
        max_window = max(cfg["window"] for cfg in _RATE_LIMITS.values())
        cutoff = time.time() - max_window

        stale_ips = [
            ip
            for ip, reqs in self._ip_requests.items()
            if not reqs or reqs[-1] < cutoff
        ]
        for ip in stale_ips:
            del self._ip_requests[ip]

        stale_keys = [
            key
            for key, reqs in self._endpoint_requests.items()
            if not reqs or reqs[-1] < cutoff
        ]
        for key in stale_keys:
            del self._endpoint_requests[key]

    def is_rate_limited(
        self,
        ip: str = "",
        endpoint: str = "",
        limit_key: str = "per_ip",
    ) -> tuple[bool, str]:
        """
        检查是否触发频率限制

        参数:
            ip: 客户端IP
            endpoint: 接口路径
            limit_key: 使用的限制规则键名

        返回:
            tuple[bool, str]: (是否被限制, 原因)
        """
        now = time.time()

        limit = _RATE_LIMITS["global"]
        self._global_requests.append(now)
        self._global_requests = self._clean_old_requests(
            self._global_requests, limit["window"]
        )
        if len(self._global_requests) > limit["requests"]:
            return True, "服务器繁忙，请稍后重试"

        if ip:
            match limit_key:
                case "upload" | "auth_fail":
                    limit = _RATE_LIMITS[limit_key]
                case _:
                    limit = _RATE_LIMITS["per_ip"]
            self._ip_requests[ip].append(now)
            self._ip_requests[ip] = self._clean_old_requests(
                self._ip_requests[ip], limit["window"]
            )
            if len(self._ip_requests[ip]) > limit["requests"]:
                return True, (
                    f"请求过于频繁（{limit['requests']}次/{limit['window']}秒）"
                )

        if endpoint and endpoint in _RATE_LIMITS:
            limit = _RATE_LIMITS[endpoint]
            self._endpoint_requests[endpoint].append(now)
            self._endpoint_requests[endpoint] = self._clean_old_requests(
                self._endpoint_requests[endpoint], limit["window"]
            )
            if len(self._endpoint_requests[endpoint]) > limit["requests"]:
                return True, "该接口请求频繁，请稍后再试"

        return False, ""

    def record_failure(self, ip: str) -> None:
        """记录认证失败"""
        limit = _RATE_LIMITS["auth_fail"]
        key = f"{ip}_fail"
        self._endpoint_requests[key].append(time.time())
        self._endpoint_requests[key] = self._clean_old_requests(
            self._endpoint_requests[key], limit["window"]
        )


class _BanManager:
    """IP封禁管理器（使用缓存持久化）"""

    def __init__(self) -> None:
        self._cache = Cache[BanInfo]("BED_LAYOUT_BAN", result_type=BanInfo)
        self._memory_cache: dict[str, BanInfo] = {}

    async def _get_ban_info(self, ip: str) -> BanInfo:
        """获取IP的封禁信息（优先从缓存读取）"""
        ban_info = await self._cache.get(ip)
        if ban_info is not None:
            return ban_info
        if ip in self._memory_cache:
            return self._memory_cache[ip]
        return BanInfo()

    async def _save_ban_info(self, ip: str, ban_info: BanInfo) -> None:
        """保存IP的封禁信息到缓存"""
        self._memory_cache[ip] = ban_info
        if ban_info.ban_until > 0:
            expire = int(ban_info.ban_until - time.time()) + 60
        else:
            expire = _BAN_CONFIG["cleanup_interval"]
        await self._cache.set(ip, ban_info, expire=max(expire, 60))

    def cleanup_expired(self) -> None:
        """清理内存中过期的封禁记录"""
        now = time.time()
        expired_ips = [
            ip
            for ip, info in self._memory_cache.items()
            if info.ban_until > 0 and now > info.ban_until
        ]
        for ip in expired_ips:
            del self._memory_cache[ip]

    async def is_banned(self, ip: str) -> bool:
        """检查IP是否被封禁"""
        ban_info = await self._get_ban_info(ip)
        if ban_info.ban_until > 0:
            remaining = int(ban_info.ban_until - time.time())
            if remaining > 0:
                return True
            ban_info.ban_until = 0
            ban_info.failure_count = 0
            await self._save_ban_info(ip, ban_info)
        return False

    async def get_remaining_ban_time(self, ip: str) -> int:
        """获取剩余封禁时间"""
        ban_info = await self._get_ban_info(ip)
        if ban_info.ban_until <= 0:
            return 0
        return max(0, int(ban_info.ban_until - time.time()))

    async def record_failure(self, ip: str) -> tuple[bool, int]:
        """
        记录一次认证失败

        返回:
            tuple[bool, int]: (是否被封禁, 当前失败次数)
        """
        ban_info = await self._get_ban_info(ip)
        ban_info.failure_count += 1
        count = ban_info.failure_count

        if count >= _BAN_CONFIG["max_failures"]:
            ban_info.ban_until = time.time() + _BAN_CONFIG["ban_duration"]
            await self._save_ban_info(ip, ban_info)
            logger.error(
                f"IP已被临时封禁: {ip} | "
                f"连续{count}次失败 | "
                f"封禁时长: {_BAN_CONFIG['ban_duration']}秒",
                "BedLayoutServer",
            )
            return True, count

        await self._save_ban_info(ip, ban_info)
        return False, count

    async def reset_failures(self, ip: str) -> None:
        """重置指定IP的失败计数"""
        ban_info = await self._get_ban_info(ip)
        if ban_info.failure_count > 0:
            ban_info.failure_count = 0
            await self._save_ban_info(ip, ban_info)


class SecurityGuard:
    """
    安全防护类

    封装IP获取、API密钥验证、防暴力破解等安全功能
    """

    _rate_limiter = _RateLimiter()
    _ban_manager = _BanManager()

    @staticmethod
    def verify_api_key(request: web.Request) -> bool:
        """
        验证API密钥

        参数:
            request: HTTP请求对象

        返回:
            bool: 验证通过返回True
        """
        api_key = get_config("API_KEY", "")
        if not api_key:
            return True
        client_key = request.headers.get("X-API-Key", "")
        return hashlib.compare_digest(client_key, api_key)

    @classmethod
    async def check_protection(cls, request: web.Request) -> tuple[bool, str, int]:
        """
        综合检查防暴力破解机制

        检查顺序：
        1. IP是否被封禁
        2. 是否触发频率限制
        3. IP白名单 + API密钥验证

        参数:
            request: HTTP请求对象

        返回:
            tuple[bool, str, int]: (是否允许, 原因说明, HTTP状态码)
        """
        client_ip = BedLayoutHttpUtils.get_client_ip(request)

        match await cls._ban_manager.is_banned(client_ip):
            case True:
                remaining = await cls._ban_manager.get_remaining_ban_time(client_ip)
                logger.warning(
                    f"被封禁IP访问: {client_ip} | 剩余{remaining}秒",
                    "BedLayoutServer",
                )
                return False, f"IP已被临时封禁，剩余{remaining}秒", 403

        endpoint = request.path
        limited, reason = cls._rate_limiter.is_rate_limited(
            ip=client_ip,
            endpoint=endpoint,
        )
        match limited:
            case True:
                logger.warning(
                    f"触发频率限制: IP={client_ip}, 接口={endpoint}",
                    "BedLayoutServer",
                )
                return False, reason, 429

        match BedLayoutHttpConfig.is_upload_ip_allowed(client_ip):
            case False:
                await cls._ban_manager.record_failure(client_ip)
                cls._rate_limiter.record_failure(client_ip)
                logger.warning(f"未授权IP: {client_ip}", "BedLayoutServer")
                return False, f"IP {client_ip} 不在允许列表中", 403

        match cls.verify_api_key(request):
            case False:
                banned, fail_count = await cls._ban_manager.record_failure(client_ip)
                cls._rate_limiter.record_failure(client_ip)

                match banned:
                    case True:
                        return (
                            False,
                            f"连续{fail_count}次认证失败，"
                            f"IP已被临时封禁{_BAN_CONFIG['ban_duration']}秒",
                            403,
                        )

                logger.warning(
                    f"无效API密钥: IP={client_ip}, 失败次数={fail_count}",
                    "BedLayoutServer",
                )
                return (
                    False,
                    f"无效的API密钥"
                    f"（剩余尝试次数: {_BAN_CONFIG['max_failures'] - fail_count}）",
                    401,
                )
            case True:
                await cls._ban_manager.reset_failures(client_ip)
                return True, "", 200

    @classmethod
    def cleanup(cls) -> None:
        """清理限流器和封禁管理器中的过期记录"""
        cls._rate_limiter.cleanup_stale()
        cls._ban_manager.cleanup_expired()


@task_manager.interval_task(
    "bed_layout_security_cleanup",
    minutes=5,
    group="bed_layout",
    name="床图安全模块过期记录清理",
    description="定期清理限流器和封禁管理器中的过期记录，防止内存泄漏",
)
async def _security_cleanup():
    """定时清理安全模块的过期记录"""
    SecurityGuard.cleanup()
