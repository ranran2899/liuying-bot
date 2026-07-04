"""用户道具库存管理模块

负责用户背包数据的持久化与查询。
库存数据存储于 UserInfo.items 字段，使用 JSON 序列化。
所有方法均为静态方法，直接接收 user_id 参数，无需构造实例。
"""

import orjson as json

from liuying.models._user.user_info import UserInfo
from liuying.utils.log import logger

from .template import TemplateRepository

_DEFAULT_SHOP = "default"


class ItemInventory:
    """用户道具库存

    所有方法均为静态方法，直接接收 user_id 参数。
    外部插件可直接调用，无需构造实例。

    示例:
        await ItemInventory.add(user_id, "item_gold_coin", 1)
        await ItemInventory.reduce(user_id, "item_gold_coin", 1)
        items = await ItemInventory.get_items(user_id)
    """

    @staticmethod
    async def _load_items(user_id: str) -> dict[str, int]:
        """从数据库加载用户道具数据

        参数:
            user_id: 用户 ID

        返回:
            dict[str, int]: 道具 ID 到数量的映射
        """
        user = await UserInfo.filter(user_id=str(user_id)).first()
        if not user or not user.items or not user.items.strip():
            return {}
        try:
            data = json.loads(user.items)
            if not isinstance(data, dict):
                return {}
            return {
                str(k): int(v)
                for k, v in data.items()
                if int(v) > 0
            }
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}

    @staticmethod
    async def _save_items(user_id: str, items_data: dict[str, int]) -> bool:
        """保存用户道具数据到数据库

        参数:
            user_id: 用户 ID
            items_data: 道具数据字典

        返回:
            bool: 是否保存成功
        """
        user, _ = await UserInfo.get_or_create(user_id=str(user_id))
        user.items = json.dumps(items_data).decode()
        await user.save()
        return True

    @staticmethod
    async def get_items(user_id: str) -> list[dict]:
        """获取用户道具列表（合并模板信息）

        参数:
            user_id: 用户 ID

        返回:
            list[dict]: 道具信息列表，每项包含 count 字段
        """
        items_data = await ItemInventory._load_items(user_id)
        result: list[dict] = []
        for item_id, count in items_data.items():
            template = await TemplateRepository.get_by_id(
                item_id, _DEFAULT_SHOP
            )
            if template:
                template["count"] = count
                result.append(template)
        return result

    @staticmethod
    async def add(user_id: str, item_id: str, quantity: int = 1) -> bool:
        """给用户添加道具

        参数:
            user_id: 用户 ID
            item_id: 道具 ID
            quantity: 添加数量

        返回:
            bool: 是否添加成功
        """
        quantity = max(1, quantity)
        template = await TemplateRepository.get_by_id(item_id, _DEFAULT_SHOP)
        if not template:
            logger.warning(f"道具模板不存在: {item_id}")
            return False

        items_data = await ItemInventory._load_items(user_id)
        items_data[item_id] = items_data.get(item_id, 0) + quantity
        if await ItemInventory._save_items(user_id, items_data):
            logger.info(f"用户 {user_id} 获得道具 {item_id} x {quantity}")
            return True
        return False

    @staticmethod
    async def reduce(user_id: str, item_id: str, quantity: int = 1) -> bool:
        """减少用户道具数量，归零时删除键

        参数:
            user_id: 用户 ID
            item_id: 道具 ID
            quantity: 减少数量

        返回:
            bool: 是否减少成功
        """
        quantity = max(1, quantity)
        items_data = await ItemInventory._load_items(user_id)
        current = items_data.get(item_id, 0)
        if current < quantity:
            return False
        new_count = current - quantity
        if new_count <= 0:
            items_data.pop(item_id, None)
        else:
            items_data[item_id] = new_count
        return await ItemInventory._save_items(user_id, items_data)

    @staticmethod
    async def get_count(user_id: str, item_id: str) -> int:
        """获取用户特定道具的数量

        参数:
            user_id: 用户 ID
            item_id: 道具 ID

        返回:
            int: 道具数量
        """
        items_data = await ItemInventory._load_items(user_id)
        return items_data.get(item_id, 0)

    @staticmethod
    async def check_enough(user_id: str, item_id: str, count: int) -> bool:
        """检查用户道具是否足够

        参数:
            user_id: 用户 ID
            item_id: 道具 ID
            count: 需要检查的数量

        返回:
            bool: 是否足够
        """
        return await ItemInventory.get_count(user_id, item_id) >= count

    @staticmethod
    async def check_limit(user_id: str, item_id: str, limit: int) -> bool:
        """检查用户是否达到限购数量

        参数:
            user_id: 用户 ID
            item_id: 道具 ID
            limit: 限购数量，-1 表示不限购

        返回:
            bool: 是否可以继续购买
        """
        if limit == -1:
            return True
        items_data = await ItemInventory._load_items(user_id)
        return items_data.get(item_id, 0) < limit

    @staticmethod
    async def resolve_item(user_id: str, keyword: str) -> dict | None:
        """解析用户背包中的道具（支持序号、ID、名称）

        参数:
            user_id: 用户 ID
            keyword: 道具序号、ID 或名称

        返回:
            dict | None: 道具信息字典
        """
        user_items = await ItemInventory.get_items(user_id)
        try:
            index = int(keyword) - 1
            if 0 <= index < len(user_items):
                return user_items[index]
        except ValueError:
            pass

        for item in user_items:
            if item["id"] == keyword or item.get("name") == keyword:
                return item
        return None


__all__ = ["ItemInventory"]
