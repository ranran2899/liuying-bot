"""内心状态增强

在EmotionManager基础上提供时间衰减合并、时段能量修正、
关系温暖度截断等增强算法。作为emotion_manager的辅助层。
"""

from datetime import datetime
import time
from typing import Any

__all__ = ["InnerStateHelper"]


_MAX_PENDING_THOUGHTS = 8
"""待处理想法最大数量"""


_MOOD_LOCK_HOURS = 0.5
"""心情锁定阈值（小时）"""


_MOOD_COMPOSITE_HOURS = 2.0
"""心情复合阈值（小时）"""


_ENERGY_COMPROMISE_HOURS = 1.0
"""能量折中阈值（小时）"""


class InnerStateHelper:
    """内心状态辅助算法工具集

    封装时间衰减合并、能量标签归一化、关系温暖度截断等
    增强算法，作为emotion_manager的辅助层。
    """

    @staticmethod
    def _hours_since(updated_at: str) -> float:
        """计算距离上次更新的小时数

        参数:
            updated_at: ISO格式时间戳或空串

        返回:
            float: 小时数，无记录返回999.0
        """
        if not updated_at:
            return 999.0
        try:
            ts = datetime.fromisoformat(updated_at).timestamp()
            return max(0.0, (time.time() - ts) / 3600.0)
        except (ValueError, TypeError):
            return 999.0

    @staticmethod
    def _normalize_energy_label(value: Any) -> str:
        """将能量值统一归一化为中文标签

        LLM解析的energy为float（0-1），当前状态由
        emotion._energy_to_label转为"高"/"中"/"低"标签。
        本函数将float归一化到同一标签空间，避免类型不一致
        导致折中逻辑失效。

        参数:
            value: 能量值（高/中/低标签或0-1浮点数）

        返回:
            str: 高/中/低 标签，无法识别返回原值的字符串形式
        """
        if value is None:
            return ""
        text = str(value).strip()
        if text in ("高", "中", "低"):
            return text
        try:
            f = float(text)
        except (TypeError, ValueError):
            return text
        if f >= 0.7:
            return "高"
        if f >= 0.4:
            return "中"
        return "低"

    @staticmethod
    def merge_state_with_decay(
        current: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """时间衰减合并内心状态

        规则：
        - <0.5h锁定mood不变
        - <2h复合为"{old}，但有些{new}"
        - <1h能量高低折中为"中"
        - pending_thoughts保留最近8条
        - relation_warmth截断[-1.0, 1.0]

        参数:
            current: 当前状态
            incoming: 新状态

        返回:
            dict: 合并后的状态
        """
        merged = dict(current)
        hours = InnerStateHelper._hours_since(
            str(current.get("updated_at", ""))
        )

        current_mood = str(current.get("mood", ""))
        incoming_mood = str(incoming.get("mood", ""))

        if incoming_mood and incoming_mood != current_mood:
            if hours < _MOOD_LOCK_HOURS:
                merged["mood"] = current_mood
            elif hours < _MOOD_COMPOSITE_HOURS:
                merged["mood"] = f"{current_mood}，但有些{incoming_mood}"
            else:
                merged["mood"] = incoming_mood

        current_energy = str(current.get("energy", ""))
        incoming_energy = InnerStateHelper._normalize_energy_label(
            incoming.get("energy", "")
        )
        if (
            current_energy == "高"
            and incoming_energy == "低"
            and hours < _ENERGY_COMPROMISE_HOURS
        ):
            merged["energy"] = "中"
        elif incoming_energy:
            merged["energy"] = incoming_energy

        current_thoughts = current.get("pending_thoughts", [])
        if not isinstance(current_thoughts, list):
            current_thoughts = []
        incoming_thoughts = incoming.get("pending_thoughts", [])
        if not isinstance(incoming_thoughts, list):
            incoming_thoughts = []
        combined = list(current_thoughts) + list(incoming_thoughts)
        if len(combined) > _MAX_PENDING_THOUGHTS:
            combined = combined[-_MAX_PENDING_THOUGHTS:]
        merged["pending_thoughts"] = combined

        current_warmth = current.get("relation_warmth", {})
        if not isinstance(current_warmth, dict):
            current_warmth = {}
        incoming_warmth = incoming.get("relation_warmth", {})
        if not isinstance(incoming_warmth, dict):
            incoming_warmth = {}
        for uid, score in incoming_warmth.items():
            try:
                current_warmth[str(uid)] = (
                    InnerStateHelper.clip_relation_warmth(
                        float(score)
                    )
                )
            except (ValueError, TypeError):
                continue
        merged["relation_warmth"] = current_warmth

        merged["updated_at"] = datetime.now().isoformat()
        return merged

    @staticmethod
    def clip_relation_warmth(score: float) -> float:
        """截断关系温暖度到[-1.0, 1.0]

        参数:
            score: 原始分数

        返回:
            float: 截断后的分数
        """
        return max(-1.0, min(1.0, float(score or 0.0)))
