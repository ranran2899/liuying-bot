"""贴纸语义分析

为每个贴纸打上心情标签和场景标签，供精准贴纸选择使用。
18 种心情标签 + 20 种场景标签，LLM 驱动语义分析，
分析结果缓存避免重复调用，采用 LRU 淘汰策略。
"""

from collections import OrderedDict
from dataclasses import dataclass
from enum import StrEnum

from liuying.utils.log import logger

from ..core.llm import llm_helper
from ..core.llm.model_router import ROLE_STICKER, model_router
from ..core.tools.json_utils import extract_json_payload


class StickerMood(StrEnum):
    """贴纸心情标签

    18 种心情标签覆盖常见情绪表达。
    """

    HAPPY = "开心"
    SAD = "难过"
    ANGRY = "生气"
    SURPRISED = "惊讶"
    AFRAID = "害怕"
    DISGUSTED = "厌恶"
    EXPECTANT = "期待"
    CALM = "平静"
    SMUG = "得意"
    HELPLESS = "无奈"
    SHY = "害羞"
    CONFUSED = "疑惑"
    SPOILED = "撒娇"
    SARCASTIC = "嘲讽"
    CARE = "心疼"
    MISS = "想念"
    ENCOURAGE = "鼓励"
    SLEEPY = "困倦"


class StickerScene(StrEnum):
    """贴纸场景标签

    20 种场景标签覆盖常见使用场景。
    """

    GREETING = "问候"
    FAREWELL = "告别"
    THANK = "感谢"
    APOLOGY = "道歉"
    BLESSING = "祝福"
    COMFORT = "安慰"
    TEASING = "调侃"
    AGREE = "赞同"
    DISAGREE = "反对"
    ASK = "询问"
    ANSWER = "回答"
    EXCLAIM = "感叹"
    SILENCE = "沉默"
    THINKING = "思考"
    WAITING = "等待"
    COMPANY = "陪伴"
    CELEBRATE = "庆祝"
    RECOMMEND = "安利"
    COMPLAINT = "吐槽"
    IDLE = "摸鱼"


_MOOD_VALUES = [m.value for m in StickerMood]
_SCENE_VALUES = [s.value for s in StickerScene]

_MAX_CACHE_SIZE = 500
"""语义分析结果缓存上限"""


@dataclass(slots=True)
class StickerSemantics:
    """贴纸语义分析结果

    Attributes:
        sticker_id: 贴纸ID
        mood: 心情标签
        scene: 场景标签
        confidence: 置信度（0-1）
        analyzed: 是否已分析
    """

    sticker_id: int
    mood: str = ""
    scene: str = ""
    confidence: float = 0.0
    analyzed: bool = False


class StickerSemanticsAnalyzer:
    """贴纸语义分析器

    使用 LLM 为贴纸打上心情和场景标签，
    分析结果缓存在内存中避免重复调用。
    仅成功结果入缓存，失败结果不占位，
    待后续调用重试；缓存按 LRU 策略淘汰。
    """

    def __init__(self) -> None:
        """初始化贴纸语义分析器"""
        self._cache: OrderedDict[int, StickerSemantics] = (
            OrderedDict()
        )
        """贴纸ID -> 语义分析结果（LRU缓存，仅含成功结果）"""

    async def analyze_sticker(
        self,
        sticker_id: int,
        description: str,
        filename: str = "",
    ) -> StickerSemantics:
        """分析单个贴纸的语义

        参数:
            sticker_id: 贴纸ID
            description: 贴纸描述文本
            filename: 贴纸文件名

        返回:
            StickerSemantics: 语义分析结果
        """
        cached = self._cache.get(sticker_id)
        if cached is not None:
            # LRU命中：移至末尾，淘汰时优先弹出最久未用条目
            self._cache.move_to_end(sticker_id)
            return cached

        result = StickerSemantics(sticker_id=sticker_id)
        if not description and not filename:
            # 无有效输入，分析无法成功，不入缓存便于后续重试
            return result
        try:
            prompt = (
                "你是一个贴纸语义分析助手。\n"
                "请根据贴纸的描述信息，分析其心情标签和场景标签。\n\n"
                f"贴纸描述：{description[:200]}\n"
                f"贴纸文件名：{filename[:100]}\n\n"
                f"可选心情标签：{'/'.join(_MOOD_VALUES)}\n"
                f"可选场景标签：{'/'.join(_SCENE_VALUES)}\n\n"
                "请输出JSON格式（只输出JSON，不要其他内容）：\n"
                '{"mood": "心情标签", "scene": "场景标签", "confidence": 0.0-1.0}\n\n'
                "如果无法判断，mood 或 scene 输出空字符串，confidence 输出 0.0。"
            )
            role = model_router.resolve(ROLE_STICKER)
            _, content = await llm_helper.chat(
                [{"role": "user", "content": prompt}],
                model=role.model or None,
                options=role.apply_to_options(),
                provider_name=role.provider or None,
            )
            parsed = self._parse_analysis(content)
            result.mood = parsed.get("mood", "")
            result.scene = parsed.get("scene", "")
            result.confidence = float(
                parsed.get("confidence", 0.0)
            )
            result.analyzed = True
        except Exception as e:
            # 分析失败（analyzed=False）不入缓存，避免失败占位
            logger.debug(
                f"贴纸语义分析失败 id={sticker_id}: {e}",
                command="AI",
                e=e,
            )
            return result
        self._update_cache(sticker_id, result)
        return result

    @staticmethod
    def _parse_analysis(raw: str) -> dict:
        """解析 LLM 分析结果

        参数:
            raw: LLM 返回的原始文本

        返回:
            dict: 解析后的字典
        """
        data = extract_json_payload(raw)
        return data if data is not None else {}

    def _update_cache(
        self, sticker_id: int, result: StickerSemantics
    ) -> None:
        """更新缓存（LRU淘汰）

        新条目写入后移至末尾，超限时从头部弹出
        最久未使用的条目。

        参数:
            sticker_id: 贴纸ID
            result: 分析结果
        """
        self._cache[sticker_id] = result
        self._cache.move_to_end(sticker_id)
        while len(self._cache) > _MAX_CACHE_SIZE:
            self._cache.popitem(last=False)


sticker_semantics_analyzer = StickerSemanticsAnalyzer()
"""贴纸语义分析器单例"""
