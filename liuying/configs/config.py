from pathlib import Path

import nonebot
from nonebot import get_driver
from pydantic import BaseModel, Field

from .utils import ConfigsManager

driver = get_driver()

NICKNAME = next(iter(driver.config.nickname), "")
"""机器人昵称"""

__all__ = ["BotConfig", "Config"]


class BotSetting(BaseModel):
    self_nickname: str = NICKNAME
    """回复时NICKNAME"""
    system_proxy: str | None = None
    """系统代理"""
    db_url: str = "sqlite+aiosqlite:///data/db/db_liuying.db"
    """默认数据库链接"""
    db_urls: dict[str, str] = Field(default_factory=dict)
    """多个数据库连接配置，键为数据库名称，值为数据库连接字符串"""
    db_sync_enabled: bool = False
    """是否开启数据库同步功能"""
    db_sync_slaves: list[str] = Field(default_factory=list)
    """需要同步主数据库的副数据库名称列表"""
    db_sync_interval: int = 3600
    """数据库同步间隔，单位为秒，默认1小时"""
    platform_superusers: dict[str, list[str]] = Field(default_factory=dict)
    """平台超级用户"""
    qbot_id_data: dict[str, str] = Field(default_factory=dict)
    """官bot id:账号id"""

    def get_qbot_uid(self, qbot_id: str) -> str | None:
        """获取官bot账号id

        参数:
            qbot_id: 官bot id

        返回:
            账号id
        """
        return self.qbot_id_data.get(qbot_id)

    def get_superuser(self, platform: str) -> list[str]:
        """获取超级用户

        参数:
            platform: 对应平台

        返回:
            超级用户id列表
        """
        if self.platform_superusers:
            return self.platform_superusers.get(platform, [])
        return []

    def get_sql_type(self, db_name: str = "default") -> str:
        """获取数据库类型

        参数:
            db_name: 数据库名称，默认为"default"

        返回:
            数据库类型（postgres, mysql, sqlite）
        """
        db_url = self.get_db_url(db_name)
        return db_url.split(":", 1)[0] if db_url else ""

    def get_db_url(self, db_name: str = "default") -> str:
        """获取指定名称的数据库连接字符串

        参数:
            db_name: 数据库名称，默认为"default"

        返回:
            数据库连接字符串
        """
        if db_name == "default":
            return self.db_url
        return self.db_urls.get(db_name, self.db_url)


Config = ConfigsManager(Path() / "data" / "configs" / "plugins2config.yaml")
BotConfig = nonebot.get_plugin_config(BotSetting)
