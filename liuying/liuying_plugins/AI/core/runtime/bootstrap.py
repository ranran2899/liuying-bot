"""运行时启动引导

按顺序初始化运行时所需模块（开关/组件组装），
并在关闭时释放资源，保证启动流程的可观测性与顺序确定性。
"""

from liuying.utils.log import logger

from ...config import get_config
from .assembly import runtime_assembly
from .switch import runtime_switch

__all__ = ["Bootstrap", "bootstrap"]


class Bootstrap:
    """运行时启动引导器

    负责按依赖顺序初始化运行时核心模块，并提供优雅关闭入口。
    重复调用 startup 会短路返回，避免重复初始化。
    """

    def __init__(self) -> None:
        """初始化启动引导器"""
        self._started = False
        """是否已完成启动"""

    async def startup(self) -> bool:
        """启动引导流程

        依次初始化运行时开关与组件组装，仅当核心组件就绪时返回 True。
        已启动时直接返回 True。

        返回:
            bool: 是否启动成功
        """
        if self._started:
            logger.debug("运行时已启动，跳过重复引导", command="AI")
            return True

        if not bool(get_config("ENABLE_AI", True)):
            logger.info("AI总开关已关闭，跳过运行时引导", command="AI")
            return False

        try:
            runtime_switch.initialize()
            runtime_assembly.assemble()
            self._started = True
            logger.info("运行时启动引导完成", command="AI")
            return True
        except Exception as e:
            logger.warning(
                f"运行时启动引导失败: {e}",
                command="AI",
                e=e,
            )
            return False

    async def shutdown(self) -> None:
        """关闭引导流程

        重置组件组装状态并标记未启动，供重启场景使用。
        """
        if not self._started:
            return
        try:
            runtime_assembly.reset()
        except Exception as e:
            logger.warning(
                f"运行时关闭清理异常: {e}",
                command="AI",
                e=e,
            )
        self._started = False
        logger.info("运行时已关闭", command="AI")

    @property
    def started(self) -> bool:
        """是否已启动"""
        return self._started


bootstrap = Bootstrap()
"""运行时启动引导器单例"""
