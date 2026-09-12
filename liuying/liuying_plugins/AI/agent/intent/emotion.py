"""情绪状态管理

维护AI对用户的情绪状态（mood/energy/relation_warmth），
对话后通过LLM更新内心状态；并附带内心状态增强算法
（时间衰减合并、时段能量修正、关系温暖度截断）。
所有状态绑定 persona_name，实现人设间情绪数据隔离。
情绪分析LLM调用走 intent 角色路由。
"""

from datetime import datetime
import json
import time
from typing import Any

from liuying.utils.log import logger

from ..core.context import context_manager
from ..core.llm import llm_helper as _default_llm_helper
from ..core.llm.model_router import ROLE_INTENT, model_router
from ..core.tools.json_utils import extract_json_payload
from ..models.emotion_state import EmotionState

__all__ = ["EmotionManager", "InnerStateHelper", "emotion_manager"]

_DEFAULT_PERSONA = "default"
"""默认人格名（未指定时回退）"""


class EmotionManager:
    """情绪状态管理器

    管理AI对每个用户的情绪状态，对话后通过LLM更新。
    所有状态绑定 persona_name，实现人设间情绪数据隔离。
    """

    async def get_state(
        self,
        user_id: str,
        group_id: str | None = None,
        persona_name: str = _DEFAULT_PERSONA,
    ) -> EmotionState:
        """获取情绪状态

        参数:
            user_id: 用户ID
            group_id: 群组ID
            persona_name: bot人格名

        返回:
            EmotionState: 情绪状态（不存在时创建默认）
        """
        return await EmotionState.get_state(
            user_id, group_id, persona_name=persona_name
        )

    async def update_after_chat(
        self,
        user_id: str,
        group_id: str | None,
        messages: list[dict[str, str]],
        persona_name: str = _DEFAULT_PERSONA,
    ) -> EmotionState:
        """对话后更新情绪状态

        参数:
            user_id: 用户ID
            group_id: 群组ID
            messages: 对话消息列表
            persona_name: bot人格名

        返回:
            EmotionState: 更新后的情绪状态
        """
        state = await self.get_state(
            user_id, group_id, persona_name=persona_name
        )
        try:
            thoughts = json.loads(state.pending_thoughts or "[]")
        except (json.JSONDecodeError, TypeError):
            thoughts = []

        conversation = "\n".join(
            f"{msg.get('role', 'user')}: {msg.get('content', '')}"
            for msg in messages[-10:]
        )

        prompt = (
            "请分析以下对话，更新我对这个用户的情绪状态。\n\n"
            "当前状态：\n"
            f"- 心情: {state.mood}\n"
            f"- 能量: {state.energy}\n"
            f"- 关系温度: {state.relation_warmth}\n"
            f"- 待处理想法: {thoughts}\n\n"
            "对话内容：\n"
            f"{conversation}\n\n"
            "请用JSON格式返回更新后的状态，包含以下字段：\n"
            "- mood: 心情（happy/sad/neutral/excited/angry/calm）\n"
            "- energy: 能量值（0-1）\n"
            "- relation_warmth: 关系温度（0-1）\n"
            "- pending_thoughts: 待处理想法列表\n\n"
            "只返回JSON，不要其他内容。"
        )

        try:
            role = model_router.resolve(ROLE_INTENT)
            result = await _default_llm_helper.chat_text(
                [{"role": "user", "content": prompt}],
                model=role.model or None,
                options=role.apply_to_options({"temperature": 0.3}),
                provider_name=role.provider or None,
            )
            new_state = self._parse_state_response(result)
            current_state = self._state_to_dict(state, user_id, thoughts)
            merged = InnerStateHelper.merge_state_with_decay(current_state, new_state)
            merged = self._merge_state(merged, self._get_time_period())
            return await self._persist_merged_state(
                merged, user_id, group_id, persona_name
            )
        except Exception as e:
            logger.warning(
                f"更新情绪状态失败: {e}", command="AI", e=e
            )
            return state

    def _state_to_dict(
        self,
        state: EmotionState,
        user_id: str,
        thoughts: list[str],
    ) -> dict:
        """将EmotionState转换为内心状态字典

        参数:
            state: 情绪状态模型
            user_id: 用户ID
            thoughts: 待处理想法列表

        返回:
            dict: 内心状态字典
        """
        updated_at = ""
        if state.updated_at:
            updated_at = (
                state.updated_at.isoformat()
                if isinstance(state.updated_at, datetime)
                else str(state.updated_at)
            )
        return {
            "mood": state.mood,
            "energy": self._energy_to_label(state.energy),
            "relation_warmth": {user_id: float(state.relation_warmth)},
            "pending_thoughts": thoughts,
            "updated_at": updated_at,
        }

    async def _persist_merged_state(
        self,
        merged: dict,
        user_id: str,
        group_id: str | None,
        persona_name: str = _DEFAULT_PERSONA,
    ) -> EmotionState:
        """持久化合并后的内心状态

        参数:
            merged: 合并后的状态字典
            user_id: 用户ID
            group_id: 群组ID
            persona_name: bot人格名

        返回:
            EmotionState: 更新后的情绪状态
        """
        energy = merged.get("energy", 0.7)
        energy_value = self._energy_to_float(energy)

        warmth_dict = merged.get("relation_warmth", {})
        if isinstance(warmth_dict, dict):
            warmth = float(warmth_dict.get(user_id, 0.3))
        else:
            warmth = float(warmth_dict or 0.3)

        pending = merged.get("pending_thoughts", [])
        if not isinstance(pending, list):
            pending = []

        return await EmotionState.update_state(
            user_id=user_id,
            mood=merged.get("mood"),
            energy=energy_value,
            relation_warmth=max(0.0, min(1.0, warmth)),
            pending_thoughts=pending,
            group_id=group_id,
            persona_name=persona_name,
        )

    def _energy_to_label(self, energy: float) -> str:
        """将能量值转换为中文标签

        参数:
            energy: 0-1能量值

        返回:
            str: 高/中/低
        """
        if energy >= 0.7:
            return "高"
        if energy >= 0.4:
            return "中"
        return "低"

    def _energy_to_float(self, energy: Any) -> float:
        """将能量标签或数字转换为0-1浮点数

        参数:
            energy: 能量值（高/中/低或数字）

        返回:
            float: 0-1能量值
        """
        if isinstance(energy, int | float):
            return max(0.0, min(1.0, float(energy)))
        match str(energy).strip():
            case "高":
                return 0.8
            case "中":
                return 0.5
            case "低":
                return 0.2
            case _:
                return 0.5

    def _parse_state_response(self, response: str) -> dict:
        """解析LLM返回的情绪状态

        参数:
            response: LLM响应文本

        返回:
            dict: 解析后的状态字典
        """
        data = extract_json_payload(response)
        if data is None:
            return {}
        try:
            if "mood" in data and data["mood"] not in (
                "happy",
                "sad",
                "neutral",
                "excited",
                "angry",
                "calm",
            ):
                data["mood"] = "neutral"
            if "energy" in data:
                data["energy"] = max(0.0, min(1.0, float(data["energy"])))
            if "relation_warmth" in data:
                data["relation_warmth"] = max(
                    0.0, min(1.0, float(data["relation_warmth"]))
                )
            return data
        except (ValueError, TypeError) as e:
            logger.debug(
                f"解析情绪状态响应失败: {e}", command="AI"
            )
            return {}

    def _get_time_period(self) -> str:
        """获取当前时段

        返回:
            str: 时段名称
        """
        return context_manager.get_current_time_period()

    def _merge_state(self, state: dict, time_period: str) -> dict:
        """时段合理性纠偏

        深夜能量自动降级，避免AI在深夜过于活跃。

        参数:
            state: 状态字典
            time_period: 时段名称

        返回:
            dict: 纠偏后的状态字典
        """
        if time_period == "深夜":
            energy = self._energy_to_float(state.get("energy", 0.7))
            state["energy"] = min(energy, 0.4)
        return state

    def build_emotion_prompt(self, state: EmotionState) -> str:
        """生成情绪上下文注入块

        参数:
            state: 情绪状态

        返回:
            str: 情绪上下文提示文本
        """
        try:
            thoughts = json.loads(state.pending_thoughts or "[]")
        except (json.JSONDecodeError, TypeError):
            thoughts = []

        thoughts_str = (
            "、".join(thoughts[:3]) if thoughts else "无"
        )
        return (
            f"\n\n[当前情绪状态]\n"
            f"心情: {state.mood}\n"
            f"能量: {state.energy:.2f}\n"
            f"关系温度: {state.relation_warmth:.2f}\n"
            f"待处理想法: {thoughts_str}"
        )

    async def build_emotion_prompt_for_user(
        self,
        user_id: str,
        group_id: str | None = None,
        persona_name: str = _DEFAULT_PERSONA,
    ) -> str:
        """为用户构建情绪提示

        参数:
            user_id: 用户ID
            group_id: 群组ID
            persona_name: bot人格名

        返回:
            str: 情绪上下文提示文本
        """
        state = await self.get_state(
            user_id, group_id, persona_name=persona_name
        )
        return self.build_emotion_prompt(state)


emotion_manager = EmotionManager()
"""情绪状态管理器单例"""


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
        if not updated_at or not isinstance(updated_at, str):
            return 999.0
        ts = datetime.fromisoformat(updated_at).timestamp()
        return max(0.0, (time.time() - ts) / 3600.0)

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
        if isinstance(value, int | float) and not isinstance(
            value, bool
        ):
            f = float(value)
            if f >= 0.7:
                return "高"
            if f >= 0.4:
                return "中"
            return "低"
        text = str(value).strip()
        if text in ("高", "中", "低"):
            return text
        return text

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
            if not isinstance(score, int | float) or isinstance(
                score, bool
            ):
                continue
            current_warmth[str(uid)] = (
                InnerStateHelper.clip_relation_warmth(
                    float(score)
                )
            )
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
