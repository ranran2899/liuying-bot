"""
塔罗牌插件配置
"""
from pathlib import Path

import nonebot
from nonebot import logger
from pydantic import BaseModel

from liuying.services.cache import cached
from liuying.utils.http.http_utils import AsyncHttpx

try:
    import orjson as json
except ModuleNotFoundError:
    import json

TAROT_PATH: Path = Path(__file__).parent / "resource"
TAROT_JSON_PATH: Path = Path(__file__).parent / "tarot.json"
OFFICIAL_THEMES: list[str] = ["BilibiliTarot"]

DOWNLOAD_BASE_URL = (
    "https://raw.fgit.ml/MinatoAquaCrews/"
    "nonebot_plugin_tarot/master/nonebot_plugin_tarot/"
)


class PluginConfig(BaseModel, extra="ignore"):
    """塔罗牌插件配置"""

    tarot_path: Path = TAROT_PATH
    tarot_auto_update: bool = False
    nickname: set[str] = {"Bot"}
    tarot_official_themes: list[str] = OFFICIAL_THEMES


driver = nonebot.get_driver()
tarot_config: PluginConfig = PluginConfig.model_validate(
    driver.config.model_dump(exclude_unset=True)
)


class ResourceError(Exception):
    """资源缺失异常"""

    def __init__(self, msg: str):
        super().__init__(msg)
        self.msg = msg


async def download_url(
    name: str, is_json: bool = False
) -> dict[str, ...] | bytes | None:
    """下载远程资源

    参数:
        name: 资源路径
        is_json: 是否以 JSON 格式返回

    返回:
        dict | bytes | None: 下载结果
    """
    url = DOWNLOAD_BASE_URL + name
    try:
        if is_json:
            return await AsyncHttpx.get_json(url, default=None)
        return await AsyncHttpx.get_content(url)
    except Exception:
        logger.warning(f"下载 {url} 失败")
        return None


@driver.on_startup
async def tarot_version_check() -> None:
    """启动时检查 tarot.json 版本并自动更新"""
    if not tarot_config.tarot_path.exists():
        tarot_config.tarot_path.mkdir(parents=True, exist_ok=True)

    cur_version: float = 0
    if TAROT_JSON_PATH.exists():
        data = json.loads(TAROT_JSON_PATH.read_text(encoding="utf-8"))
        cur_version = data.get("version", 0)

    if not tarot_config.tarot_auto_update:
        if not TAROT_JSON_PATH.exists():
            logger.warning("塔罗牌文本资源缺失！请检查！")
            raise ResourceError("缺少必要资源: tarot.json!")
        return

    response = await download_url("tarot.json", is_json=True)
    if response is None:
        if not TAROT_JSON_PATH.exists():
            logger.warning("塔罗牌文本资源缺失！请检查！")
            raise ResourceError("缺少必要资源: tarot.json!")
        return

    version: float = response.get("version", 0)
    if version > cur_version:
        TAROT_JSON_PATH.write_text(
            json.dumps(response, ensure_ascii=False, indent=4),
            encoding="utf-8",
        )
        logger.info(f"已更新 tarot.json, 版本: {cur_version} -> {version}")


@cached(
    "TAROT_IMAGE",
    key_builder=lambda _theme, _type, _name: f"{_theme}:{_type}:{_name}",
    expire=180,
)
async def get_tarot(_theme: str, _type: str, _name: str) -> bytes | None:
    """下载塔罗牌图片并缓存

    参数:
        _theme: 主题名称
        _type: 子类型
        _name: 图片名称

    返回:
        bytes | None: 图片数据，下载失败返回 None
    """
    logger.info(f"正在下载塔罗牌图片 {_theme}/{_type}/{_name}")
    resource = f"resource/{_theme}/{_type}/{_name}"
    data = await download_url(resource)

    if data is None:
        logger.warning(f"下载塔罗牌图片 {_theme}/{_type}/{_name} 失败！")

    return data
