"""实体索引服务

基于 LLM 的命名实体识别（人名/地名/时间/事件），
LLM 不可用或解析失败时降级到简易关键词提取。
"""

import json
import re

from liuying.utils.log import logger

from ..llm import llm_helper
from ._common import _extract_entities_simple

_VALID_TYPES = frozenset({"person", "location", "time", "event"})
"""有效实体类型"""

_ENTITY_PROMPT = """请从以下文本中提取命名实体，按类型分类。

文本：{text}

提取以下类型的实体：
- person: 人名
- location: 地名
- time: 时间
- event: 事件

只返回JSON数组，每项含 name 和 type 字段：
[{{"name": "张三", "type": "person"}}, {{"name": "北京", "type": "location"}}]

无实体时返回空数组 []。"""

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)
"""JSON数组提取正则"""

_MAX_TEXT_LENGTH = 1000
"""单次提取文本最大长度"""


class EntityIndexer:
    """实体索引器

    优先调用 LLM 进行命名实体识别（人名/地名/时间/事件），
    LLM 不可用或解析失败时降级到简易关键词提取。
    """

    def _parse_response(self, content: str) -> list[dict]:
        """解析 LLM 返回的实体 JSON

        参数:
            content: LLM 返回文本

        返回:
            list[dict]: 实体列表，每项含 name/type/weight
        """
        match = _JSON_ARRAY_RE.search(content)
        if not match:
            return []
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
        entities: list[dict] = []
        seen: set[str] = set()
        for item in data:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            etype = str(item.get("type", "")).strip().lower()
            if not name or etype not in _VALID_TYPES:
                continue
            if name in seen:
                continue
            seen.add(name)
            entities.append({"name": name, "type": etype, "weight": 1.0})
        return entities

    async def extract(self, text: str) -> list[dict]:
        """提取文本中的命名实体

        优先调用 LLM 提取人名/地名/时间/事件实体，
        失败或无结果时降级到简易关键词提取。

        参数:
            text: 输入文本

        返回:
            list[dict]: 实体列表，每项含 name/type/weight
        """
        if not text or not text.strip():
            return []
        snippet = text[:_MAX_TEXT_LENGTH]
        try:
            content = await llm_helper.chat_text(
                [{"role": "user", "content": _ENTITY_PROMPT.format(text=snippet)}],
                options={"temperature": 0.1},
            )
            entities = self._parse_response(content)
            if entities:
                return entities
            logger.debug(
                "LLM未提取到实体，降级到简易提取",
                command="AI",
            )
        except Exception as e:
            logger.warning(
                f"LLM实体提取失败，降级到简易提取: {e}",
                command="AI",
                e=e,
            )
        return _extract_entities_simple(text)


entity_indexer = EntityIndexer()
"""实体索引器单例"""
