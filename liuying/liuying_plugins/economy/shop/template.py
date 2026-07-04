"""道具模板访问层

封装 ItemTemplate 模型的所有业务操作：注册、查询、统计、删除等。
模型层仅负责表结构与基础读写，本模块承担全部业务逻辑，
所有上层模块对道具模板的访问均应通过 TemplateRepository 进行。
"""

from datetime import datetime
import time

import orjson as json

from liuying.models._economy import ItemTemplate
from liuying.models._economy.item_template import _default_stats
from liuying.utils.log import logger

_DEFAULT_SHOP = "default"
_REQUIRED_KEYS = ("id", "name")


def is_valid_time(limited_time: int) -> bool:
    """检查限时是否有效

    参数:
        limited_time: 限时时间戳，-1 表示不限时

    返回:
        bool: 是否在有效期内
    """
    return limited_time == -1 or limited_time >= int(time.time())


def _build_store_data(item_data: dict) -> dict:
    """从原始道具数据构建标准化存储数据

    严格遵循标准参数顺序：
    name-id-description-type-rarity-image_url-is_visible-price-discount-
    limit_purchase-limited_time

    参数:
        item_data: 原始道具数据字典

    返回:
        dict: 标准化后的道具数据
    """
    return {
        "name": item_data["name"],
        "id": item_data["id"],
        "description": item_data.get("description", ""),
        "type": item_data.get("type", ""),
        "rarity": item_data.get("rarity", 1),
        "image_url": item_data.get("image_url", ""),
        "is_visible": item_data.get("is_visible", 1),
        "price": item_data.get("price", 0),
        "discount": item_data.get("discount", 100),
        "limit_purchase": item_data.get("limit_purchase", -1),
        "limited_time": item_data.get("limited_time", -1),
    }


