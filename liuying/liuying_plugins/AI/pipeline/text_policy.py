"""回复文本策略

剥离模型输出中的 Markdown 格式语法，让聊天回复像真人而非文档。
支持围栏代码块、行内代码、加粗/斜体、标题、列表、表格、引用、
链接、图片、URL 等格式的结构化清理。

本模块为纯函数逻辑，不发起网络/LLM 调用。
"""

import re
from typing import Any

__all__ = ["ReplyTextPolicy"]


_IMAGE_B64_RE = re.compile(
    r"\[IMAGE_B64\][A-Za-z0-9+/=\r\n]+\[/IMAGE_B64\]"
)
"""图片Base64标记模式"""

_FENCED_CODE_RE = re.compile(
    r"```[A-Za-z0-9_-]*\s*\n?([\s\S]*?)```", re.MULTILINE
)
"""围栏代码块模式"""

_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
"""Markdown图片语法模式"""

_MARKDOWN_LINK_RE = re.compile(
    r"\[([^\]]+)\]\((?:https?://|file://|/)[^)]+\)"
)
"""Markdown链接语法模式"""

_BOLD_RE = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1", re.DOTALL)
"""加粗标记模式"""

_ITALIC_STAR_RE = re.compile(
    r"(?<!\*)\*(?=\S)(.+?)(?<=\S)\*(?!\*)", re.DOTALL
)
"""星号斜体标记模式"""

_ITALIC_UNDER_RE = re.compile(
    r"(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)", re.DOTALL
)
"""下划线斜体标记模式"""

_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
"""行内代码标记模式"""

_SETEXT_HEADING_RE = re.compile(
    r"^\s*(?:={3,}|-{3,})\s*$", re.MULTILINE
)
"""Setext标题下划线模式"""

_TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$",
    re.MULTILINE,
)
"""表格分隔行模式"""

_HORIZONTAL_RULE_RE = re.compile(
    r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", re.MULTILINE
)
"""水平线模式"""

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
"""ATX标题前缀模式"""

_BLOCKQUOTE_RE = re.compile(r"^\s{0,3}>\s?", re.MULTILINE)
"""引用块前缀模式"""

_TASK_BULLET_RE = re.compile(
    r"^\s*[-*+]\s+\[[ xX]\]\s+", re.MULTILINE
)
"""任务列表项模式"""

_BULLET_RE = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
"""无序列表项模式"""

_NUMBERED_RE = re.compile(r"^\s*\d{1,3}[.)]\s+", re.MULTILINE)
"""有序列表项模式"""

_URL_RE = re.compile(r"https?://\S+")
"""裸URL模式"""

_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
"""连续多个空行模式"""

_SPACE_TAB_RE = re.compile(r"[ \t]+")


