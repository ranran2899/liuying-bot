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
    ("象", "像"),
    ("像", "象"),
    ("需", "须"),
    ("须", "需"),
    ("以", "已"),
    ("已", "以"),
    ("进", "近"),
    ("近", "进"),
    ("因", "应"),
    ("应", "因"),
    ("坐", "座"),
    ("座", "坐"),
]
"""易混字对（覆盖常见误用，含象/像、需/须、以/已、进/近等）"""

_TYPO_MIN_LEN = 6
"""错别字注入最小文本长度"""

_TYPO_MAX_LEN = 40
"""错别字注入最大文本长度"""

_REACTION_FACE_POOL: dict[str, list[int]] = {
    "positive": [76, 66, 21, 100, 13],
    "neutral": [0, 9, 29, 36, 12],
    "negative": [1, 14, 28, 5, 15],
}
"""表情表态face_id池（按情绪分组：赞/爱心/飞吻/拥抱/微笑；惊讶/尴尬/流汗/疑问/呲牙；撇嘴/难过/惊恐/流泪/酷）"""

_CATCHPHRASE_MAX_LEN = 50
"""口头禅插入的回复最大长度"""

_QUOTE_REPLY_MIN_GAP = 4
"""触发引用回复的最小历史长度"""

_AT_REPLY_PROBABILITY = 0.5
"""@回复触发概率（与引用互斥）"""

_PARAGRAPH_SPLIT_PATTERN = re.compile(r"\n\s*\n+")
"""段落分隔模式（连续2+换行/空行）"""

_SUBSEGMENT_SPLIT_PATTERN = re.compile(r"([，；,;]+)")
"""子段分隔模式（按中英文逗号、分号）"""

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
        调用方需保证text已经过ReplyTextPolicy清理
        （当前唯一调用链 processor -> build_segments 已保证）。

        参数:
            text: 原始回复文本（已清理）
            max_segment_chars: 单段最大字符数，<=0时不做二次切分

        返回:
            list[str]: 碎片段列表
        """
        if not text:
            return []
        segments = HumanizeToolkit.split_text_into_segments(text)
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

    @staticmethod
    def pick_reaction_face_id(
        mood: str = "neutral",
        rng: random.Random | None = None,
    ) -> int:
        """按情绪随机选择表情表态face_id

        参数:
            mood: 情绪倾向（positive/neutral/negative）
            rng: 随机数生成器

        返回:
            int: face_id
        """
        use_rng = rng or random
        pool = _REACTION_FACE_POOL.get(mood) or _REACTION_FACE_POOL["neutral"]
        return use_rng.choice(pool)

    @staticmethod
    def should_quote_reply(
        is_private: bool,
        quote_enabled: bool,
        history_len: int,
        min_gap: int = _QUOTE_REPLY_MIN_GAP,
    ) -> bool:
        """判断是否需要引用回复

        群聊 + 配置开启 + 历史长度达到阈值时引用，避免上下文较长时歧义。

        参数:
            is_private: 是否私聊
            quote_enabled: 引用回复配置是否开启
            history_len: 历史消息条数
            min_gap: 触发引用的最小历史长度

        返回:
            bool: 是否需要引用
        """
        if is_private or not quote_enabled:
            return False
        return history_len >= min_gap

    @staticmethod
    def should_at_target(
        is_private: bool,
        at_enabled: bool,
        is_at_bot: bool,
        should_quote: bool,
        rng: random.Random | None = None,
        probability: float = _AT_REPLY_PROBABILITY,
    ) -> bool:
        """判断是否需要@回复对象

        群聊 + 配置开启 + 用户未直接@bot + 未引用时按概率@。
        与引用互斥，避免一条消息又引用又@显得啰嗦。

        参数:
            is_private: 是否私聊
            at_enabled: @回复配置是否开启
            is_at_bot: 用户是否已@bot
            should_quote: 是否已决定引用回复
            rng: 随机数生成器
            probability: @触发概率

        返回:
            bool: 是否需要@
        """
        if is_private or not at_enabled:
            return False
        if is_at_bot or should_quote:
            return False
        use_rng = rng or random
        return use_rng.random() < probability

    @staticmethod
    def maybe_prepend_catchphrase(
        text: str,
        catchphrases: list[str],
        mood: str = "neutral",
        probability: float = 0.2,
        rng: random.Random | None = None,
    ) -> str:
        """按概率在回复前插入人格口头禅

        仅对短句插入，避免破坏长回复结构。
        mood=positive时提高概率，negative时降低。

        参数:
            text: 原始回复文本
            catchphrases: 口头禅列表
            mood: 当前情绪
            probability: 基础触发概率
            rng: 随机数生成器

        返回:
            str: 可能前置了口头禅的文本
        """
        if not catchphrases or len(text) > _CATCHPHRASE_MAX_LEN:
            return text
        use_rng = rng or random
        adjusted = probability
        if mood == "positive":
            adjusted = min(1.0, probability * 1.5)
        elif mood == "negative":
            adjusted = probability * 0.5
        if use_rng.random() >= adjusted:
            return text
        phrase = use_rng.choice(catchphrases)
        return f"{phrase}{text}"