class TemplateRepository:
    """道具模板访问仓储

    提供模板的注册、查询、解析、统计等业务操作。
    所有上层模块通过本仓储访问道具模板，避免直接依赖 ORM 模型。
    """

    @classmethod
    async def batch_register(
        cls, items: dict | list[dict], shop_name: str = _DEFAULT_SHOP
    ) -> tuple[int, int]:
        """批量注册道具模板（支持单个和批量）

        传入单个字典时自动包装为列表处理。

        参数:
            items: 道具数据字典或字典列表
            shop_name: 商店名称

        返回:
            tuple[int, int]: (成功注册数量, 总数量)
        """
        items_list = [items] if isinstance(items, dict) else items
        if not items_list:
            logger.warning("道具注册失败: 未提供有效的道具数据")
            return 0, 0

        added = 0
        skipped = 0
        for item_data in items_list:
            if not isinstance(item_data, dict):
                continue
            if not all(k in item_data for k in _REQUIRED_KEYS):
                logger.warning(f"道具数据缺少必要字段: {item_data}")
                continue
            item_id = item_data["id"]
            if await cls._find_orm_by_id(item_id, shop_name):
                skipped += 1
                continue
            store_data = _build_store_data(item_data)
            await ItemTemplate.create(
                shop_name=shop_name,
                item_data=json.dumps(store_data).decode(),
                purchase_stats=json.dumps(_default_stats()).decode(),
            )
            added += 1

        total = len(items_list)
        if added > 0:
            logger.info(f"道具批量注册完成: {added}/{total}", "商店")
        elif skipped == total:
            logger.debug(f"道具模板均已存在，跳过注册: {skipped}/{total}", "商店")
        else:
            logger.warning("道具批量注册失败，未能注册任何道具", "商店")
        return added, total

    @classmethod
    async def get_all(
        cls, shop_name: str = _DEFAULT_SHOP
    ) -> list[dict]:
        """获取指定商店的全部道具模板

        参数:
            shop_name: 商店名称

        返回:
            list[dict]: 道具模板字典列表
        """
        templates = await ItemTemplate.filter(shop_name=shop_name).all()
        return [t.to_dict() for t in templates]

    @classmethod
    async def get_visible(
        cls, shop_name: str = _DEFAULT_SHOP
    ) -> list[dict]:
        """获取所有可见且在有效期内的道具模板

        参数:
            shop_name: 商店名称

        返回:
            list[dict]: 可见道具模板列表
        """
        return [
            t
            for t in await cls.get_all(shop_name)
            if t.get("is_visible", 1) != 0
            and is_valid_time(t.get("limited_time", -1))
        ]

    @classmethod
    async def get_by_id(
        cls, item_id: str, shop_name: str = _DEFAULT_SHOP
    ) -> dict | None:
        """通过 ID 获取道具模板

        参数:
            item_id: 道具 ID
            shop_name: 商店名称

        返回:
            dict | None: 道具模板字典，未找到返回 None
        """
        if not item_id:
            return None
        template = await cls._find_orm_by_id(item_id, shop_name)
        return template.to_dict() if template else None

    @classmethod
    async def find(
        cls, keyword: str, shop_name: str = _DEFAULT_SHOP
    ) -> dict | None:
        """通过 ID 或名称查找道具模板

        参数:
            keyword: 道具 ID 或名称
            shop_name: 商店名称

        返回:
            dict | None: 道具模板字典，未找到返回 None
        """
        if not keyword:
            return None
        by_id = await cls.get_by_id(keyword, shop_name)
        if by_id:
            return by_id

        templates = await ItemTemplate.filter(shop_name=shop_name).all()
        for t in templates:
            if t.get_data().get("name") == keyword:
                return t.to_dict()
        return None

    @classmethod
    async def resolve(
        cls, keyword: str, shop_name: str = _DEFAULT_SHOP
    ) -> dict | None:
        """从商店目录解析道具（支持序号、ID、名称）

        参数:
            keyword: 道具序号、ID 或名称
            shop_name: 商店名称

        返回:
            dict | None: 道具信息字典
        """
        try:
            index = int(keyword) - 1
            if index >= 0:
                all_items = await cls.get_visible(shop_name)
                if 0 <= index < len(all_items):
                    return all_items[index]
        except ValueError:
            pass
        return await cls.find(keyword, shop_name)

    @classmethod
    async def delete(
        cls,
        item_id: str | None = None,
        item_name: str | None = None,
        shop_name: str = _DEFAULT_SHOP,
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

        template = None
        if item_id:
            template = await cls._find_orm_by_id(item_id, shop_name)
        if not template and item_name:
            templates = await ItemTemplate.filter(shop_name=shop_name).all()
            for t in templates:
                if t.get_data().get("name") == item_name:
                    template = t
                    break
        if not template:
            return False
        await template.delete()
        return True

    @classmethod
    async def record_purchase(
        cls, item_id: str, quantity: int = 1, shop_name: str = _DEFAULT_SHOP
    ) -> bool:
        """记录购买统计

        参数:
            item_id: 道具 ID
            quantity: 购买数量
            shop_name: 商店名称

        返回:
            bool: 是否记录成功
        """
        template = await cls._find_orm_by_id(item_id, shop_name)
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
    async def get_hot_items(
        cls, limit: int = 10, shop_name: str = _DEFAULT_SHOP
    ) -> list[dict]:
        """获取热销道具排行榜

        一次性读取所有模板与购买统计，避免逐条查询数据库。

        参数:
            limit: 返回数量上限
            shop_name: 商店名称

        返回:
            list[dict]: 热销道具列表，按销量降序
        """
        templates = await ItemTemplate.filter(shop_name=shop_name).all()
        stats_list: list[dict] = []
        for t in templates:
            data = t.to_dict()
            total = t.get_stats().get("total", 0)
            if total > 0:
                stats_list.append(
                    {
                        "id": data.get("id", ""),
                        "name": data.get("name", ""),
                        "total": total,
                        "price": data.get("price", 0),
                        "type": data.get("type", ""),
                        "rarity": data.get("rarity", 1),
                        "image_url": data.get("image_url", ""),
                        "description": data.get("description", ""),
                    }
                )
        stats_list.sort(key=lambda x: x["total"], reverse=True)
        return stats_list[:limit]

    @classmethod
    async def _find_orm_by_id(
        cls, item_id: str, shop_name: str = _DEFAULT_SHOP
    ) -> ItemTemplate | None:
        """通过道具 ID 在 JSON 中查找模板记录（返回 ORM 实例）

        参数:
            item_id: 道具 ID
            shop_name: 商店名称

        返回:
            ItemTemplate | None: 模板实例，未找到返回 None
        """
        templates = await ItemTemplate.filter(shop_name=shop_name).all()
        for t in templates:
            if t.get_data().get("id") == item_id:
                return t
        return None


__all__ = ["TemplateRepository", "is_valid_time"]
