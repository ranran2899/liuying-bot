"""拟人化发送层

纯函数模块，不发起网络/LLM调用。
提供打字延迟、段间延迟、错别字注入、引用决策、
碎片化分段、Markdown清理等原子函数。
"""

import random
import re

_BASE_TYPING_DELAY = 0.5
"""基础打字延迟（秒）"""

_NIGHT_FACTOR = 1.5
"""深夜延迟放大系数"""

_GAP_MIN = 0.6
"""段间最小延迟（秒）"""

_GAP_JITTER_MIN = 0.2
"""段间抖动下限（秒）"""

_GAP_JITTER_MAX = 0.6
"""段间抖动上限（秒）"""

_TYPO_PAIRS: list[tuple[str, str]] = [
    ("的", "得"),
    ("得", "的"),
    ("在", "再"),
    ("再", "在"),
    ("他", "她"),
    ("她", "他"),
    ("做", "作"),
    ("作", "做"),
    ("那", "哪"),
    ("哪", "那"),
    ("买", "卖"),
    ("卖", "买"),
]
"""易混字对"""

_TYPO_MIN_LEN = 6
"""错别字注入最小文本长度"""

_TYPO_MAX_LEN = 40
"""错别字注入最大文本长度"""

_PARAGRAPH_SPLIT_PATTERN = re.compile(r"\n\s*\n+")
"""段落分隔模式（连续2+换行/空行）"""

_SUBSEGMENT_SPLIT_PATTERN = re.compile(r"([，；,;]+)")
"""子段分隔模式（按中英文逗号、分号）"""

_MARKDOWN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\*\*([^*]+)\*\*"),
    re.compile(r"__([^_]+)__"),
    re.compile(r"\*([^*]+)\*"),
    re.compile(r"_([^_]+)_"),
    re.compile(r"^#{1,6}\s+", re.MULTILINE),
    re.compile(r"^\s*[-*+]\s+", re.MULTILINE),
    re.compile(r"\[([^\]]+)\]\([^)]+\)"),
    re.compile(r"`([^`]+)`"),
    re.compile(r"^>\s+", re.MULTILINE),
)
"""Markdown残留模式元组"""


