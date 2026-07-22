"""贴纸语义分析

为每个贴纸打上心情标签和场景标签，供精准贴纸选择使用。
18 种心情标签 + 20 种场景标签，LLM 驱动语义分析，
分析结果缓存避免重复调用。
"""

from dataclasses import dataclass
from enum import StrEnum

from liuying.utils.log import logger

from ...models.sticker_item import StickerItem
from ..json_utils import extract_json_payload
from ..llm import llm_helper
from ..llm.model_router import ROLE_STICKER, model_router


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

_ANALYZE_PROMPT = """你是一个贴纸语义分析助手。
请根据贴纸的描述信息，分析其心情标签和场景标签。

贴纸描述：{description}
贴纸文件名：{filename}

可选心情标签：{moods}
可选场景标签：{scenes}

请输出JSON格式（只输出JSON，不要其他内容）：
{{"mood": "心情标签", "scene": "场景标签", "confidence": 0.0-1.0}}

如果无法判断，mood 或 scene 输出空字符串，confidence 输出 0.0。"""

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
    """

    def __init__(self) -> None:
        """初始化贴纸语义分析器"""
        self._cache: dict[int, StickerSemantics] = {}
        """贴纸ID -> 语义分析结果"""

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
        if cached and cached.analyzed:
            return cached
        result = StickerSemantics(sticker_id=sticker_id)
        if not description and not filename:
            self._update_cache(sticker_id, result)
            return result
        try:
            prompt = _ANALYZE_PROMPT.format(
                description=description[:200],
                filename=filename[:100],
                moods="/".join(_MOOD_VALUES),
                scenes="/".join(_SCENE_VALUES),
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
            logger.debug(
                f"贴纸语义分析失败 id={sticker_id}: {e}",
                command="AI",
                e=e,
            )
        self._update_cache(sticker_id, result)
        return result

    async def analyze_batch(
        self, stickers: list[dict]
    ) -> dict[int, StickerSemantics]:
        """批量分析贴纸语义

        参数:
            stickers: 贴纸字典列表，每项含 id/description/filename

        返回:
            dict: 贴纸ID -> 语义分析结果
        """
        results: dict[int, StickerSemantics] = {}
        for sticker in stickers:
            sid = sticker.get("id", 0)
            desc = sticker.get("description", "")
            fname = sticker.get("filename", "")
            if not sid:
                continue
            result = await self.analyze_sticker(sid, desc, fname)
            results[sid] = result
        return results

    async def analyze_unlabeled_stickers(
        self, limit: int = 20
    ) -> int:
        """分析未标注的贴纸（定时任务入口）

        参数:
            limit: 单次处理上限

        返回:
            int: 处理的贴纸数量
        """
        stickers = await StickerItem.filter(
            is_disabled=False,
        ).limit(limit).all()
        count = 0
        for sticker in stickers:
            if sticker.id in self._cache:
                cached = self._cache[sticker.id]
                if cached.analyzed:
                    continue
            desc = sticker.description or ""
            fname = sticker.name or ""
            result = await self.analyze_sticker(
                sticker.id, desc, fname
            )
            if result.analyzed:
                count += 1
        if count > 0:
            logger.info(
                f"贴纸语义分析完成: {count} 张",
                command="AI",
            )
        return count

    def get_cached(self, sticker_id: int) -> StickerSemantics | None:
        """获取缓存的分析结果

        参数:
            sticker_id: 贴纸ID

        返回:
            StickerSemantics | None: 缓存结果或None
        """
        return self._cache.get(sticker_id)

    def find_by_mood(
        self, mood: str
    ) -> list[int]:
        """按心情标签查找贴纸ID

        参数:
            mood: 心情标签

        返回:
            list[int]: 匹配的贴纸ID列表
        """
        return [
            sid
            for sid, sem in self._cache.items()
            if sem.mood == mood and sem.analyzed
        ]

    def find_by_scene(
        self, scene: str
    ) -> list[int]:
        """按场景标签查找贴纸ID

        参数:
            scene: 场景标签

        返回:
            list[int]: 匹配的贴纸ID列表
        """
        return [
            sid
            for sid, sem in self._cache.items()
            if sem.scene == scene and sem.analyzed
        ]

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

        参数:
            sticker_id: 贴纸ID
            result: 分析结果
        """
        if len(self._cache) >= _MAX_CACHE_SIZE:
            oldest_key = next(iter(self._cache))
            self._cache.pop(oldest_key, None)
        self._cache[sticker_id] = result


sticker_semantics_analyzer = StickerSemanticsAnalyzer()
"""贴纸语义分析器单例"""
