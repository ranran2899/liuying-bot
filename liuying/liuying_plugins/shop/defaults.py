"""商店默认道具配置

定义系统商店启动时自动注册的道具列表。
道具图片默认存放于 IMAGE_PATH/shop 目录下。
"""

from liuying.configs.path_config import IMAGE_PATH

SHOP_IMAGE_PATH = IMAGE_PATH / "shop"

DEFAULT_ITEMS: list[dict] = [
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
            "https://gitee.com/shiranranran/tuku/raw/master/"
            "liuying/touxiang/001.png"
        ),
        "name_color": "#d8a8ce",
        "description_color": "#638d7c",
    },
]

__all__ = ["DEFAULT_ITEMS"]
