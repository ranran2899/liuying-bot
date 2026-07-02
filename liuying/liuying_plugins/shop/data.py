"""商店数据初始化模块"""

from liuying.configs.path_config import IMAGE_PATH
from liuying.models._bot import ItemTemplate
from liuying.utils.enum import PropHandle
from liuying.utils.log import logger
from liuying.utils.manager.priority_manager import PriorityLifecycle
from liuying.utils.user import UserExp, UserGold

from .handler import UseResult, registry

SHOP_IMAGE_PATH = IMAGE_PATH / "shop"

# 默认商店道具配置
_DEFAULT_ITEMS: list[dict] = [
    {
        "id": "item_hp_potion",
        "name": "生命药水",
        "description": "恢复一定量的生命值，在游戏中使用",
        "price": 1000,
        "type": "消耗品",
        "image_url": str(SHOP_IMAGE_PATH / "生命药水.png"),
        "name_color": "#00FF00",
        "description_color": "#00FF00",
    },
    {
        "id": "item_mana_potion",
        "name": "魔法药水",
        "description": "恢复一定量的魔法值，在游戏中使用",
        "price": 1500,
        "type": "消耗品",
        "image_url": str(SHOP_IMAGE_PATH / "魔法药水.png"),
        "name_color": "#C77DFF",
        "description_color": "#9370DB",
    },
    {
        "id": "item_lucky_charm",
        "name": "幸运符",
        "description": "增加你的幸运值，概率提升奖励",
        "price": 5000000,
        "type": "增益道具",
        "image_url": str(SHOP_IMAGE_PATH / "幸运符.png"),
        "name_color": "#FFD700",
        "description_color": "#FFA500",
    },
    {
        "id": "item_experience_book",
        "name": "经验书",
        "description": "直接获得大量经验值，提升等级",
        "price": 10000,
        "type": "消耗品",
        "image_url": str(SHOP_IMAGE_PATH / "经验书.png"),
        "name_color": "#FF49B4",
        "description_color": "#FF60B9",
    },
    {
        "id": "item_gold_coin",
        "name": "金币袋",
        "description": "打开后获得随机数量的金币",
        "price": 20000,
        "type": "消耗品",
        "image_url": str(SHOP_IMAGE_PATH / "金币袋.png"),
        "name_color": "#FF7700",
        "description_color": "#FF9100",
    },
    {
        "id": "item_iron_sword",
        "name": "铁剑",
        "description": "增加你的攻击值，提升伤害输出",
        "price": 500,
        "type": "武器",
        "image_url": str(SHOP_IMAGE_PATH / "铁剑.png"),
        "name_color": "#FF4500",
        "description_color": "#FF8C00",
    },
    {
        "id": "item_iron_armor",
        "name": "铁盾",
        "description": "增加你的防御值，提升伤害减免",
        "price": 400,
        "type": "防具",
        "image_url": str(SHOP_IMAGE_PATH / "铁盾.png"),
        "name_color": "#0a0000",
        "description_color": "#0a0000",
    },
    {
        "id": "item_blind_box",
        "name": "流萤盲盒",
        "description": "打开后获得随机物品",
        "price": 30000,
        "type": "消耗品",
        "image_url": (
            "https://gitee.com/shiranranran/tuku/raw/master/" "liuying/touxiang/001.png"
        ),
        "name_color": "#d8a8ce",
        "description_color": "#638d7c",
    },
]


@registry.item_use("item_gold_coin", "金币袋")
async def use_gold_coin(user_id: str, item_info: dict, quantity: int = 1) -> UseResult:
    """使用金币袋

    参数:
        user_id: 用户ID
        item_info: 道具信息字典
        quantity: 使用数量

    返回:
        UseResult: 使用结果
    """
    import random

    gold_amount = random.randint(10, 50000) * quantity
    await UserGold.add_user_gold(user_id, gold_amount)
    return UseResult(
        success=True,
        result_type=PropHandle.USE,
        message=f"打开金币袋 x {quantity}，获得 {gold_amount} 金币!",
    )


@registry.item_use("item_experience_book", "经验书")
async def use_exp_book(user_id: str, item_info: dict, quantity: int = 1) -> UseResult:
    """使用经验书

    参数:
        user_id: 用户ID
        item_info: 道具信息字典
        quantity: 使用数量

    返回:
        UseResult: 使用结果
    """
    total_exp = 1000 * quantity
    level, exp, leveled_up = await UserExp.add_level_exp(user_id, total_exp)

    message = f"使用经验书 x {quantity}，获得 {total_exp} 经验值!"
    if leveled_up:
        message += f"\n恭喜升级! 当前等级: {level}"

    return UseResult(
        success=True,
        result_type=PropHandle.USE,
        message=message,
        data={"level": level, "exp": exp, "leveled_up": leveled_up},
    )


@PriorityLifecycle.on_startup(priority=2)
async def init_store_data() -> None:
    """插件启动时初始化商店数据"""
    await register_items(_DEFAULT_ITEMS)
    logger.info("商店道具初始化完成")


async def register_items(items: dict | list[dict]) -> tuple[int, int]:
    """注册道具（委托给 ItemTemplate.batch_register）

    参数:
        items: 道具数据，单个字典或列表

    返回:
        tuple[int, int]: (成功注册数量, 总数量)
    """
    return await ItemTemplate.batch_register(items)


__all__ = ["register_items"]