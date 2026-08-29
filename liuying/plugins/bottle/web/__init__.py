"""漂流瓶 WebUI 扩展注册入口

聚合漂流瓶的 WebUI 路由、模型与静态页面，
通过流萤 WebUI 扩展接口注册，web_ui 插件本体不含漂流瓶代码。

目录结构:
    router.py       WebUI API 路由
    data_source.py  WebUI 数据源
    model.py        WebUI 数据模型
    static/         前端页面与静态资源
"""

from pathlib import Path

from liuying.liuying_plugins.web_ui.registry import registry

from .router import router as bottle_web_router


def register() -> None:
    """将漂流瓶管理页注册到流萤 WebUI"""
    registry.register_api(bottle_web_router)
    registry.register_static("/bottle_ext", Path(__file__).parent / "static")
    registry.register_page(
        module="bottle",
        name="漂流瓶管理",
        path="/bottle",
        icon="bottle",
        js="/bottle_ext/js/page.js",
        css=[
            "/bottle_ext/css/page.css",
            "/bottle_ext/css/images.css",
        ],
    )
