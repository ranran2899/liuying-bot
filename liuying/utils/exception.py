from nonebot.exception import IgnoredException


class CooldownError(IgnoredException):
    """冷却异常，用于在冷却时中断事件处理。

    继承自 IgnoredException，不会在控制台留下错误堆栈。
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class HookPriorityException(BaseException):
    """钩子优先级异常"""

    def __init__(self, info: str = "") -> None:
        self.info = info

    def __str__(self) -> str:
        return self.info


class NotFoundError(Exception):
    """未发现"""


class GroupInfoNotFound(Exception):
    """群组未找到"""


class EmptyError(Exception):
    """空错误"""


class UserAndGroupIsNone(Exception):
    """用户和群组为空"""


class InsufficientGold(Exception):
    """金币不足"""


class InsufficientCopper(Exception):
    """铜币不足"""


class InsufficientSilver(Exception):
    """银币不足"""


class InsufficientDiamond(Exception):
    """钻石不足"""


class InsufficientXingqiong(Exception):
    """星琼不足"""


class InsufficientYuanshi(Exception):
    """原石不足"""


class InsufficientTianrew(Exception):
    """天赏点不足"""


class NotFindSuperuser(Exception):
    """未找到超级用户"""


class GoodsNotFound(Exception):
    """未找到道具"""


class AllURIsFailedError(Exception):
    """当所有备用URL都尝试失败后抛出此异常"""

    def __init__(self, urls: list[str], exceptions: list[Exception]):
        self.urls = urls
        self.exceptions = exceptions
        super().__init__(
            f"All {len(urls)} URIs failed. Last exception: {exceptions[-1]}"
        )

    def __str__(self) -> str:
        exc_info = "\n".join(
            f"  - {url}: {exc.__class__.__name__}({exc})"
            for url, exc in zip(self.urls, self.exceptions)
        )
        return f"All {len(self.urls)} URIs failed:\n{exc_info}"
