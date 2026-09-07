"""链式构建头像（单个/组合）的辅助类。"""

from typing import Literal, Self

from ...models.widgets.avatar import Avatar, AvatarGroup
from ..base import BaseBuilder

__all__ = ["AvatarBuilder", "AvatarGroupBuilder"]


class AvatarBuilder(BaseBuilder[Avatar]):
    """链式构建单个头像的辅助类。"""

    def __init__(self, src: str):
        """初始化头像构建器。

        参数:
            src: 头像的 URL 或 Base64 数据 URI。
        """
        data_model = Avatar(src=src, shape="circle", size=50)
        super().__init__(data_model, template_name="components/widgets/avatar")

    def set_shape(self, shape: Literal["circle", "square"]) -> Self:
        """设置头像形状。

        参数:
            shape: 头像形状（circle/square）。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.shape = shape
        return self

    def set_size(self, size: int) -> Self:
        """设置头像尺寸。

        参数:
            size: 头像边长（像素）。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.size = size
        return self


class AvatarGroupBuilder(BaseBuilder[AvatarGroup]):
    """链式构建头像组的辅助类。"""

    def __init__(self):
        """初始化头像组构建器，默认间距 -15px（重叠）。"""
        data_model = AvatarGroup(avatars=[], spacing=-15, max_count=None)
        super().__init__(
            data_model, template_name="components/widgets/avatar_group"
        )

    def add_avatar(self, avatar: Avatar | AvatarBuilder | str) -> Self:
        """添加一个头像，支持模型、构建器或 URL 字符串。

        参数:
            avatar: 头像模型、头像构建器或头像 URL 字符串。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        match avatar:
            case str():
                self._data.avatars.append(Avatar(src=avatar, shape="circle", size=50))
            case AvatarBuilder():
                self._data.avatars.append(avatar.build())
            case _:
                self._data.avatars.append(avatar)
        return self
