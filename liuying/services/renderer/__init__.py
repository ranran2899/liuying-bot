"""图片渲染服务包。

按职责划分为三个子包（依赖方向：render -> theme -> core）：
- core: 协议契约、静态配置、渲染上下文与通用工具
- theme: 主题系统（主题管理、页面主题目录、资源注册、asset 解析）
- render: 渲染执行（门面、依赖收集、缓存、截图引擎）

对外暴露 renderer_service 单例，并提供启动生命周期钩子。
"""

from liuying.utils.manager.priority_manager import PriorityLifecycle

from .core.context import RenderContext
from .render.service import RendererService

renderer_service = RendererService()


@PriorityLifecycle.on_startup(priority=10)
async def _init_renderer_service():
    """在Bot启动时初始化渲染服务及其依赖。"""
    await renderer_service.initialize()


__all__ = ["RenderContext", "renderer_service"]
