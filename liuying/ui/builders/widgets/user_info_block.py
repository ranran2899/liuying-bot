"""链式构建用户信息块的辅助类。"""

from typing import Self

from ...models.widgets.user_info_block import UserInfoBlock
from ..base import BaseBuilder

__all__ = ["UserInfoBlockBuilder"]


class UserInfoBlockBuilder(BaseBuilder[UserInfoBlock]):
    """链式构建用户信息块的辅助类。"""

    def __init__(
        self,
        name: str,
        avatar_url: str,
        subtitle: str | None = None,
        tags: list[str] | None = None,
    ):
        """初始化用户信息块构建器。

        参数:
            name: 用户的名称。
            avatar_url: 用户头像的 URL。
            subtitle: 显示在名称下方的可选副标题（如 UID 或角色）。
            tags: 初始附加标签列表。
        """
        data_model = UserInfoBlock(
            name=name, avatar_url=avatar_url, subtitle=subtitle, tags=tags or []
        )
        super().__init__(
            data_model, template_name="components/widgets/user_info_block"
        )

    def set_subtitle(self, subtitle: str) -> Self:
        """设置副标题。

        参数:
            subtitle: 显示在名称下方的文本。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.subtitle = subtitle
        return self

    def add_tag(self, tag: str) -> Self:
        """添加一个标签。

        参数:
            tag: 标签文本。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.tags.append(tag)
        return self

    def add_tags(self, tags: list[str]) -> Self:
        """批量添加标签。

        参数:
            tags: 标签文本列表。

        返回:
            Self: 构建器自身，支持链式调用。
        """
        self._data.tags.extend(tags)
        return self
