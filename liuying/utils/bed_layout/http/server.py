"""
本地床图HTTP服务器
"""

import time
from typing import ClassVar, Self

from aiohttp import web

from liuying.utils.bed_layout.http.config import BedLayoutHttpConfig
from liuying.utils.bed_layout.http.handlers import BedLayoutHandlers
from liuying.utils.bed_layout.http.utils import BedLayoutHttpUtils
from liuying.utils.http import SSLUtils
from liuying.utils.log import logger
from liuying.utils.manager.priority_manager import PriorityLifecycle


class BedLayoutServer:
    """
    本地床图HTTP服务器

    安全防护：IP封禁、频率限制、IP白名单 + API密钥双重认证
    """

    _instance: ClassVar["BedLayoutServer | None"] = None
    _runner: ClassVar[web.AppRunner | None] = None
    _site: ClassVar[web.TCPSite | None] = None

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self.app = web.Application(middlewares=[self._security_middleware])
            self._setup_routes()

    def _setup_routes(self) -> None:
        """设置路由"""
        h = BedLayoutHandlers
        self.app.router.add_get("/images/{filename:.*}", h.serve_image)
        self.app.router.add_get("/health", h.health_check)
        self.app.router.add_post("/upload", h.upload_image)
        self.app.router.add_get("/stats", h.get_stats)

    @web.middleware
    async def _security_middleware(
        self,
        request: web.Request,
        handler: web.RequestHandler,
    ) -> web.StreamResponse:
        """安全中间件：异常捕获和日志"""
        start_time = time.time()
        client_ip = BedLayoutHttpUtils.get_client_ip(request)

        try:
            return await handler(request)
        except web.HTTPException:
            raise
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            logger.error(
                f"请求处理异常: [{request.method}] {request.path} | "
                f"IP={client_ip} | 耗时={duration:.2f}ms | 错误={e}",
                command="BedLayoutServer",
                e=e,
            )
            raise

    async def start(self) -> None:
        """启动HTTP/HTTPS服务器"""
        BedLayoutHttpConfig.ensure_ssl_dir()

        self._runner = web.AppRunner(self.app)
        await self._runner.setup()

        ssl_context = None
        if BedLayoutHttpConfig.is_https_enabled():
            ssl_context = SSLUtils.create_ssl_context(
                cert_path=BedLayoutHttpConfig.get_ssl_cert_file(),
                key_path=BedLayoutHttpConfig.get_ssl_key_file(),
                auto_generate=True,
                common_name="localhost",
                organization="BedLayout",
            )

        self._site = web.TCPSite(
            self._runner,
            BedLayoutHttpConfig.get_server_host(),
            BedLayoutHttpConfig.get_server_port(),
            ssl_context=ssl_context,
        )
        await self._site.start()

        protocol = "HTTPS" if BedLayoutHttpConfig.is_https_enabled() else "HTTP"
        logger.info(
            f"床图服务已启动 | "
            f"{BedLayoutHttpConfig.get_base_url()} | "
            f"{protocol} | 数据库存储",
            "BedLayoutServer",
        )

    async def stop(self) -> None:
        """停止HTTP服务器"""
        if self._site:
            await self._site.stop()
            self._site = None

        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    @classmethod
    def get_server(cls) -> Self:
        """获取床图服务器单例"""
        return cls()


@PriorityLifecycle.on_startup(priority=2)
async def _start_server():
    """在Bot启动时自动启动床图服务器"""
    await BedLayoutServer.get_server().start()


@PriorityLifecycle.on_shutdown(priority=2)
async def _stop_server():
    """在Bot关闭时自动停止床图服务器"""
    await BedLayoutServer.get_server().stop()
