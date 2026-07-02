"""视觉能力路由探测

检测当前LLM provider的视觉能力支持情况，路由图片处理请求。
支持能力探测缓存、降级策略、能力标签注入。
"""

import base64
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from liuying.services.cache import CacheDict
from liuying.utils.LLM import Capability, llm_manager
from liuying.utils.log import logger

from ...config import get_config

_PROBE_CACHE_TTL_HOURS = 6
"""能力探测缓存TTL（小时）"""

_PROBE_CACHE_TTL_SECONDS = _PROBE_CACHE_TTL_HOURS * 3600
"""能力探测缓存TTL（秒）"""

_PROBE_TEST_PROMPT = "描述这张测试图片"
"""能力探测测试prompt"""

_VISION_MODEL_KEYWORDS: tuple[str, ...] = (
    "gpt-4o", "gpt-4-vision", "gpt-4-turbo",
    "glm-4v", "glm-4-plus", "glm-4.6v",
    "qwen-vl", "qwen2-vl", "qwen-multimodal",
    "claude-3", "gemini", "llava",
    "vision", "multimodal", "visual",
)
"""支持视觉的模型关键词"""

_NON_VISION_KEYWORDS: tuple[str, ...] = (
    "text-only", "audio-only", "embedding",
    "whisper", "tts", "dall-e",
)
"""不支持视觉的模型关键词"""


@dataclass(slots=True)
class VisionCapabilityInfo:
    """视觉能力信息

    Attributes:
        provider: provider名
        model: 模型名
        supports_vision: 是否支持视觉
        confidence: 置信度（0-1）
        detection_method: 检测方式（keyword/probe/config）
        last_check: 最后检测时间
        error: 错误信息
    """

    provider: str = ""
    model: str = ""
    supports_vision: bool = False
    confidence: float = 0.0
    detection_method: str = "keyword"
    last_check: datetime | None = None
    error: str = ""


@dataclass(slots=True)
class VisionRouteResult:
    """视觉路由结果

    Attributes:
        success: 是否成功路由
        provider: 路由到的provider
        model: 路由到的模型
        info: 能力信息
        fallback_used: 是否使用降级
        fallback_reason: 降级原因
    """

    success: bool = False
    provider: str = ""
    model: str = ""
    info: VisionCapabilityInfo | None = None
    fallback_used: bool = False
    fallback_reason: str = ""