class ReplyTextPolicy:
    """回复文本策略

    封装 Markdown 格式清理能力，将模型输出的结构化文档语法
    转换为适合聊天的纯文本。所有方法均为静态方法，
    可直接通过类名调用。

    清理范围：
    - 围栏代码块：保留代码内容，去除```标记
    - 行内代码：保留内容，去除`标记
    - 加粗/斜体：保留内容，去除*/_标记
    - 标题：去除#前缀和Setext下划线
    - 列表：去除-/*/数字前缀
    - 表格分隔行：移除
    - 水平线：移除
    - 引用块：去除>前缀
    - 链接：保留显示文本，去除URL
    - 图片：保留alt文本
    - 裸URL：移除
    - 图片Base64标记：保护不被清理
    - 多余空行：压缩为最多1个空行
    """

    _SPACE_TAB_RE = _SPACE_TAB_RE
    """空格与制表符替换正则"""

    @staticmethod
    def _protect_image_markers(
        text: str,
    ) -> tuple[str, list[str]]:
        """保护图片Base64标记不被清理

        参数:
            text: 原始文本

        返回:
            tuple[str, list[str]]: (替换后文本, 被保护的标记列表)
        """
        markers: list[str] = []

        def _replace(match: re.Match[str]) -> str:
            markers.append(match.group(0))
            return f"@@AI_IMAGE_B64_{len(markers) - 1}@@"

        return _IMAGE_B64_RE.sub(_replace, text), markers

    @staticmethod
    def _restore_image_markers(
        text: str, markers: list[str]
    ) -> str:
        """恢复被保护的图片Base64标记

        参数:
            text: 清理后文本
            markers: 被保护的标记列表

        返回:
            str: 恢复标记后的文本
        """
        restored = text
        for index, marker in enumerate(markers):
            restored = restored.replace(
                f"@@AI_IMAGE_B64_{index}@@", marker
            )
        return restored

    @staticmethod
    def normalize_visible_reply_text(text: Any) -> str:
        """清理回复文本中的 Markdown 格式

        剥离模型输出中的结构化文档语法，保留纯文本内容。
        图片Base64标记会被保护不被清理。

        参数:
            text: 原始回复文本

        返回:
            str: 清理后的纯文本
        """
        raw = str(text or "").strip()
        if not raw:
            return ""

        cleaned, image_markers = (
            ReplyTextPolicy._protect_image_markers(raw)
        )
        cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")

        cleaned = _FENCED_CODE_RE.sub(
            lambda m: str(m.group(1) or "").strip(), cleaned
        )
        cleaned = _MARKDOWN_IMAGE_RE.sub(
            lambda m: str(m.group(1) or "").strip(), cleaned
        )
        cleaned = _MARKDOWN_LINK_RE.sub(
            lambda m: str(m.group(1) or "").strip(), cleaned
        )
        cleaned = _INLINE_CODE_RE.sub(
            lambda m: str(m.group(1) or ""), cleaned
        )
        cleaned = _BOLD_RE.sub(
            lambda m: str(m.group(2) or ""), cleaned
        )
        cleaned = _ITALIC_STAR_RE.sub(
            lambda m: str(m.group(1) or ""), cleaned
        )
        cleaned = _ITALIC_UNDER_RE.sub(
            lambda m: str(m.group(1) or ""), cleaned
        )
        cleaned = _SETEXT_HEADING_RE.sub("", cleaned)
        cleaned = _TABLE_SEPARATOR_RE.sub("", cleaned)
        cleaned = _HORIZONTAL_RULE_RE.sub("", cleaned)
        cleaned = _HEADING_RE.sub("", cleaned)
        cleaned = _BLOCKQUOTE_RE.sub("", cleaned)
        cleaned = _TASK_BULLET_RE.sub("", cleaned)
        cleaned = _BULLET_RE.sub("", cleaned)
        cleaned = _NUMBERED_RE.sub("", cleaned)
        cleaned = _URL_RE.sub("", cleaned)

        lines = [
            ReplyTextPolicy._SPACE_TAB_RE.sub(" ", line).strip()
            for line in cleaned.split("\n")
        ]
        compacted: list[str] = []
        blank_seen = False
        for line in lines:
            if not line:
                if compacted and not blank_seen:
                    compacted.append("")
                    blank_seen = True
                continue
            compacted.append(line)
            blank_seen = False
        cleaned = "\n".join(compacted).strip()
        cleaned = _MULTI_NEWLINE_RE.sub("\n\n", cleaned)
        return ReplyTextPolicy._restore_image_markers(
            cleaned, image_markers
        ).strip()

    @staticmethod
    def looks_like_markdown_reply(text: Any) -> bool:
        """检测文本是否包含 Markdown 格式

        参数:
            text: 待检测文本

        返回:
            bool: 是否包含Markdown格式
        """
        raw = str(text or "")
        if not raw.strip():
            return False
        return bool(
            _FENCED_CODE_RE.search(raw)
            or _MARKDOWN_LINK_RE.search(raw)
            or _MARKDOWN_IMAGE_RE.search(raw)
            or _BOLD_RE.search(raw)
            or _ITALIC_STAR_RE.search(raw)
            or _HEADING_RE.search(raw)
            or _TASK_BULLET_RE.search(raw)
            or _BULLET_RE.search(raw)
            or _NUMBERED_RE.search(raw)
            or _BLOCKQUOTE_RE.search(raw)
            or _TABLE_SEPARATOR_RE.search(raw)
        )