class HumanizeToolkit:
    """拟人化工具集

    封装打字延迟、段间延迟、错别字注入、Markdown清理、
    碎片化分段等原子操作。所有方法均为静态方法，
    可直接通过类名或模块级别名调用。
    """

    @staticmethod
    def compute_typing_delay(
        text: str,
        cps: float = 7.0,
        max_delay: float = 5.0,
        already_elapsed: float = 0.0,
        is_night: bool = False,
    ) -> float:
        """计算打字延迟

        模拟真人打字速度，减去LLM已耗时避免双重延迟。

        参数:
            text: 回复文本
            cps: 每秒字符数
            max_delay: 最大延迟（秒）
            already_elapsed: LLM生成已耗时（秒）
            is_night: 是否深夜（深夜延迟放大）

        返回:
            float: 实际延迟秒数（>=0）
        """
        if not text:
            return 0.0
        base = _BASE_TYPING_DELAY + random.uniform(0.3, 0.8)
        typing_time = len(text) / max(cps, 0.1)
        delay = base + typing_time - already_elapsed
        if is_night:
            delay *= _NIGHT_FACTOR
        return max(0.0, min(delay, max_delay))

    @staticmethod
    def compute_gap_delay(
        text: str,
        rng: random.Random | None = None,
    ) -> float:
        """计算段间延迟

        用于分段消息之间的间隔。

        参数:
            text: 段文本
            rng: 随机数生成器（可注入便于测试）

        返回:
            float: 段间延迟秒数
        """
        use_rng = rng or random
        jitter = use_rng.uniform(_GAP_JITTER_MIN, _GAP_JITTER_MAX)
        return _GAP_MIN + jitter

    @staticmethod
    def _is_pure_chatty_text(text: str) -> bool:
        """判断是否为纯闲聊短句

        仅对纯闲聊短句注入错别字，避免破坏代码/数字/链接。

        参数:
            text: 待判断文本

        返回:
            bool: 是否为纯闲聊短句
        """
        if not (_TYPO_MIN_LEN <= len(text) <= _TYPO_MAX_LEN):
            return False
        if any(sub in text for sub in ("http", "://", "@", "#")):
            return False
        if any(ch.isdigit() for ch in text):
            return False
        return True

    @staticmethod
    def maybe_inject_typo(
        text: str,
        probability: float = 0.0,
        rng: random.Random | None = None,
    ) -> tuple[str, str | None]:
        """按概率注入错别字

        仅处理纯闲聊短句。返回修正提示，由调用方决定是否跟发。

        参数:
            text: 原始文本
            probability: 注入概率[0,1]
            rng: 随机数生成器

        返回:
            tuple[str, str | None]: (修改后文本, 修正提示)，
                未注入时修正提示为None
        """
        if probability <= 0 or not HumanizeToolkit._is_pure_chatty_text(text):
            return text, None

        use_rng = rng or random
        if use_rng.random() >= probability:
            return text, None

        candidates: list[tuple[int, str, str]] = []
        for idx, ch in enumerate(text):
            for wrong, right in _TYPO_PAIRS:
                if ch == right:
                    candidates.append((idx, wrong, right))
                    break

        if not candidates:
            return text, None

        idx, wrong, right = use_rng.choice(candidates)
        new_text = text[:idx] + wrong + text[idx + 1 :]
        return new_text, right

    @staticmethod
    def normalize_visible_reply_text(text: str) -> str:
        """清理Markdown残留，让回复更像口语短句

        参数:
            text: 原始文本

        返回:
            str: 清理后的文本
        """
        cleaned = (text or "").strip()
        for pattern in _MARKDOWN_PATTERNS:
            if pattern.pattern.startswith(r"\["):
                cleaned = pattern.sub(r"\1", cleaned)
            elif pattern.pattern.startswith(r"`"):
                cleaned = pattern.sub(r"\1", cleaned)
            elif (
                pattern.pattern.startswith(r"\*\*")
                or pattern.pattern.startswith(r"__")
            ):
                cleaned = pattern.sub(r"\1", cleaned)
            elif (
                pattern.pattern.startswith(r"\*")
                or pattern.pattern.startswith(r"_")
            ):
                cleaned = pattern.sub(r"\1", cleaned)
            else:
                cleaned = pattern.sub("", cleaned)
        return cleaned.strip()

    @staticmethod
    def split_text_into_segments(text: str) -> list[str]:
        """将文本按空行切成段落

        只按LLM显式输出的段落分隔（连续2+换行/空行）切分。
        单个句号、问号、感叹号不再触发切分，避免一句完整回复被发成多条消息。

        参数:
            text: 原始文本

        返回:
            list[str]: 段落列表
        """
        if not text:
            return []
        parts = _PARAGRAPH_SPLIT_PATTERN.split((text or "").strip())
        return [p.strip() for p in parts if p and p.strip()]

    @staticmethod
    def split_segment_if_long(
        segment: str,
        max_chars: int,
    ) -> list[str]:
        """超长段按标点二次切分

        参数:
            segment: 单段文本
            max_chars: 单段最大字符数

        返回:
            list[str]: 切分后的段列表
        """
        if max_chars <= 0 or len(segment) <= max_chars:
            return [segment]

        sub_parts = _SUBSEGMENT_SPLIT_PATTERN.split(segment)
        result: list[str] = []
        current: str = ""
        for part in sub_parts:
            if not part:
                continue
            candidate = current + part
            if len(candidate) > max_chars and current:
                result.append(current.strip())
                current = part.lstrip("，；,;")
            else:
                current = candidate
        if current.strip():
            result.append(current.strip())
        return result

    @staticmethod
    def fragment_reply(
        text: str,
        max_segment_chars: int = 40,
    ) -> list[str]:
        """碎片化输出主入口

        先按空行切段，再对超长段做二次切分。

        参数:
            text: 原始回复文本
            max_segment_chars: 单段最大字符数，<=0时不做二次切分

        返回:
            list[str]: 碎片段列表
        """
        cleaned = HumanizeToolkit.normalize_visible_reply_text(text)
        if not cleaned:
            return []
        segments = HumanizeToolkit.split_text_into_segments(cleaned)
        if max_segment_chars > 0:
            expanded: list[str] = []
            for seg in segments:
                expanded.extend(
                    HumanizeToolkit.split_segment_if_long(
                        seg, max_segment_chars
                    )
                )
            segments = expanded
        return [s for s in segments if s]

    @staticmethod
    def build_group_chat_style_prompt() -> str:
        """构建群聊短消息风格prompt

        返回:
            str: 风格提示文本
        """
        return (
            "\n[输出风格] 像QQ群友聊天那样说话："
            "需要多句时拆成1-3条短消息，"
            "条与条之间用空行分隔；"
            "单条尽量不超过40字，口语化，"
            "可以只接半句，不要写成完整段落或书面文。"
        )


# 模块级别名，保持外部导入路径稳定
compute_typing_delay = HumanizeToolkit.compute_typing_delay
compute_gap_delay = HumanizeToolkit.compute_gap_delay
maybe_inject_typo = HumanizeToolkit.maybe_inject_typo
fragment_reply = HumanizeToolkit.fragment_reply
build_group_chat_style_prompt = HumanizeToolkit.build_group_chat_style_prompt
