"""群风格/群档案

提供群风格提示词注入块与群风格只读访问：风格抽取与持久化由
group_style_autobuild 定时任务负责（写入 GroupContextSnapshot.style
JSON），回复热路径不针对单条消息触发 LLM 抽取，也不回写库。"""

import json
from typing import Any

from liuying.services.cache import CacheDict

from ...models.group_context import GroupContextSnapshot

_STYLE_CACHE_TTL = 3600.0
"""群风格缓存TTL（秒）"""


class ProfileToolkit:
    """群档案工具集

    提供群风格提示词构建等无状态工具方法。
    """

    @staticmethod
    def build_group_style_prompt_block(
        style: dict[str, Any],
    ) -> str:
        """构建群风格prompt注入块

        参数:
            style: 群风格字典

        返回:
            str: prompt文本
        """
        if not style:
            return ""

        tone = style.get("tone", "")
        pace = style.get("pace", "")
        catchphrases = style.get("catchphrases", [])
        taboos = style.get("taboos", [])
        typical = style.get("typical_length", "")

        lines = ["\n\n[群风格参考]"]
        if tone:
            lines.append(f"语气: {tone}")
        if pace:
            lines.append(f"节奏: {pace}")
        if catchphrases:
            phrases = "、".join(str(p) for p in catchphrases[:5])
            lines.append(f"常用语: {phrases}")
        if taboos:
            taboos_str = "、".join(str(t) for t in taboos[:3])
            lines.append(f"避免话题: {taboos_str}")
        if typical:
            lines.append(f"典型句长: {typical}")

        return "\n".join(lines) if len(lines) > 1 else ""


class GroupProfileManager:
    """群档案管理器

    只提供群风格的只读访问（缓存 + 持久化回退），
    抽取与写入由 group_style_autobuild 定时任务负责。
    """

    def __init__(self) -> None:
        """初始化群档案管理器"""
        self._style_cache = CacheDict(
            "AI_GROUP_PROFILE_STYLE", expire=int(_STYLE_CACHE_TTL)
        )
        """群风格缓存：group_id -> style（1小时TTL）"""

    async def get_style(self, group_id: str) -> dict[str, Any]:
        """只读获取群风格（不触发 LLM 抽取、不回写库）

        优先读缓存，未命中时解析群上下文快照中持久化的
        JSON 风格（由 autobuild 任务写入）。

        参数:
            group_id: 群组ID

        返回:
            dict: 群风格字典，未设置或格式非法时返回空字典
        """
        cached = self._style_cache.get(group_id)
        if cached:
            return cached

        style = await self._load_persisted_style(group_id)
        if style:
            self._style_cache.set(group_id, style)
        return style

    @staticmethod
    async def _load_persisted_style(
        group_id: str,
    ) -> dict[str, Any]:
        """从群上下文快照解析持久化的 JSON 风格

        参数:
            group_id: 群组ID

        返回:
            dict: 群风格字典，缺失或非法时返回空字典
        """
        snapshot = await GroupContextSnapshot.get_context(group_id)
        if not snapshot or not snapshot.style:
            return {}
        try:
            data = json.loads(snapshot.style)
        except (json.JSONDecodeError, TypeError):
            return {}
        return data if isinstance(data, dict) else {}


group_profile = GroupProfileManager()
"""群档案管理器单例"""
