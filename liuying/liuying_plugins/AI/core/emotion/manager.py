"""情绪状态管理

维护AI对用户的情绪状态（mood/energy/relation_warmth），
对话后通过LLM更新内心状态。
所有状态绑定 persona_name，实现人设间情绪数据隔离。
"""

from datetime import datetime
import json
from typing import Any

from liuying.utils.log import logger

from ...models.emotion_state import EmotionState
from ..context import context_manager
from ..llm import llm_helper as _default_llm_helper
from .inner_state import InnerStateHelper

_DEFAULT_PERSONA = "default"
"""默认人格名（未指定时回退）"""

_INNER_STATE_PROMPT = """请分析以下对话，更新我对这个用户的情绪状态。

当前状态：
- 心情: {mood}
- 能量: {energy}
- 关系温度: {relation_warmth}
- 待处理想法: {pending_thoughts}

对话内容：
{conversation}

请用JSON格式返回更新后的状态，包含以下字段：
- mood: 心情（happy/sad/neutral/excited/angry/calm）
- energy: 能量值（0-1）
- relation_warmth: 关系温度（0-1）
- pending_thoughts: 待处理想法列表

只返回JSON，不要其他内容。"""


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
        llm_helper=None,
        persona_name: str = _DEFAULT_PERSONA,
    ) -> EmotionState:
        """对话后更新情绪状态

        参数:
            user_id: 用户ID
            group_id: 群组ID
            messages: 对话消息列表
            llm_helper: LLM助手，None时延迟导入
            persona_name: bot人格名

        返回:
            EmotionState: 更新后的情绪状态
        """
        if llm_helper is None:
            llm_helper = _default_llm_helper

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

        prompt = _INNER_STATE_PROMPT.format(
            mood=state.mood,
            energy=state.energy,
            relation_warmth=state.relation_warmth,
            pending_thoughts=thoughts,
            conversation=conversation,
        )

        try:
            result = await llm_helper.chat_text(
                [{"role": "user", "content": prompt}],
                options={"temperature": 0.3},
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
        response = response.strip()
        if response.startswith("```"):
            lines = response.split("\n")
            response = "\n".join(
                line for line in lines if not line.startswith("```")
            )
        try:
            data = json.loads(response)
            if not isinstance(data, dict):
                return {}
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
        except (json.JSONDecodeError, ValueError, TypeError) as e:
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
