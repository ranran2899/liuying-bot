"""流萤 WebUI 扩展注册接口

供其他插件开发者将自定义页面与 API 注册进流萤 WebUI，
无需修改 web_ui 插件本体代码。

在插件模块顶层调用单例 registry 的注册方法即可，
所有注册在 WebUI 启动时统一生效。

使用示例::

    from pathlib import Path

    from fastapi import APIRouter

    from liuying.liuying_plugins.web_ui.registry import registry

    # 1. 注册后端 API（挂载到 /liuying/api 下）
    demo_router = APIRouter(prefix="/demo")

    @demo_router.get("/hello")
    async def hello():
        return {"message": "hello"}

    registry.register_api(demo_router)

    # 2. 注册插件自带静态资源目录（挂载到站点根路径下，如 /demo_ext/xxx.js）
    registry.register_static("/demo_ext", Path(__file__).parent / "static")

    # 3. 注册侧边栏页面（js 指向前端页面模块地址，导出 default 异步渲染函数）
    registry.register_page(
        module="demo",
        name="示例页面",
        path="/demo",
        icon="plugin",
        js="/demo_ext/page.js",
    )

页面模块需导出 default 异步函数，渲染到 #app-content::

    export default async function render(query) {
      document.getElementById('app-content').innerHTML = '<div>示例</div>';
    }
"""

from pathlib import Path

from fastapi import APIRouter

from liuying.utils.log import logger

from .api.menu.data_source import default_menus, menu_manage
from .api.menu.model import MenuItem
from .public import extra_version_dirs


class WebUiRegistry:
    """WebUI 扩展注册器

    收集外部插件注册的页面与路由，WebUI 启动时统一挂载。
    """

    def __init__(self) -> None:
        self.api_routers: list[APIRouter] = []
        """外部插件注册的 API 路由，启动时挂载到 /liuying/api 下"""
        self.ws_routers: list[APIRouter] = []
        """外部插件注册的 WebSocket 路由，启动时挂载到 /liuying/socket 下"""
        self.static_mounts: list[tuple[str, Path]] = []
        """外部插件注册的静态资源目录（挂载路径, 本地目录）"""
        self._registered_modules: set[str] = set()
        """已注册外部页面的 module 标识，用于菜单同步清理"""

    def register_api(self, router: APIRouter) -> None:
        """注册后端 API 路由到 WebUI

        参数:
            router: FastAPI 路由对象，挂载到 /liuying/api 下
        """
        self.api_routers.append(router)
        logger.debug(f"外部插件注册 API 路由: {router.prefix}", command="WebUI")

    def register_ws_router(self, router: APIRouter) -> None:
        """注册 WebSocket 路由到 WebUI

        参数:
            router: FastAPI 路由对象，挂载到 /liuying/socket 下
        """
        self.ws_routers.append(router)
        logger.debug(f"外部插件注册 WS 路由: {router.prefix}", command="WebUI")

    def register_static(self, mount_path: str, directory: Path) -> None:
        """注册插件自带的静态资源目录

        参数:
            mount_path: 站点根路径下的挂载路径，如 "/demo_ext"
            directory: 本地静态资源目录
        """
        if not mount_path.startswith("/"):
            mount_path = f"/{mount_path}"
        if any(path == mount_path for path, _ in self.static_mounts):
            return
        self.static_mounts.append((mount_path, directory))
        # 插件静态目录纳入版本指纹，资源更新后重启机器人缓存自动失效
        if directory not in extra_version_dirs:
            extra_version_dirs.append(directory)
        logger.debug(
            f"外部插件注册静态资源: {mount_path} -> {directory}", command="WebUI"
        )

    def register_page(
        self,
        module: str,
        name: str,
        path: str,
        icon: str = "plugin",
        js: str = "",
        css: str | list[str] = "",
        default: bool = False,
    ) -> None:
        """注册侧边栏页面菜单项

        参数:
            module: 模块唯一标识
            name: 菜单显示名称
            path: 前端哈希路由，如 "/demo"
            icon: 图标名（使用内置图标，未知图标回退为 plugin）
            js: 前端页面模块地址（如 "/demo_ext/js/page.js"），导出 default
                异步渲染函数；为空则表示路由由前端内置页面实现
            css: 前端页面样式表地址，单个字符串或列表均可
                （如 "/demo_ext/css/page.css"），加载菜单时自动注入
            default: 是否设为默认页
        """
        self._registered_modules.add(module)
        # 样式表地址归一化为列表
        css_list = [css] if isinstance(css, str) and css else list(css)
        menu_manage.add_external(
            MenuItem(
                module=module,
                name=name,
                router=path,
                icon=icon,
                js=js,
                css=css_list,
                default=default,
            )
        )
        logger.debug(f"外部插件注册页面: {name} ({path})", command="WebUI")

    def sync_menus(self) -> None:
        """同步菜单：清理已卸载插件残留的外部菜单项

        仅保留内置默认菜单与本次启动已注册的外部菜单。
        """
        keep = {m.module for m in default_menus} | self._registered_modules
        menu_manage.keep_modules(keep)


registry = WebUiRegistry()
"""WebUI 扩展注册器单例，供外部插件调用"""
