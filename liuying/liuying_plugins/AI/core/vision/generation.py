"""图片生成

封装 LLM helper 的图片生成能力（DALL-E/Gemini等），
提供统一的图片生成接口与尺寸校验。
"""

from liuying.utils.log import logger

from ...config import get_config
from ..llm import llm_helper

__all__ = ["ImageGenerator", "image_generator"]


_VALID_SIZES: frozenset[str] = frozenset({
    "256x256",
    "512x512",
    "1024x1024",
    "1792x1024",
    "1024x1792",
})
"""支持的图片尺寸集合"""


_DEFAULT_SIZE = "1024x1024"
"""默认图片尺寸"""


_DEFAULT_N = 1
"""默认生成数量"""


_MAX_N = 4
"""最大生成数量"""


class ImageGenerator:
    """图片生成器

    通过 llm_helper.image_generate 调用底层 provider
    （如 DALL-E 或 Gemini）生成图片。
    """

    def __init__(self) -> None:
        """初始化图片生成器"""

    def _is_enabled(self) -> bool:
        """检查图片生成是否启用

        返回:
            bool: 是否启用
        """
        return bool(get_config("VISION_ENABLED", True))

    def _normalize_size(self, size: str) -> str:
        """规范化图片尺寸

        参数:
            size: 待校验的尺寸字符串

        返回:
            str: 合法的尺寸字符串，非法时回退默认
        """
        if size in _VALID_SIZES:
            return size
        logger.debug(
            f"图片尺寸不合法，回退默认: {size}",
            command="AI",
        )
        return _DEFAULT_SIZE

    def _normalize_n(self, n: int) -> int:
        """规范化生成数量

        参数:
            n: 待校验的数量

        返回:
            int: 合法的数量（1到_MAX_N之间）
        """
        if n < 1:
            return _DEFAULT_N
        return min(n, _MAX_N)

    async def generate(
        self,
        prompt: str,
        size: str = _DEFAULT_SIZE,
        n: int = _DEFAULT_N,
    ) -> list[str]:
        """生成图片

        参数:
            prompt: 生成提示文本
            size: 图片尺寸（如 1024x1024）
            n: 生成数量（1-4）

        返回:
            list[str]: 图片URL列表，失败返回空列表
        """
        if not self._is_enabled():
            logger.warning("图片生成未启用", command="AI")
            return []

        if not prompt or not prompt.strip():
            logger.warning("图片生成提示为空", command="AI")
            return []

        use_size = self._normalize_size(size)
        use_n = self._normalize_n(n)

        try:
            urls = await llm_helper.image_generate(
                prompt=prompt.strip(),
                size=use_size,
                n=use_n,
            )
            if not urls:
                logger.info(
                    "图片生成返回空结果",
                    command="AI",
                )
                return []
            return [str(u) for u in urls if u]
        except Exception as e:
            logger.warning(
                f"图片生成失败: {e}",
                command="AI",
                e=e,
            )
            return []


image_generator = ImageGenerator()
"""图片生成器单例"""
