from datetime import datetime
from typing import ClassVar

import orjson as json
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model
from liuying.utils.log import logger

# 道具模板必需字段
_REQUIRED_KEYS = ("id", "name")
# 道具模板可选字段及默认值
_OPTIONAL_KEYS: dict[str, object] = {
    "description": "",
    "price": 0,
    "type": "",
    "image_url": "",
    "name_color": "",
    "description_color": "",
    "limited_time": -1,
    "discount": 100,
    "is_visible": 1,
    "limit_purchase": -1,
}


class ItemTemplate(Model):
    """道具模板模型类，道具ID存储在 item_data JSON 中"""

    __tablename__ = "item_template"
    __table_args__: ClassVar[dict] = {"comment": "道具模板表"}

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    shop_name: Mapped[str] = mapped_column(
        String(255), default="default", index=True, comment="商店名称"
    )
    item_data: Mapped[str] = mapped_column(
        Text, default="{}", comment="道具信息JSON"
    )
    purchase_stats: Mapped[str] = mapped_column(
        Text, default="{}", comment="购买统计JSON"
    )
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.now, comment="创建时间"
    )

    # ==================== 数据访问方法 ====================

    def get_data(self) -> dict:
        """获取道具数据字典"""
        try:
            return json.loads(self.item_data)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_data(self, data: dict) -> None:
        """设置道具数据"""
        self.item_data = json.dumps(data).decode()

    def get_stats(self) -> dict:
        """获取购买统计数据"""
        try:
            return json.loads(self.purchase_stats)
        except (json.JSONDecodeError, TypeError):
            return _default_stats()

    def set_stats(self, stats: dict) -> None:
        """设置购买统计数据"""
        self.purchase_stats = json.dumps(stats).decode()

    def to_dict(self) -> dict:
        """将模板实例转换为字典，包含 shop_name 字段"""
        data = self.get_data()
        data["shop_name"] = self.shop_name
        return data

    # ==================== 统一注册接口 ====================

    @classmethod
    async def register(
        cls, item_data: dict, shop_name: str = "default"
    ) -> bool:
        """注册单个道具模板（统一注册入口）

        参数:
            item_data: 道具数据字典，必须包含 id 和 name
            shop_name: 商店名称，默认为 "default"

        返回:
            bool: 是否注册成功（已存在或新增成功均返回 True）
        """
        if not isinstance(item_data, dict):
            return False
        if not all(k in item_data for k in _REQUIRED_KEYS):
            logger.warning(f"道具数据缺少必要字段: {item_data}")
            return False

        item_id = item_data["id"]
        existing = await cls._find_by_item_id(item_id, shop_name)
        if existing:
            return True

        store_data = cls._build_store_data(item_data)
        await cls.create(
            shop_name=shop_name,
            item_data=json.dumps(store_data).decode(),
            purchase_stats=json.dumps(_default_stats()).decode(),
        )
        return True

    @classmethod
    async def batch_register(
        cls, items: dict | list[dict], shop_name: str = "default"
    ) -> tuple[int, int]:
        """批量注册道具模板

        参数:
            items: 道具数据字典或字典列表
            shop_name: 商店名称，默认为 "default"

        返回:
            tuple[int, int]: (成功注册数量, 总数量)
        """
        items_list = [items] if isinstance(items, dict) else items

        if not items_list:
            logger.warning("道具注册失败: 未提供有效的道具数据")
            return 0, 0

        added = 0
        for item in items_list:
            if await cls.register(item, shop_name):
                added += 1
        if added > 0:
            logger.info(f"道具批量注册完成: {added}/{len(items_list)}")
        else:
            logger.warning("道具批量注册失败，未能注册任何道具")
        return added, len(items_list)

    @classmethod
    async def add_template(
        cls, item_data: dict, shop_name: str = "default"
    ) -> bool:
        """添加道具模板（委托给 register）

        参数:
            item_data: 道具数据字典，必须包含 id 和 name
            shop_name: 商店名称，默认为 "default"

        返回:
            bool: 是否添加成功
        """
        return await cls.register(item_data, shop_name)

    @staticmethod
    def _build_store_data(item_data: dict) -> dict:
        """从原始道具数据构建标准化存储数据

        参数:
            item_data: 原始道具数据字典

        返回:
            dict: 标准化后的道具数据
        """
        return {
            "id": item_data["id"],
            "name": item_data["name"],
            **{k: item_data.get(k, v) for k, v in _OPTIONAL_KEYS.items()},
        }

    # ==================== 查询内部方法 ====================

    @classmethod
    async def _find_by_item_id(
        cls, item_id: str, shop_name: str = "default"
    ) -> "ItemTemplate | None":
        """通过道具 ID 在 JSON 中查找模板记录"""
        templates = await cls.filter(shop_name=shop_name).all()
        for t in templates:
            if t.get_data().get("id") == item_id:
                return t
        return None

    # ==================== 查询方法 ====================

    @classmethod
    async def get_all_templates(
        cls, shop_name: str = "default"
    ) -> list[dict]:
        """获取指定商店的道具模板列表"""
        templates = await cls.filter(shop_name=shop_name).all()
        return [t.to_dict() for t in templates]

    @classmethod
    async def get_template_by_id(
        cls, item_id: str, shop_name: str = "default"
    ) -> dict | None:
        """通过 ID 获取道具模板"""
        if not item_id:
            return None
        template = await cls._find_by_item_id(item_id, shop_name)
        return template.to_dict() if template else None

    @classmethod
    async def get_template_by_name(
        cls, name: str, shop_name: str = "default"
    ) -> dict | None:
        """通过名称获取道具模板"""
        if not name:
            return None
        templates = await cls.filter(shop_name=shop_name).all()
        for t in templates:
            if t.get_data().get("name") == name:
                return t.to_dict()
        return None

    @classmethod
    async def delete_template(
        cls,
        item_id: str | None = None,
        item_name: str | None = None,
        shop_name: str = "default",
    ) -> bool:
        """删除道具模板

        参数:
            item_id: 道具 ID
            item_name: 道具名称
            shop_name: 商店名称

        返回:
            bool: 是否删除成功
        """
        if not item_id and not item_name:
            return False

        template = await cls._find_template(item_id, item_name, shop_name)
        if not template:
            return False
        await template.delete()
        return True

    @classmethod
    async def _find_template(
        cls,
        item_id: str | None,
        item_name: str | None,
        shop_name: str,
    ) -> "ItemTemplate | None":
        """通过 ID 或名称查找模板记录"""
        if item_id:
            template = await cls._find_by_item_id(item_id, shop_name)
            if template:
                return template
        if item_name:
            templates = await cls.filter(shop_name=shop_name).all()
            for t in templates:
                if t.get_data().get("name") == item_name:
                    return t
        return None

    # ==================== 购买统计方法 ====================

    @classmethod
    async def record_purchase(
        cls, item_id: str, quantity: int = 1, shop_name: str = "default"
    ) -> bool:
        """记录购买统计

        参数:
            item_id: 道具 ID
            quantity: 购买数量
            shop_name: 商店名称

        返回:
            bool: 是否记录成功
        """
        template = await cls._find_by_item_id(item_id, shop_name)
        if not template:
            return False

        stats = template.get_stats()
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        week_key = f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"
        month_key = now.strftime("%Y-%m")
        year_key = str(now.year)

        stats.setdefault("daily", {})[today] = (
            stats["daily"].get(today, 0) + quantity
        )
        stats.setdefault("weekly", {})[week_key] = (
            stats["weekly"].get(week_key, 0) + quantity
        )
        stats.setdefault("monthly", {})[month_key] = (
            stats["monthly"].get(month_key, 0) + quantity
        )
        stats.setdefault("yearly", {})[year_key] = (
            stats["yearly"].get(year_key, 0) + quantity
        )
        stats["total"] = stats.get("total", 0) + quantity

        template.set_stats(stats)
        await template.save(update_fields=["purchase_stats"])
        return True

    @classmethod
    async def get_purchase_stats(
        cls, item_id: str, shop_name: str = "default"
    ) -> dict | None:
        """获取道具购买统计"""
        template = await cls._find_by_item_id(item_id, shop_name)
        return template.get_stats() if template else None

    @classmethod
    async def get_all_purchase_stats(
        cls, shop_name: str = "default"
    ) -> dict[str, dict]:
        """获取指定商店所有道具的购买统计

        参数:
            shop_name: 商店名称，默认为 "default"

        返回:
            dict[str, dict]: 道具 ID 到购买统计字典的映射
        """
        templates = await cls.filter(shop_name=shop_name).all()
        return {t.get_data().get("id", ""): t.get_stats() for t in templates}

    # ==================== 数据库迁移 ====================

    @classmethod
    def _run_script(cls) -> list[str]:
        """数据库迁移脚本"""
        return [
            "ALTER TABLE item_template "
            "ADD COLUMN shop_name VARCHAR(255) DEFAULT 'default';",
            "UPDATE item_template SET item_data = json_set("
            "item_data, '$.id', item_id) "
            "WHERE item_id IS NOT NULL "
            "AND json_extract(item_data, '$.id') IS NULL;",
            "CREATE INDEX IF NOT EXISTS ix_item_template_shop_name "
            "ON item_template (shop_name);",
        ]


def _default_stats() -> dict:
    """生成默认购买统计结构"""
    return {
        "daily": {},
        "weekly": {},
        "monthly": {},
        "yearly": {},
        "total": 0,
    }
