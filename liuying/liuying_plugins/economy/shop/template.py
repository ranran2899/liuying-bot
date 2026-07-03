"""道具模板访问层

封装 ItemTemplate 模型的查询与统计操作，提供面向业务的简洁接口。
所有上层模块对道具模板的访问均应通过 TemplateRepository 进行，
避免直接依赖 ORM 模型，便于后续替换持久化实现。
"""

import time

from liuying.models._economy import ItemTemplate

_DEFAULT_SHOP = "default"


def _is_valid_time(limited_time: int) -> bool:
    """检查限时是否有效

    参数:
        limited_time: 限时时间戳，-1 表示不限时

    返回:
        bool: 是否在有效期内
    """
    return limited_time == -1 or limited_time >= int(time.time())


class TemplateRepository:
    """道具模板访问仓储

    提供模板查询、解析、统计等只读操作，无状态可共享。
    写操作（注册/删除）由 ItemTemplate 模型方法承担。
    """

    @staticmethod
    async def get_visible_templates(shop_name: str = _DEFAULT_SHOP) -> list[dict]:
        """获取所有可见且在有效期内的道具模板

        参数:
            shop_name: 商店名称，默认为 "default"

        返回:
            list[dict]: 可见道具模板列表
        """
        all_templates = await ItemTemplate.get_all_templates(shop_name)
        return [
            t
            for t in all_templates
            if t.get("is_visible", 1) != 0
            and _is_valid_time(t.get("limited_time", -1))
        ]

    @staticmethod
    async def find_template(
        keyword: str, shop_name: str = _DEFAULT_SHOP
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
        return await ItemTemplate.get_template_by_id(
            keyword, shop_name
        ) or await ItemTemplate.get_template_by_name(keyword, shop_name)

    @staticmethod
    async def resolve_store_item(
        keyword: str, shop_name: str = _DEFAULT_SHOP
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
                all_items = await TemplateRepository.get_visible_templates(shop_name)
                if 0 <= index < len(all_items):
                    return all_items[index]
        except ValueError:
            pass

        return await TemplateRepository.find_template(keyword, shop_name)

    @staticmethod
    async def get_template_with_count(
        item_id: str, count: int, shop_name: str = _DEFAULT_SHOP
    ) -> dict | None:
        """获取道具模板并附带数量字段

        参数:
            item_id: 道具 ID
            count: 道具数量
            shop_name: 商店名称

        返回:
            dict | None: 包含 count 字段的道具字典
        """
        template = await ItemTemplate.get_template_by_id(item_id, shop_name)
        if not template:
            return None
        return {**template, "count": count}

    @staticmethod
    async def get_hot_items(
        limit: int = 10, shop_name: str = _DEFAULT_SHOP
    ) -> list[dict]:
        """获取热销道具排行榜

        一次性读取所有模板与购买统计，避免逐条查询数据库。

        参数:
            limit: 返回数量上限
            shop_name: 商店名称

        返回:
            list[dict]: 热销道具列表，按销量降序
        """
        templates = await ItemTemplate.get_all_templates(shop_name)
        stats_map = await ItemTemplate.get_all_purchase_stats(shop_name)

        stats_list: list[dict] = []
        for t in templates:
            total = stats_map.get(t["id"], {}).get("total", 0)
            if total > 0:
                stats_list.append(
                    {
                        "id": t["id"],
                        "name": t.get("name", ""),
                        "total": total,
                        "price": t.get("price", 0),
                        "type": t.get("type", ""),
                        "image_url": t.get("image_url", ""),
                        "name_color": t.get("name_color", ""),
                        "description_color": t.get("description_color", ""),
                        "description": t.get("description", ""),
                    }
                )
        stats_list.sort(key=lambda x: x["total"], reverse=True)
        return stats_list[:limit]

    @staticmethod
    def is_expired(limited_time: int) -> bool:
        """检查道具是否过期

        参数:
            limited_time: 限时时间戳

        返回:
            bool: True 表示已过期
        """
        return not _is_valid_time(limited_time)


__all__ = ["TemplateRepository"]
