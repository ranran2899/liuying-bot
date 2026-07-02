"""文本处理工具模块

提供常用的文本处理功能，包括文本截断、敏感词过滤、格式转换等
"""
from collections import Counter
import re

_MD_PATTERNS = [
    (r"\*\*(.+?)\*\*", r"\1"),
    (r"\*(.+?)\*", r"\1"),
    (r"__(.+?)__", r"\1"),
    (r"_(.+?)_", r"\1"),
    (r"`(.+?)`", r"\1"),
    (r"~~(.+?)~~", r"\1"),
    (r"!\[.*?\]\(.*?\)", ""),
    (r"\[(.+?)\]\(.+?\)", r"\1"),
    (r"^#{1,6}\s+", ""),
    (r"^>\s+", ""),
    (r"^[-*+]\s+", ""),
    (r"^\d+\.\s+", ""),
]

_MD_SPECIAL_CHARS = re.compile(r"([\\`*_{}\[\]()#+-.!|])")


class TextUtils:
    """文本处理工具类"""

    URL_PATTERN = re.compile(
        r"https?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+"
    )
    HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
    EMAIL_PATTERN = re.compile(
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    )
    CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fa5]")

    @classmethod
    def truncate(
        cls,
        text: str,
        max_length: int = 100,
        suffix: str = "...",
    ) -> str:
        """截断文本并在末尾添加省略号

        参数:
            text: 原始文本
            max_length: 最大长度（包含后缀）
            suffix: 截断后缀

        返回:
            str: 截断后的文本
        """
        if len(text) <= max_length:
            return text
        if max_length <= len(suffix):
            return suffix[:max_length]
        return text[: max_length - len(suffix)] + suffix

    @classmethod
    def censor_sensitive_words(
        cls,
        text: str,
        sensitive_words: list[str],
        replacement: str = "*",
    ) -> str:
        """过滤替换敏感词

        参数:
            text: 原始文本
            sensitive_words: 敏感词列表
            replacement: 替换字符

        返回:
            str: 处理后的文本
        """
        result = text
        for word in sensitive_words:
            result = result.replace(word, replacement * len(word))
        return result

    @classmethod
    def has_sensitive_words(
        cls,
        text: str,
        sensitive_words: list[str],
    ) -> bool:
        """检查文本是否包含敏感词

        参数:
            text: 要检查的文本
            sensitive_words: 敏感词列表

        返回:
            bool: 是否包含敏感词
        """
        return any(word in text for word in sensitive_words)

    @classmethod
    def strip_html_tags(cls, text: str) -> str:
        """移除HTML标签

        参数:
            text: 包含HTML的文本

        返回:
            str: 移除HTML标签后的文本
        """
        return cls.HTML_TAG_PATTERN.sub("", text)

    @classmethod
    def extract_urls(cls, text: str) -> list[str]:
        """提取文本中的URL

        参数:
            text: 要提取URL的文本

        返回:
            list[str]: URL列表
        """
        return cls.URL_PATTERN.findall(text)

    @classmethod
    def extract_emails(cls, text: str) -> list[str]:
        """提取文本中的邮箱地址

        参数:
            text: 要提取邮箱的文本

        返回:
            list[str]: 邮箱列表
        """
        return cls.EMAIL_PATTERN.findall(text)

    @classmethod
    def extract_chinese(cls, text: str) -> str:
        """提取文本中的中文字符

        参数:
            text: 要提取中文的文本

        返回:
            str: 仅包含中文的文本
        """
        return "".join(cls.CHINESE_PATTERN.findall(text))

    @classmethod
    def markdown_to_plain(cls, text: str) -> str:
        """将Markdown文本转换为纯文本

        参数:
            text: Markdown格式的文本

        返回:
            str: 纯文本
        """
        result = text
        for pattern, repl in _MD_PATTERNS:
            result = re.sub(pattern, repl, result, flags=re.MULTILINE)
        return result

    @classmethod
    def split_text_into_chunks(
        cls,
        text: str,
        chunk_size: int = 2000,
        overlap: int = 0,
        separator: str = "\n",
    ) -> list[str]:
        """将长文本分块

        参数:
            text: 要分块的文本
            chunk_size: 每块最大字符数
            overlap: 块之间重叠字符数
            separator: 分隔符，优先按此分割

        返回:
            list[str]: 分块后的文本列表
        """
        if len(text) <= chunk_size:
            return [text]

        parts = text.split(separator)
        chunks: list[str] = []
        current_chunk = ""

        for part in parts:
            if len(current_chunk) + len(part) + len(separator) <= chunk_size:
                current_chunk += separator + part if current_chunk else part
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                if len(part) > chunk_size:
                    for i in range(0, len(part), chunk_size - overlap):
                        chunks.append(part[i : i + chunk_size])
                    current_chunk = ""
                else:
                    current_chunk = part

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    @classmethod
    def count_words(cls, text: str, top_n: int | None = None) -> list[tuple[str, int]]:
        """统计文本词频

        参数:
            text: 要统计的文本
            top_n: 返回前N个高频词

        返回:
            list[tuple[str, int]]: 词频列表
        """
        words = re.findall(r"\b\w+\b", text.lower())
        counter = Counter(words)
        return counter.most_common(top_n)

    @classmethod
    def calculate_similarity(cls, text1: str, text2: str) -> float:
        """计算两个文本的相似度（基于字符级）

        参数:
            text1: 第一个文本
            text2: 第二个文本

        返回:
            float: 相似度（0.0-1.0）
        """
        if not text1 and not text2:
            return 1.0
        if not text1 or not text2:
            return 0.0
        set1, set2 = set(text1), set(text2)
        return len(set1 & set2) / len(set1 | set2)

    @classmethod
    def escape_markdown(cls, text: str) -> str:
        """转义Markdown特殊字符

        参数:
            text: 要转义的文本

        返回:
            str: 转义后的文本
        """
        return _MD_SPECIAL_CHARS.sub(r"\\\1", text)

    @classmethod
    def pad_string(
        cls,
        text: str,
        width: int,
        fillchar: str = " ",
        align: str = "left",
    ) -> str:
        """填充字符串到指定宽度

        参数:
            text: 原始文本
            width: 目标宽度
            fillchar: 填充字符
            align: 对齐方式 (left, right, center)

        返回:
            str: 填充后的文本
        """
        match align:
            case "left":
                return text.ljust(width, fillchar)
            case "right":
                return text.rjust(width, fillchar)
            case "center":
                return text.center(width, fillchar)
            case _:
                return text

    @classmethod
    def remove_extra_spaces(cls, text: str, replace_newline: bool = False) -> str:
        """移除多余的空格

        参数:
            text: 要处理的文本
            replace_newline: 是否将换行符也替换为空格

        返回:
            str: 处理后的文本
        """
        if replace_newline:
            text = text.replace("\n", " ").replace("\r", " ")
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def extract_numbers(cls, text: str) -> list[float]:
        """提取文本中的数字（整数和浮点数）

        参数:
            text: 要提取数字的文本

        返回:
            list[float]: 数字列表
        """
        return [float(num) for num in re.findall(r"-?\d+(?:\.\d+)?", text)]

    @classmethod
    def is_url(cls, text: str) -> bool:
        """判断文本是否为URL

        参数:
            text: 要判断的文本

        返回:
            bool: 是否为URL
        """
        return bool(cls.URL_PATTERN.fullmatch(text))

    @classmethod
    def is_email(cls, text: str) -> bool:
        """判断文本是否为邮箱

        参数:
            text: 要判断的文本

        返回:
            bool: 是否为邮箱
        """
        return bool(cls.EMAIL_PATTERN.fullmatch(text))

    @classmethod
    def contains_chinese(cls, text: str) -> bool:
        """判断文本是否包含中文

        参数:
            text: 要判断的文本

        返回:
            bool: 是否包含中文
        """
        return bool(cls.CHINESE_PATTERN.search(text))

    @classmethod
    def keyword_match(
        cls,
        text: str,
        keywords: list[str],
        match_all: bool = False,
        case_sensitive: bool = False,
    ) -> bool:
        """关键词匹配检查

        参数:
            text: 要检查的文本
            keywords: 关键词列表
            match_all: 是否需要匹配所有关键词
            case_sensitive: 是否区分大小写

        返回:
            bool: 是否匹配
        """
        if not case_sensitive:
            text = text.lower()
            keywords = [k.lower() for k in keywords]

        check = all if match_all else any
        return check(k in text for k in keywords)

    @classmethod
    def format_bytes(cls, num_bytes: int) -> str:
        """格式化字节数为易读字符串

        参数:
            num_bytes: 字节数

        返回:
            str: 格式化后的大小字符串
        """
        if num_bytes < 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        size = float(num_bytes)
        for unit in units:
            if size < 1024.0:
                return f"{int(size)} {unit}" if unit == "B" else f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} {units[-1]}"
