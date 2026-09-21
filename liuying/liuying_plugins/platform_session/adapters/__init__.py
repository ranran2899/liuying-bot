"""适配器加载入口，按已注册适配器动态构建会话抓取器"""

import importlib
from pathlib import Path

from nonebot import get_adapters

from liuying.utils.log import logger

from ..action import ActionExecutor
from ..fetch import InfoFetcher
from ..loader import BaseLoader

root = Path(__file__).parent

# 动态发现子包内的适配器加载器，键为适配器名（与 bot.adapter.get_name() 一致）
loaders: dict[str, BaseLoader] = {}
for _path in root.iterdir():
    if not _path.is_dir() or _path.stem.startswith("_"):
        continue
    try:
        _module = importlib.import_module(f".{_path.stem}", __package__)
        _loader: BaseLoader = getattr(_module, "Loader")()
        loaders[_loader.get_adapter().value] = _loader
    except Exception as e:
        logger.warning(f"加载平台会话适配器模块失败: {_path.stem}", e=e)

INFO_FETCHER_MAPPING: dict[str, InfoFetcher] = {}
ACTION_EXECUTOR_MAPPING: dict[str, ActionExecutor] = {}
try:
    _adapters = get_adapters()
except Exception as e:
    logger.warning("获取 nonebot 已注册适配器失败", e=e)
    _adapters = {}

for _adapter_name in _adapters:
    _loader = loaders.get(_adapter_name)
    if _loader is None:
        logger.warning(f"适配器 {_adapter_name} 暂不支持统一平台会话，已跳过")
        continue
    try:
        INFO_FETCHER_MAPPING[_adapter_name] = _loader.get_fetcher()
    except Exception as e:
        logger.warning(f"加载适配器 {_adapter_name} 的会话抓取器失败", e=e)
    try:
        _executor = _loader.get_executor()
    except Exception as e:
        logger.warning(f"加载适配器 {_adapter_name} 的动作执行器失败", e=e)
    else:
        if _executor is not None:
            ACTION_EXECUTOR_MAPPING[_adapter_name] = _executor


_unsupported: set[str] = set()
"""加载失败或不受支持的适配器名，负缓存避免逐事件重复告警"""


def alter_get_fetcher(adapter_name: str) -> InfoFetcher | None:
    """延迟加载指定适配器的会话抓取器，失败结果会被记住不再重试"""
    if adapter_name in _unsupported:
        return None
    loader = loaders.get(adapter_name)
    if loader is None:
        _unsupported.add(adapter_name)
        logger.warning(f"适配器 {adapter_name} 暂不支持统一平台会话")
        return None
    try:
        fetcher = loader.get_fetcher()
    except Exception as e:
        _unsupported.add(adapter_name)
        logger.warning(f"加载适配器 {adapter_name} 的会话抓取器失败", e=e)
        return None
    INFO_FETCHER_MAPPING[adapter_name] = fetcher
    return fetcher


def get_executor(adapter_name: str) -> ActionExecutor | None:
    """获取指定适配器已注册的动作执行器，未注册时尝试延迟加载"""
    executor = ACTION_EXECUTOR_MAPPING.get(adapter_name)
    if executor is not None:
        return executor
    if adapter_name not in INFO_FETCHER_MAPPING:
        return None
    loader = loaders.get(adapter_name)
    if loader is None:
        return None
    try:
        executor = loader.get_executor()
    except Exception as e:
        logger.warning(f"加载适配器 {adapter_name} 的动作执行器失败", e=e)
        return None
    if executor is not None:
        ACTION_EXECUTOR_MAPPING[adapter_name] = executor
    return executor
