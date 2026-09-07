"""渲染结果缓存：内存缓存与磁盘文件缓存的两级实现。"""

from hashlib import sha256
from pathlib import Path

import aiofiles
import orjson as json

from liuying.configs.config import Config
from liuying.configs.path_config import UI_CACHE_PATH
from liuying.services.cache import Cache
from liuying.services.log import logger

from .config import CACHE_CONFIG_KEY, CONFIG_MODULE, RENDER_CACHE_EXPIRE


def render_cache_key(payload: dict) -> str:
    """根据渲染要素生成稳定的缓存键。

    参数:
        payload: 参与哈希的渲染要素（模板、主题、变体、数据）。

    返回:
        str: payload 的 SHA256 十六进制摘要。
    """
    data_bytes = json.dumps(payload, option=json.OPT_SORT_KEYS)
    return sha256(data_bytes).hexdigest()


class RenderCache:
    """渲染图片的两级缓存，内存层使用流萤缓存系统，磁盘层持久化 PNG。"""

    def __init__(self) -> None:
        """初始化内存缓存层。"""
        self._memory = Cache("UI_RENDER", result_type=bytes)

    @property
    def enabled(self) -> bool:
        """是否启用渲染缓存。

        返回:
            bool: 读取 UI.CACHE 配置项的结果。
        """
        return bool(Config.get_config(CONFIG_MODULE, CACHE_CONFIG_KEY))

    async def get(self, cache_key: str) -> bytes | None:
        """读取缓存：先查内存，再查磁盘文件并回填内存。

        参数:
            cache_key: 由 render_cache_key 生成的缓存键。

        返回:
            bytes | None: 缓存的图片字节，未命中时返回 None。
        """
        if (cached := await self._memory.get(cache_key)) is not None:
            logger.debug(f"UI内存缓存命中: {cache_key[:16]}...")
            return cached

        file_path = self._file_path(cache_key)
        if not file_path.exists():
            return None
        try:
            async with aiofiles.open(file_path, "rb") as f:
                image_bytes = await f.read()
        except OSError as e:
            logger.warning(f"UI文件缓存读取失败: {e}", e=e)
            return None
        await self._memory.set(
            cache_key, image_bytes, expire=RENDER_CACHE_EXPIRE
        )
        logger.debug(f"UI文件缓存命中: {cache_key[:16]}...")
        return image_bytes

    async def set(self, cache_key: str, image_bytes: bytes) -> None:
        """写入两级缓存，任一层失败仅告警不中断渲染。

        参数:
            cache_key: 由 render_cache_key 生成的缓存键。
            image_bytes: 渲染生成的图片字节数据。
        """
        try:
            await self._memory.set(
                cache_key, image_bytes, expire=RENDER_CACHE_EXPIRE
            )
            file_path = self._file_path(cache_key)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(image_bytes)
            logger.debug(f"UI缓存写入成功: {cache_key[:16]}...")
        except (OSError, TypeError) as e:
            logger.warning(f"UI缓存写入失败: {e}", e=e)

    async def clear(self) -> None:
        """清空内存缓存。"""
        await self._memory.clear()

    def _file_path(self, cache_key: str) -> Path:
        """返回缓存键对应的磁盘文件路径。

        参数:
            cache_key: 缓存键。

        返回:
            Path: 缓存 PNG 文件路径。
        """
        return UI_CACHE_PATH / f"{cache_key}.png"
