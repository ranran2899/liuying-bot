class IsSuperuserException(Exception):
    pass


class _InfoException(Exception):
    """信息异常基类"""

    def __init__(self, info: str, *args: object) -> None:
        super().__init__(info, *args)
        self.info = info

    def __str__(self) -> str:
        return self.info

    def __repr__(self) -> str:
        return self.info


class SkipPluginException(_InfoException):
    pass


class PermissionExemption(_InfoException):
    pass
