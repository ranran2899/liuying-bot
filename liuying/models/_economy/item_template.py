"""道具模板模型

仅包含数据表结构定义与基础 JSON 数据访问方法。
所有业务逻辑（注册、查询、统计）由商店插件的 TemplateRepository 承担，
模型层与业务层彻底分离。
"""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class ItemTemplate(Model):
    """道具模板模型类

    道具 ID 存储在 item_data JSON 字段中，本类仅负责表结构与基础读写。
    """

    __tablename__ = "item_template"
    __table_args__: ClassVar[dict] = {"comment": "道具模板表"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    shop_name: Mapped[str] = mapped_column(
        String(255), default="default", index=True, comment="商店名称"
    )
    item_data: Mapped[dict] = mapped_column(
        JSON, default=dict, comment="道具信息JSON"
    )
    purchase_stats: Mapped[dict] = mapped_column(
        JSON, default=dict, comment="购买统计JSON"
    )
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.now, comment="创建时间"
    )

    def get_data(self) -> dict:
        """获取道具数据字典

        返回:
            dict: 道具数据字典，字段异常时返回空字典
        """
        return self.item_data if isinstance(self.item_data, dict) else {}

    def set_data(self, data: dict) -> None:
        """设置道具数据字典

        参数:
            data: 道具数据字典
        """
        self.item_data = data

    def get_stats(self) -> dict:
        """获取购买统计数据

        返回:
            dict: 购买统计数据字典，字段异常时返回默认结构
        """
        return (
            self.purchase_stats
            if isinstance(self.purchase_stats, dict)
            else _default_stats()
        )

    def set_stats(self, stats: dict) -> None:
        """设置购买统计数据

        参数:
            stats: 购买统计数据字典
        """
        self.purchase_stats = stats

    def to_dict(self) -> dict:
        """将模板实例转换为字典

        返回:
            dict: 包含 shop_name 字段的道具字典
        """
        data = dict(self.get_data())
        data["shop_name"] = self.shop_name
        return data

    @classmethod
    def _run_script(cls) -> list[str]:
        """数据库迁移脚本

        返回:
            list[str]: 迁移 SQL 语句列表
        """
        return [
            "ALTER TABLE item_template "
            "ADD COLUMN shop_name VARCHAR(255) DEFAULT 'default';",
            "CREATE INDEX IF NOT EXISTS ix_item_template_shop_name "
            "ON item_template (shop_name);",
        ]


def _default_stats() -> dict:
    """生成默认购买统计结构

    返回:
        dict: 默认购买统计字典
    """
    return {
        "daily": {},
        "weekly": {},
        "monthly": {},
        "yearly": {},
        "total": 0,
    }
