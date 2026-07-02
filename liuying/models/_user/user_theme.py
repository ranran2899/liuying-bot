"""用户主题模型"""

from typing import ClassVar

import orjson as json
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class UserTheme(Model):
    """用户主题模型 - 管理用户拥有的主题和当前选择"""

    __tablename__ = "user_theme"
    __table_args__: ClassVar[dict] = {
        "comment": "用户主题表，用于管理用户拥有的主题和当前选择"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    user_id: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, comment="用户id"
    )
    owned_themes: Mapped[str] = mapped_column(
        Text,
        default='{"data": {}}',
        comment="用户拥有的主题，JSON格式，如"
                '{"data": {"sign": ["default", "spring_bloom"]}}',
    )
    current_themes: Mapped[str] = mapped_column(
        Text,
        default="{}",
        comment="用户当前选择的主题，JSON格式，如"
                '{"sign": "spring_bloom"}',
    )

    @classmethod
    async def get_user_theme(cls, user_id: str) -> "UserTheme":
        """获取用户主题记录，不存在则创建默认记录。

        参数:
            user_id: 用户ID

        返回:
            UserTheme: 用户主题记录
        """
        user_theme, _ = await cls.get_or_create(
            user_id=user_id,
            defaults={
                "owned_themes": '{"data": {}}',
                "current_themes": "{}",
            },
        )
        return user_theme

    @classmethod
    def _parse_json(cls, raw: str, default: dict | list) -> dict | list:
        """安全解析JSON字符串。

        参数:
            raw: JSON字符串
            default: 解析失败时的默认值

        返回:
            dict | list: 解析结果
        """
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, AttributeError):
            return default

    @classmethod
    async def get_current_theme(cls, user_id: str, feature: str) -> str:
        """获取用户指定功能的当前主题。

        参数:
            user_id: 用户ID
            feature: 功能标识，如 "sign"、"bank"

        返回:
            str: 当前主题名称，默认返回 "default"
        """
        user_theme = await cls.get_user_theme(user_id)
        current = cls._parse_json(user_theme.current_themes, {})
        return current.get(feature, "default")

    @classmethod
    async def set_current_theme(
        cls, user_id: str, feature: str, theme_name: str
    ) -> bool:
        """设置用户指定功能的当前主题。

        "default"主题始终可用，无需检查所有权。

        参数:
            user_id: 用户ID
            feature: 功能标识
            theme_name: 主题名称

        返回:
            bool: 是否设置成功
        """
        if theme_name != "default":
            if not await cls.has_theme(user_id, feature, theme_name):
                return False
        user_theme = await cls.get_user_theme(user_id)
        current = cls._parse_json(user_theme.current_themes, {})
        current[feature] = theme_name
        user_theme.current_themes = json.dumps(
            current, ensure_ascii=False
        ).decode()
        await user_theme.save(update_fields=["current_themes"])
        return True

    @classmethod
    async def add_owned_theme(
        cls, user_id: str, feature: str, theme_name: str
    ) -> bool:
        """为用户添加拥有的主题。

        添加非默认主题时，自动确保"default"也在拥有列表中。

        参数:
            user_id: 用户ID
            feature: 功能标识
            theme_name: 主题名称

        返回:
            bool: 是否添加成功
        """
        user_theme = await cls.get_user_theme(user_id)
        owned = cls._parse_json(user_theme.owned_themes, {"data": {}})
        if "data" not in owned:
            owned["data"] = {}
        if feature not in owned["data"]:
            owned["data"][feature] = []
        if "default" not in owned["data"][feature]:
            owned["data"][feature].append("default")
        if theme_name not in owned["data"][feature]:
            owned["data"][feature].append(theme_name)
        user_theme.owned_themes = json.dumps(
            owned, ensure_ascii=False
        ).decode()
        await user_theme.save(update_fields=["owned_themes"])
        return True

    @classmethod
    async def remove_owned_theme(
        cls, user_id: str, feature: str, theme_name: str
    ) -> bool:
        """移除用户拥有的主题。

        参数:
            user_id: 用户ID
            feature: 功能标识
            theme_name: 主题名称

        返回:
            bool: 是否移除成功
        """
        user_theme = await cls.get_user_theme(user_id)
        owned = cls._parse_json(user_theme.owned_themes, {"data": {}})
        if "data" in owned and feature in owned["data"]:
            if theme_name in owned["data"][feature]:
                owned["data"][feature].remove(theme_name)
                user_theme.owned_themes = json.dumps(
                    owned, ensure_ascii=False
                ).decode()
                await user_theme.save(update_fields=["owned_themes"])
                return True
        return False

    @classmethod
    async def get_owned_themes(
        cls, user_id: str, feature: str | None = None
    ) -> dict | list:
        """获取用户拥有的主题。

        参数:
            user_id: 用户ID
            feature: 功能标识，为None时返回全部

        返回:
            dict | list: 拥有的主题列表或完整字典
        """
        user_theme = await cls.get_user_theme(user_id)
        owned = cls._parse_json(user_theme.owned_themes, {"data": {}})
        if feature:
            return owned.get("data", {}).get(feature, [])
        return owned

    @classmethod
    async def get_current_themes_dict(cls, user_id: str) -> dict:
        """获取用户所有功能的当前主题字典。

        参数:
            user_id: 用户ID

        返回:
            dict: 功能到主题名称的映射字典
        """
        user_theme = await cls.get_user_theme(user_id)
        return cls._parse_json(user_theme.current_themes, {})

    @classmethod
    async def has_theme(
        cls, user_id: str, feature: str, theme_name: str
    ) -> bool:
        """检查用户是否拥有指定功能的指定主题。

        参数:
            user_id: 用户ID
            feature: 功能标识
            theme_name: 主题名称

        返回:
            bool: 是否拥有该主题
        """
        owned = await cls.get_owned_themes(user_id, feature)
        return theme_name in owned
