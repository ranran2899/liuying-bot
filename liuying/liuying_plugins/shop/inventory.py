import time

import orjson as json

from liuying.models._bot import ItemTemplate
from liuying.models._user.user_info import UserInfo
from liuying.utils.log import logger


def is_valid_time(limited_time: int) -> bool:
    """检查限时是否有效

    参数:
        limited_time: 限时时间戳，-1 表示不限时

    返回:
        bool: 是否有效
    """
    return limited_time == -1 or limited_time >= int(time.time())


class _ItemRepository:
    """道具数据持久化（内部实现）"""

    @staticmethod
    async def get_user_items(user_id: str) -> dict:
        """获取用户道具数据

        参数:
            user_id: 用户 ID

        返回:
            dict: 道具数据字典
        """
        user = await UserInfo.filter(user_id=str(user_id)).first()
        if not user or not user.items or not user.items.strip():
            return {}
        try:
            data = json.loads(user.items)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @staticmethod
    async def save_user_items(user_id: str, items_data: dict) -> bool:
        """保存用户道具数据

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
    async def incr_item(user_id: str, item_id: str, quantity: int = 1) -> bool:
        """增量添加单个道具

        参数:
            user_id: 用户 ID
            item_id: 道具 ID
            quantity: 增加数量

        返回:
            bool: 是否添加成功
        """
        items_data = await _ItemRepository.get_user_items(user_id)
        items_data[item_id] = items_data.get(item_id, 0) + quantity
        return await _ItemRepository.save_user_items(user_id, items_data)

    @staticmethod
    async def decr_item(user_id: str, item_id: str, quantity: int = 1) -> bool:
        """增量减少单个道具，数量归零时删除键

        参数:
            user_id: 用户 ID
            item_id: 道具 ID
            quantity: 减少数量

        返回:
            bool: 是否减少成功
        """
        items_data = await _ItemRepository.get_user_items(user_id)
        current = items_data.get(item_id, 0)
        if current < quantity:
            return False
        new_count = current - quantity
        if new_count <= 0:
            items_data.pop(item_id, None)
        else:
            items_data[item_id] = new_count
        return await _ItemRepository.save_user_items(user_id, items_data)

    @staticmethod
    async def get_item_count(user_id: str, item_id: str) -> int:
        """获取用户单个道具的数量

        参数:
            user_id: 用户 ID
            item_id: 道具 ID

        返回:
            int: 道具数量
        """
        items_data = await _ItemRepository.get_user_items(user_id)
        return items_data.get(item_id, 0)


class ItemResolver:
    """物品解析类"""

    async def get_visible_templates(self) -> list[dict]:
        """获取所有可见道具模板列表

        返回:
            list[dict]: 可见道具模板列表
        """
        all_templates = await ItemTemplate.get_all_templates()
        return [
            t
            for t in all_templates
            if t.get("is_visible", 1) != 0
            and is_valid_time(t.get("limited_time", -1))
        ]

    async def find_template(self, keyword: str) -> dict | None:
        """通过 ID 或名称查找道具模板

        参数:
            keyword: 道具 ID 或名称

        返回:
            dict | None: 道具模板字典
        """
        return await ItemTemplate.get_template_by_id(
            keyword
        ) or await ItemTemplate.get_template_by_name(keyword)

    async def resolve_store_item(self, keyword: str) -> dict | None:
        """从商店目录解析道具（支持序号、ID、名称）

        参数:
            keyword: 道具序号、ID 或名称

        返回:
            dict | None: 道具信息字典
        """
        try:
            index = int(keyword) - 1
            if index >= 0:
                all_items = await self.get_visible_templates()
                if 0 <= index < len(all_items):
                    return all_items[index]
        except ValueError:
            pass

        return await self.find_template(keyword)

    async def resolve_inventory_item(
        self, inventory: "ItemInventory", keyword: str
    ) -> dict | None:
        """解析用户背包中的道具（支持序号、ID、名称）

        参数:
            inventory: ItemInventory 实例
            keyword: 道具序号、ID 或名称

        返回:
            dict | None: 道具信息字典
        """
        user_items = await inventory.get_items()
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


class ItemInventory:
    """道具库存管理类"""

    def __init__(self, user_id: str):
        self.user_id = user_id

    async def get_items(self) -> list[dict]:
        """获取用户道具列表

        返回:
            list[dict]: 道具信息列表
        """
        items_data = await _ItemRepository.get_user_items(self.user_id)
        result: list[dict] = []
        for item_id, count in items_data.items():
            if count <= 0:
                continue
            template = await ItemTemplate.get_template_by_id(item_id)
            if template:
                template["count"] = count
                result.append(template)
        return result

    async def add(self, item_id: str, quantity: int = 1) -> bool:
        """给用户添加道具

        参数:
            item_id: 道具 ID
            quantity: 添加数量

        返回:
            bool: 是否添加成功
        """
        quantity = max(1, quantity)
        template = await ItemTemplate.get_template_by_id(item_id)
        if not template:
            logger.warning(f"道具模板不存在: {item_id}")
            return False

        if await _ItemRepository.incr_item(self.user_id, item_id, quantity):
            logger.info(f"用户 {self.user_id} 获得道具 {item_id} x {quantity}")
            return True
        return False

    async def reduce(self, item_id: str, quantity: int = 1) -> bool:
        """减少用户道具数量

        参数:
            item_id: 道具 ID
            quantity: 减少数量

        返回:
            bool: 是否减少成功
        """
        quantity = max(1, quantity)
        return await _ItemRepository.decr_item(self.user_id, item_id, quantity)

    async def get_count(self, item_id: str) -> int:
        """获取用户特定道具的数量

        参数:
            item_id: 道具 ID

        返回:
            int: 道具数量
        """
        return await _ItemRepository.get_item_count(self.user_id, item_id)

    async def check_enough(self, item_id: str, count: int) -> bool:
        """检查用户道具是否足够

        参数:
            item_id: 道具 ID
            count: 需要检查的数量

        返回:
            bool: 是否足够
        """
        return await self.get_count(item_id) >= count

    async def check_limit(self, item_id: str, limit: int) -> bool:
        """检查用户是否达到限购数量

        参数:
            item_id: 道具 ID
            limit: 限购数量，-1 表示不限购

        返回:
            bool: 是否可以购买
        """
        if limit == -1:
            return True
        items_data = await _ItemRepository.get_user_items(self.user_id)
        return items_data.get(item_id, 0) < limit
