"""道具稀有度系统模块

提供 1-5 级稀有度等级的颜色与描述文本查询。
所有显示颜色通过等级动态获取，禁止硬编码颜色值。
"""

from typing import ClassVar


class RaritySystem:
    """道具稀有度系统

    提供 1-5 级稀有度等级的颜色与描述文本查询。
    所有方法均为类方法，通过等级动态获取显示属性。

    等级说明：
        1 - 普通（灰色）
        2 - 稀有（绿色）
        3 - 史诗（紫色）
        4 - 传说（橙色）
        5 - 稀世（红色）
    """

    # 稀有度档位配置表（按等级升序）
    # 字段：label 名称色 描述色 边框色 光效色 分级前缀
    _PROFILES: ClassVar[dict[int, dict[str, str]]] = {
        1: {
            "label": "普通",
            "name_color": "#888888",
            "description_color": "#9e9e9e",
            "rarity_border": "#9e9e9e",
            "rarity_glow": "",
            "tier_prefix": "",
        },
        2: {
            "label": "稀有",
            "name_color": "#4CAF50",
            "description_color": "#66BB6A",
            "rarity_border": "#4CAF50",
            "rarity_glow": "",
            "tier_prefix": "[稀有] ",
        },
        3: {
            "label": "史诗",
            "name_color": "#9C27B0",
            "description_color": "#AB47BC",
            "rarity_border": "#9C27B0",
            "rarity_glow": "",
            "tier_prefix": "[史诗] ",
        },
        4: {
            "label": "传说",
            "name_color": "#FF9800",
            "description_color": "#FFA726",
            "rarity_border": "#FF9800",
            "rarity_glow": "rgba(255, 152, 0, 0.35)",
            "tier_prefix": "[传说] ",
        },
        5: {
            "label": "稀世",
            "name_color": "#F44336",
            "description_color": "#EF5350",
            "rarity_border": "#F44336",
            "rarity_glow": "rgba(244, 67, 54, 0.45)",
            "tier_prefix": "[稀世] ",
        },
    }

    @staticmethod
    def _normalize(level: int | None) -> int:
        """规范化稀有度等级至 1-5 区间

        参数:
            level: 原始稀有度等级

        返回:
            int: 规范化后的稀有度等级
        """
        if level is None or level < 1:
            return 1
        if level > 5:
            return 5
        return int(level)

    @classmethod
    def _profile(cls, level: int) -> dict[str, str]:
        """获取指定等级的档位配置

        参数:
            level: 稀有度等级

        返回:
            dict: 档位配置字典，等级非法时回退到普通档
        """
        return cls._PROFILES.get(cls._normalize(level), cls._PROFILES[1])

    @classmethod
    def get_label(cls, level: int) -> str:
        """获取稀有度中文标签

        参数:
            level: 稀有度等级

        返回:
            str: 标签文本（普通/稀有/史诗/传说/稀世）
        """
        return cls._profile(level)["label"]

    @classmethod
    def get_name_color(cls, level: int) -> str:
        """获取稀有度对应的名称显示颜色

        参数:
            level: 稀有度等级

        返回:
            str: 十六进制颜色值
        """
        return cls._profile(level)["name_color"]

    @classmethod
    def get_description_color(cls, level: int) -> str:
        """获取稀有度对应的描述显示颜色

        参数:
            level: 稀有度等级

        返回:
            str: 十六进制颜色值
        """
        return cls._profile(level)["description_color"]

    @classmethod
    def get_tier_description(cls, level: int, description: str) -> str:
        """根据稀有度生成分级描述文本

        2级及以上的道具描述前会加上等级前缀，确保描述内容与稀有度匹配。

        参数:
            level: 稀有度等级
            description: 原始描述文本

        返回:
            str: 分级后的描述文本
        """
        if not description:
            return description
        prefix = cls._profile(level)["tier_prefix"]
        if prefix and not description.startswith(prefix):
            return f"{prefix}{description}"
        return description

    @classmethod
    def apply_to_dict(cls, data: dict) -> dict:
        """将稀有度属性注入道具字典

        根据道具字典中的 rarity 字段，动态计算并注入 name_color、
        description_color、rarity_border、rarity_glow、rarity_label
        以及分级描述字段，
        供渲染层直接读取。

        参数:
            data: 原始道具字典，应包含 rarity 字段

        返回:
            dict: 注入稀有度属性后的字典
        """
        level = cls._normalize(data.get("rarity", 1))
        profile = cls._profile(level)
        result = dict(data)
        result["rarity"] = level
        result["rarity_label"] = profile["label"]
        result["name_color"] = profile["name_color"]
        result["description_color"] = profile["description_color"]
        result["rarity_border"] = profile["rarity_border"]
        result["rarity_glow"] = profile["rarity_glow"]
        result["description"] = cls.get_tier_description(
            level, data.get("description", "")
        )
        return result


__all__ = ["RaritySystem"]