class VisionCapabilityRouter:
    """视觉能力路由器

    探测LLM provider的视觉能力，路由图片处理请求。
    支持关键词检测、主动探测、配置声明三种方式。
    """

    def __init__(self) -> None:
        """初始化视觉能力路由器"""
        self._cache = CacheDict(
            "AI_VISION_CAPABILITY", expire=_PROBE_CACHE_TTL_SECONDS
        )
        """能力缓存：key -> VisionCapabilityInfo（6小时TTL）"""
        self._preferred_vision_provider: str | None = None
        """首选视觉provider"""
        self._preferred_vision_model: str | None = None
        """首选视觉模型"""

    def _cache_key(
        self, provider: str, model: str
    ) -> str:
        """生成缓存键

        参数:
            provider: provider名
            model: 模型名

        返回:
            str: 缓存键
        """
        return f"{provider}:{model}"

    def _cache_get(
        self, provider: str, model: str
    ) -> VisionCapabilityInfo | None:
        """从缓存获取

        参数:
            provider: provider名
            model: 模型名

        返回:
            VisionCapabilityInfo | None: 能力信息或None
        """
        key = self._cache_key(provider, model)
        return self._cache.get(key)

    def _cache_set(
        self, info: VisionCapabilityInfo
    ) -> None:
        """设置缓存

        参数:
            info: 能力信息
        """
        key = self._cache_key(info.provider, info.model)
        self._cache.set(key, info)

    def invalidate_cache(self) -> None:
        """清空缓存"""
        self._cache.clear()

    def detect_by_keyword(self, model: str) -> tuple[bool, float]:
        """通过模型名关键词检测视觉能力

        参数:
            model: 模型名

        返回:
            tuple[bool, float]: (是否支持, 置信度)
        """
        if not model:
            return False, 0.0
        model_lower = model.lower()

        for kw in _NON_VISION_KEYWORDS:
            if kw in model_lower:
                return False, 0.9

        for kw in _VISION_MODEL_KEYWORDS:
            if kw in model_lower:
                return True, 0.8

        return False, 0.3

    async def probe_capability(
        self,
        provider: str,
        model: str,
        test_image_data: bytes | None = None,
    ) -> VisionCapabilityInfo:
        """主动探测视觉能力

        参数:
            provider: provider名
            model: 模型名
            test_image_data: 测试图片数据，None时仅检测provider能力

        返回:
            VisionCapabilityInfo: 能力信息
        """
        cached = self._cache_get(provider, model)
        if cached is not None:
            return cached

        info = VisionCapabilityInfo(
            provider=provider,
            model=model,
            last_check=datetime.now(),
        )

        try:
            prov = llm_manager.get_provider(provider)
            if prov is None:
                info.error = f"provider不存在: {provider}"
                self._cache_set(info)
                return info

            chat_cap = prov.get_capability(Capability.CHAT)
            if chat_cap is None:
                info.error = "provider不支持chat能力"
                self._cache_set(info)
                return info

            kw_support, kw_conf = self.detect_by_keyword(model)
            info.detection_method = "keyword"
            info.supports_vision = kw_support
            info.confidence = kw_conf

            if kw_support and test_image_data:
                try:
                    b64 = base64.b64encode(
                        test_image_data
                    ).decode("ascii")
                    messages: list[dict[str, Any]] = [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": _PROBE_TEST_PROMPT,
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{b64}"
                                    },
                                },
                            ],
                        }
                    ]
                    await chat_cap.chat(model, messages)
                    info.detection_method = "probe"
                    info.confidence = 0.95
                except Exception as e:
                    info.supports_vision = False
                    info.confidence = 0.7
                    info.error = f"探测失败: {e}"

            self._cache_set(info)
            return info
        except Exception as e:
            info.error = str(e)
            self._cache_set(info)
            return info

    async def detect_all_providers(self) -> list[VisionCapabilityInfo]:
        """检测所有provider的视觉能力

        返回:
            list[VisionCapabilityInfo]: 能力信息列表
        """
        results: list[VisionCapabilityInfo] = []
        try:
            provider_names = (
                llm_manager.get_available_providers()
                if hasattr(llm_manager, "get_available_providers")
                else []
            )
            for name in provider_names:
                try:
                    prov = llm_manager.get_provider(name)
                    if not prov:
                        continue
                    models = (
                        llm_manager.get_available_model_names()
                        if hasattr(
                            llm_manager, "get_available_model_names"
                        )
                        else []
                    )
                    for model in models[:5]:
                        info = await self.probe_capability(name, model)
                        if info.supports_vision:
                            results.append(info)
                            if self._preferred_vision_provider is None:
                                self._preferred_vision_provider = name
                                self._preferred_vision_model = model
                            break
                except Exception as e:
                    logger.debug(
                        f"检测provider {name} 视觉能力失败: {e}",
                        command="AI",
                        e=e,
                    )
        except Exception as e:
            logger.debug(
                f"枚举providers失败: {e}", command="AI", e=e
            )
        return results

    async def route_vision_request(
        self,
        prefer_provider: str | None = None,
        prefer_model: str | None = None,
    ) -> VisionRouteResult:
        """路由视觉请求到合适的provider

        参数:
            prefer_provider: 首选provider
            prefer_model: 首选模型

        返回:
            VisionRouteResult: 路由结果
        """
        candidates: list[tuple[str, str]] = []
        if prefer_provider and prefer_model:
            candidates.append((prefer_provider, prefer_model))
        if self._preferred_vision_provider and self._preferred_vision_model:
            candidates.append(
                (self._preferred_vision_provider, self._preferred_vision_model)
            )

        try:
            default_provider = get_config("CHAT_PROVIDER", None)
            default_model = get_config("CHAT_MODEL", None)
            if default_provider and default_model:
                candidates.append((default_provider, default_model))
        except Exception:
            pass

        seen: set[str] = set()
        for provider, model in candidates:
            key = self._cache_key(provider, model)
            if key in seen:
                continue
            seen.add(key)
            info = await self.probe_capability(provider, model)
            if info.supports_vision:
                return VisionRouteResult(
                    success=True,
                    provider=provider,
                    model=model,
                    info=info,
                )

        if candidates:
            provider, model = candidates[0]
            info = await self.probe_capability(provider, model)
            return VisionRouteResult(
                success=False,
                provider=provider,
                model=model,
                info=info,
                fallback_used=True,
                fallback_reason="无provider明确支持视觉，降级使用默认chat",
            )

        return VisionRouteResult(
            success=False,
            fallback_used=True,
            fallback_reason="无可用provider",
        )

    def get_capability_summary(self) -> dict[str, Any]:
        """获取能力摘要

        返回:
            dict: 能力摘要字典
        """
        values = self._cache.values()
        return {
            "cached_probes": len(self._cache),
            "preferred_provider": self._preferred_vision_provider,
            "preferred_model": self._preferred_vision_model,
            "vision_supported": any(
                info.supports_vision
                for info in values
                if isinstance(info, VisionCapabilityInfo)
            ),
        }

    def set_preferred(
        self, provider: str, model: str
    ) -> None:
        """设置首选视觉provider

        参数:
            provider: provider名
            model: 模型名
        """
        self._preferred_vision_provider = provider
        self._preferred_vision_model = model
        logger.info(
            f"设置首选视觉provider: {provider}/{model}",
            command="AI",
        )


vision_router = VisionCapabilityRouter()
"""视觉能力路由器单例"""
