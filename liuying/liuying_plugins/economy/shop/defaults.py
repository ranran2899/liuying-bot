"""商店默认道具配置

定义系统商店启动时自动注册的道具列表。
道具图片默认存放于 IMAGE_PATH/shop 目录下。
所有颜色通过稀有度等级动态获取，禁止硬编码颜色值。
"""

from liuying.configs.path_config import IMAGE_PATH

SHOP_IMAGE_PATH = IMAGE_PATH / "shop"

# 稀有度等级参考：
# 1=普通 2=稀有 3=史诗 4=传说 5=稀世
DEFAULT_ITEMS: list[dict] = [
    {
        "name": "生命药水",
        "id": "item_hp_potion",
        "description": "恢复一定量的生命值，在游戏中使用",
        "type": "消耗品",
        "rarity": 1,
        "image_url": str(SHOP_IMAGE_PATH / "生命药水.png"),
        "is_visible": 1,
        "price": 1000,
        "discount": 100,
        "limit_purchase": -1,
        "limited_time": -1,
    },
    {
        "name": "魔法药水",
        "id": "item_mana_potion",
        "description": "恢复一定量的魔法值，在游戏中使用",
        "type": "消耗品",
        "rarity": 2,
        "image_url": str(SHOP_IMAGE_PATH / "魔法药水.png"),
        "is_visible": 1,
        "price": 1500,
        "discount": 100,
        "limit_purchase": -1,
        "limited_time": -1,
    },
    {
        "name": "幸运符",
        "id": "item_lucky_charm",
        "description": "增加你的幸运值，概率提升奖励",
        "type": "增益道具",
        "rarity": 5,
        "image_url": str(SHOP_IMAGE_PATH / "幸运符.png"),
        "is_visible": 1,
        "price": 5000000,
        "discount": 100,
        "limit_purchase": -1,
        "limited_time": -1,
    },
    {
        "name": "经验书",
        "id": "item_experience_book",
        "description": "直接获得大量经验值，提升等级",
        "type": "消耗品",
        "rarity": 3,
        "image_url": str(SHOP_IMAGE_PATH / "经验书.png"),
        "is_visible": 1,
        "price": 10000,
        "discount": 100,
        "limit_purchase": -1,
        "limited_time": -1,
    },
    {
        "name": "金币袋",
        "id": "item_gold_coin",
        "description": "打开后获得随机数量的金币",
        "type": "消耗品",
        "rarity": 2,
        "image_url": str(SHOP_IMAGE_PATH / "金币袋.png"),
        "is_visible": 1,
        "price": 20000,
        "discount": 100,
        "limit_purchase": -1,
        "limited_time": -1,
    },
    {
        "name": "铁剑",
        "id": "item_iron_sword",
        "description": "增加你的攻击值，提升伤害输出",
        "type": "武器",
        "rarity": 2,
        "image_url": str(SHOP_IMAGE_PATH / "铁剑.png"),
        "is_visible": 1,
        "price": 500,
        "discount": 100,
        "limit_purchase": -1,
        "limited_time": -1,
    },
    {
        "name": "铁盾",
        "id": "item_iron_armor",
        "description": "增加你的防御值，提升伤害减免",
        "type": "防具",
        "rarity": 1,
        "image_url": str(SHOP_IMAGE_PATH / "铁盾.png"),
        "is_visible": 1,
        "price": 400,
        "discount": 100,
        "limit_purchase": -1,
        "limited_time": -1,
    },
    {
        "name": "流萤盲盒",
        "id": "item_blind_box",
        "description": "打开后获得随机物品",
        "type": "消耗品",
        "rarity": 4,
        "image_url": (
            "https://gitee.com/shiranranran/tuku/raw/master/"
            "liuying/touxiang/001.png"
        ),
        "is_visible": 1,
        "price": 30000,
        "discount": 100,
        "limit_purchase": -1,
        "limited_time": -1,
    },
]

__all__ = ["DEFAULT_ITEMS"]
