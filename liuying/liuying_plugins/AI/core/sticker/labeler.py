"""贴纸自动标注

基于视觉LLM分析贴纸图片内容，自动生成情绪与语义标签，
用于贴纸库的自动入库与标签补全。
"""

import json

from liuying.utils.http.http_utils import AsyncHttpx
from liuying.utils.log import logger

from ...config import get_config
from ..llm import llm_helper
from ..vision import summarize_image
from .importer import MOOD_FILENAMES, SEMANTIC_HINTS

__all__ = ["StickerLabeler", "sticker_labeler"]


_DOWNLOAD_TIMEOUT = 15.0
"""贴纸下载超时（秒）"""


_LABEL_PROMPT = """请分析这张贴纸/表情包的内容、情绪与适用场景。
按JSON格式返回，字段：
- mood_tags: 情绪标签数组（从 {moods} 中选择）
- semantic_tags: 语义标签数组（从 {semantics} 中选择）
- description: 简洁描述（不超过30字）

只返回JSON。"""
"""贴纸标注prompt"""


_DESCRIBE_PROMPT = "请用中文简要描述这张贴纸的内容和情绪，不超过30字。"
"""贴纸视觉描述prompt"""


_VALID_MOODS: tuple[str, ...] = tuple(MOOD_FILENAMES.keys())
"""合法情绪标签集合"""


_VALID_SEMANTICS: tuple[str, ...] = tuple(SEMANTIC_HINTS.keys())
"""合法语义标签集合"""


class StickerLabeler:
    """贴纸自动标注器

    下载贴纸图片后，先调用视觉LLM生成描述，
    再用 LLM 解析出情绪与语义标签。
    """

    def __init__(self) -> None:
        """初始化贴纸自动标注器"""

    def _is_enabled(self) -> bool:
        """检查自动标注是否启用

        返回:
            bool: 是否启用
        """
        return bool(get_config("STICKER_AUTO_LABEL_ENABLED", False))

    def _build_label_prompt(self) -> str:
        """构建标注prompt

        返回:
            str: 填充合法标签后的prompt
        """
        moods = "/".join(_VALID_MOODS)
        semantics = "/".join(_VALID_SEMANTICS)
        return _LABEL_PROMPT.format(moods=moods, semantics=semantics)

    def _filter_mood_tags(self, tags: list) -> list[str]:
        """过滤合法的情绪标签

        参数:
            tags: 原始标签列表

        返回:
            list[str]: 合法且去重后的标签
        """
        valid_set = set(_VALID_MOODS)
        seen: set[str] = set()
        result: list[str] = []
        for tag in tags:
            name = str(tag).strip().lower()
            if name in valid_set and name not in seen:
                seen.add(name)
                result.append(name)
        return result

    def _filter_semantic_tags(self, tags: list) -> list[str]:
        """过滤合法的语义标签

        参数:
            tags: 原始标签列表

        返回:
            list[str]: 合法且去重后的标签
        """
        valid_set = set(_VALID_SEMANTICS)
        seen: set[str] = set()
        result: list[str] = []
        for tag in tags:
            name = str(tag).strip().lower()
            if name in valid_set and name not in seen:
                seen.add(name)
                result.append(name)
        return result

    def _parse_label_response(self, response: str) -> list[str]:
        """解析标注响应为标签列表

        参数:
            response: LLM响应文本

        返回:
            list[str]: 情绪+语义标签合并列表
        """
        if not response:
            return []
        try:
            data = json.loads(response.strip())
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug(
                f"贴纸标注响应解析失败: {e}",
                command="AI",
                e=e,
            )
            return []

        if not isinstance(data, dict):
            return []

        mood_tags = self._filter_mood_tags(data.get("mood_tags", []))
        semantic_tags = self._filter_semantic_tags(
            data.get("semantic_tags", [])
        )
        return mood_tags + semantic_tags

    async def _download_image(self, image_url: str) -> bytes | None:
        """下载贴纸图片

        参数:
            image_url: 图片URL

        返回:
            bytes | None: 图片二进制数据，失败返回None
        """
        try:
            return await AsyncHttpx.get_content(
                image_url, timeout=_DOWNLOAD_TIMEOUT
            )
        except Exception as e:
            logger.warning(
                f"贴纸图片下载失败: {image_url}: {e}",
                command="AI",
                e=e,
            )
            return None

    async def label(self, image_url: str) -> list[str]:
        """为贴纸图片生成标签

        参数:
            image_url: 贴纸图片URL

        返回:
            list[str]: 标签列表（情绪+语义），失败返回空列表
        """
        if not self._is_enabled() or not image_url:
            return []

        image_data = await self._download_image(image_url)
        if not image_data:
            return []

        try:
            summary = await summarize_image(
                image_data,
                prompt=_DESCRIBE_PROMPT,
            )
            if not summary.success or not summary.description:
                return []
        except Exception as e:
            logger.warning(
                f"贴纸视觉描述失败: {e}",
                command="AI",
                e=e,
            )
            return []

        try:
            response = await llm_helper.chat_text(
                [
                    {
                        "role": "system",
                        "content": self._build_label_prompt(),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"图片描述: {summary.description}"
                        ),
                    },
                ],
                options={"temperature": 0.2},
            )
            return self._parse_label_response(response)
        except Exception as e:
            logger.warning(
                f"贴纸标注LLM调用失败: {e}",
                command="AI",
                e=e,
            )
            return []


sticker_labeler = StickerLabeler()
"""贴纸自动标注器单例"""
