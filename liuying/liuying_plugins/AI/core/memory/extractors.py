"""记忆策展提取器

提供实体识别、偏好检测、记忆质量评分、向量相似度计算等
无状态工具方法，供 MemoryCurator 调用，避免策展器主模块过长。
"""

from dataclasses import dataclass
import math
import re

from ...models.memory_item import MemoryItem

_ENTITY_PATTERN = re.compile(
    r"[\u4e00-\u9fa5]{2,8}|[A-Z][a-z]+(?:\s[A-Z][a-z]+)?"
)
"""实体识别正则（中文2-8字 + 英文首字母大写）"""

_PREFERENCE_KEYWORDS: dict[str, list[str]] = {
    "喜欢": ["喜欢", "爱", "偏好", "最爱", "钟爱"],
    "讨厌": ["讨厌", "恨", "不喜欢", "厌恶", "反感"],
    "想要": ["想要", "希望", "渴望", "期待", "想"],
    "拥有": ["有", "拥有", "养了", "买了", "获得了"],
}
"""偏好关键词映射"""

_STOPWORDS: set[str] = {
    "今天", "昨天", "明天", "现在", "刚才", "之后", "之前",
    "什么", "怎么", "为什么", "如何", "这个", "那个", "这些",
    "那些", "我们", "你们", "他们", "她们", "它们", "自己",
    "的话", "是的", "不是", "可以", "不能", "应该", "可能",
}
"""停用词集合"""


@dataclass(slots=True)
class EntityMention:
    """实体提及

    Attributes:
        name: 实体名
        entity_type: 实体类型
        weight: 权重
        context: 上下文
    """

    name: str
    entity_type: str = "generic"
    weight: float = 1.0
    context: str = ""


class CurationExtractor:
    """记忆策展提取器

    封装实体识别、偏好检测、质量评分、相似度计算等
    无状态工具方法，供 MemoryCurator 调用。
    """

    @staticmethod
    def cosine_similarity(
        a: list[float], b: list[float]
    ) -> float:
        """余弦相似度

        参数:
            a: 向量a
            b: 向量b

        返回:
            float: 相似度（0-1）
        """
        if not a or not b:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return max(0.0, min(1.0, dot / (norm_a * norm_b)))

    @staticmethod
    def extract_entities(text: str) -> list[EntityMention]:
        """从文本中提取实体

        参数:
            text: 输入文本

        返回:
            list[EntityMention]: 实体提及列表
        """
        if not text:
            return []
        mentions: list[EntityMention] = []
        seen: set[str] = set()

        for match in _ENTITY_PATTERN.finditer(text):
            name = match.group().strip()
            if (
                not name
                or name in _STOPWORDS
                or len(name) < 2
                or name in seen
            ):
                continue
            seen.add(name)

            start = max(0, match.start() - 10)
            end = min(len(text), match.end() + 10)
            context = text[start:end]

            entity_type = "generic"
            if any(
                k in context
                for k in ("哥", "姐", "同学", "朋友", "老师")
            ):
                entity_type = "person"
            elif any(
                k in context
                for k in ("游戏", "动漫", "电影", "书", "歌")
            ):
                entity_type = "interest"
            elif any(
                k in context
                for k in ("公司", "学校", "工作", "学习")
            ):
                entity_type = "activity"

            mentions.append(
                EntityMention(
                    name=name,
                    entity_type=entity_type,
                    weight=1.0,
                    context=context,
                )
            )
        return mentions

    @staticmethod
    def detect_preferences(text: str) -> list[dict[str, str]]:
        """检测用户偏好

        参数:
            text: 输入文本

        返回:
            list[dict]: 偏好列表（含type/target/context）
        """
        if not text:
            return []
        preferences: list[dict[str, str]] = []
        for pref_type, keywords in _PREFERENCE_KEYWORDS.items():
            for kw in keywords:
                idx = text.find(kw)
                if idx < 0:
                    continue
                start = idx + len(kw)
                end = min(len(text), start + 20)
                target_text = text[start:end].strip()
                target_text = re.split(
                    r"[，。！？；\s]", target_text
                )[0].strip()
                if target_text and len(target_text) >= 2:
                    preferences.append(
                        {
                            "type": pref_type,
                            "target": target_text,
                            "context": text[
                                max(0, idx - 10):min(
                                    len(text), end
                                )
                            ],
                        }
                    )
                    break
        return preferences

    @staticmethod
    def score_memory_quality(memory: MemoryItem) -> float:
        """评估记忆质量评分

        综合考虑：内容长度、重要性、访问次数、巩固次数、层级。

        参数:
            memory: 记忆项

        返回:
            float: 质量评分（0-1）
        """
        length_score = min(
            1.0, len(memory.summary or "") / 50.0
        )
        salience_score = float(memory.salience or 0.0)
        access_score = min(1.0, memory.access_count * 0.1)
        reinforce_score = min(
            1.0, memory.reinforcement_count * 0.2
        )
        tier_bonus = {
            "semantic": 0.2,
            "episodic": 0.1,
            "working": 0.05,
            "background": 0.0,
        }.get(memory.tier, 0.0)

        score = (
            length_score * 0.2
            + salience_score * 0.3
            + access_score * 0.2
            + reinforce_score * 0.2
            + tier_bonus
        )
        return max(0.0, min(1.0, score))
