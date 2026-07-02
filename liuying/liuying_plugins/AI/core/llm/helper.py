"""LLM调用封装

对接 liuying.utils.LLM.llm_manager，提供统一的对话/嵌入/TTS/图片调用接口。
通过 provider_router 实现多 provider 自动容错切换。
"""

from collections.abc import AsyncIterator
from typing import Any

from liuying.utils.LLM import Capability, llm_manager
from liuying.utils.log import logger

from ...config import get_config
from .provider_router import provider_router


class LLMHelper:
    """LLM调用助手

    封装llm_manager，提供统一的对话/嵌入/TTS/图片生成接口。
    通过provider_router实现多provider自动容错切换。
    """

    def _get_provider(self, name: str | None = None):
        """获取provider实例

        参数:
            name: provider名称，None时用配置或默认

        返回:
            BaseProvider: provider实例

        异常:
            ValueError: provider未配置或不存在
        """
        provider_name = name or get_config("CHAT_PROVIDER", None)
        if provider_name:
            provider = llm_manager.get_provider(provider_name)
            if provider:
                return provider
            raise ValueError(f"LLM provider '{provider_name}' 未找到")
        provider = llm_manager.get_default_provider()
        if not provider:
            raise ValueError("无可用LLM provider，请检查配置")
        return provider

    def _build_candidates(
        self,
        capability: Capability,
        preferred: str | None = None,
    ) -> list[str]:
        """构建支持指定能力的provider候选列表

        参数:
            capability: 能力类型
            preferred: 优先使用的provider名

        返回:
            list[str]: 候选provider名列表
        """
        names: list[str] = []

        def _supports(name: str) -> bool:
            """检查provider是否支持指定能力

            参数:
                name: provider名

            返回:
                bool: 是否支持
            """
            provider = llm_manager.get_provider(name)
            return bool(provider and provider.get_capability(capability))

        chat_provider = get_config("CHAT_PROVIDER", None)
        if preferred and _supports(preferred):
            names.append(preferred.lower())
        if (
            chat_provider
            and chat_provider.lower() not in names
            and _supports(chat_provider)
        ):
            names.append(chat_provider.lower())

        for cfg in llm_manager.get_all_providers():
            pname = cfg.name.lower()
            if pname in names:
                continue
            provider = llm_manager.get_provider(pname)
            if provider and provider.get_capability(capability):
                names.append(pname)
        return names

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        options: dict[str, Any] | None = None,
        provider_name: str | None = None,
    ) -> tuple[str, str]:
        """对话调用

        返回思考链与回复内容两个字段。
        根据 THINKING_MODE_ENABLED 配置向 provider 传递深度思考请求标志。

        参数:
            messages: 消息列表
            model: 模型名，None时用配置默认
            options: 额外选项
            provider_name: 指定provider

        返回:
            tuple[str, str]: (reasoning_content, content)
                - reasoning_content: 思考链内容，无思考链时为空串
                - content: 正常回复内容

        异常:
            ValueError: provider未配置
            Exception: 调用失败
        """
        use_model = model or get_config("CHAT_MODEL", None) or ""
        candidates = self._build_candidates(
            Capability.CHAT,
            provider_name or get_config("CHAT_PROVIDER", None),
        )
        call_options = {
            **(options or {}),
            "reasoning_enabled": get_config(
                "THINKING_MODE_ENABLED", False
            ),
        }

        async def _call(name: str) -> tuple[str, str]:
            provider = llm_manager.get_provider(name)
            if not provider:
                raise ValueError(f"provider '{name}' 不存在")
            chat_cap = provider.get_capability(Capability.CHAT)
            if not chat_cap:
                raise ValueError(
                    f"provider '{name}' 不支持对话能力"
                )
            return await chat_cap.chat(
                use_model, messages, call_options
            )

        result = await provider_router.call_with_failover(
            candidates, _call
        )
        logger.debug(
            f"LLM对话调用成功，模型: {use_model}",
            command="AI",
        )
        return result

    async def chat_text(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        options: dict[str, Any] | None = None,
        provider_name: str | None = None,
    ) -> str:
        """对话调用（文本模式）

        模型返回思考链时，将思考链拼接到回复前。
        适用于只需要最终文本的场景，无需调用方自行处理 tuple。

        参数:
            messages: 消息列表
            model: 模型名，None时用配置默认
            options: 额外选项
            provider_name: 指定provider

        返回:
            str: AI回复文本（含思考链时自动拼接）
        """
        reasoning, content = await self.chat(
            messages, model, options, provider_name
        )
        if reasoning:
            return f"{reasoning}\n\n{content}"
        return content

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        options: dict[str, Any] | None = None,
        provider_name: str | None = None,
    ) -> AsyncIterator[str]:
        """流式对话调用

        参数:
            messages: 消息列表
            model: 模型名
            options: 额外选项
            provider_name: 指定provider

        返回:
            AsyncIterator[str]: 流式回复文本片段

        说明:
            流式调用暂不支持中途切换provider，仅做首选provider冷却检测。
            若首选provider冷却，则回退到非流式chat_text并一次性yield结果。
        """
        preferred = provider_name or get_config("CHAT_PROVIDER", None)
        if preferred and provider_router.is_cooling(preferred):
            logger.warning(
                f"provider {preferred} 处于冷却期，流式调用回退到非流式",
                command="AI",
            )
            text = await self.chat_text(
                messages, model, options, preferred
            )
            yield text
            return

        provider = self._get_provider(provider_name)
        chat_cap = provider.get_capability(Capability.CHAT)
        if not chat_cap:
            raise ValueError(
                f"provider '{provider.name}' 不支持流式对话"
            )
        use_model = model or get_config("CHAT_MODEL", None) or ""
        call_options = {
            **(options or {}),
            "reasoning_enabled": get_config(
                "THINKING_MODE_ENABLED", False
            ),
        }
        async for chunk in chat_cap.chat_stream(
            use_model, messages, call_options
        ):
            yield chunk

    async def embedding(
        self,
        text: str,
        model: str | None = None,
        provider_name: str | None = None,
    ) -> list[float]:
        """生成嵌入向量

        参数:
            text: 输入文本
            model: 嵌入模型名
            provider_name: 指定provider

        返回:
            list[float]: 嵌入向量

        异常:
            ValueError: provider不支持嵌入
        """
        use_model = model or get_config("EMBEDDING_MODEL", None) or ""
        candidates = self._build_candidates(
            Capability.EMBEDDING,
            provider_name or get_config("EMBEDDING_PROVIDER", None),
        )

        async def _call(name: str) -> list[float]:
            provider = llm_manager.get_provider(name)
            if not provider:
                raise ValueError(f"provider '{name}' 不存在")
            emb_cap = provider.get_capability(Capability.EMBEDDING)
            if not emb_cap:
                raise ValueError(
                    f"provider '{name}' 不支持嵌入能力"
                )
            return await emb_cap.create(text, use_model)

        return await provider_router.call_with_failover(
            candidates, _call
        )

    async def tts(
        self,
        text: str,
        voice: str | None = None,
        model: str | None = None,
        provider_name: str | None = None,
    ) -> bytes:
        """语音合成

        参数:
            text: 合成文本
            voice: 音色
            model: TTS模型名
            provider_name: 指定provider

        返回:
            bytes: 音频数据

        异常:
            ValueError: provider不支持TTS
        """
        use_model = model or get_config("TTS_MODEL", "tts-1")
        use_voice = voice or get_config("TTS_VOICE", "alloy")
        candidates = self._build_candidates(
            Capability.AUDIO,
            provider_name or get_config("TTS_PROVIDER", None),
        )

        async def _call(name: str) -> bytes:
            provider = llm_manager.get_provider(name)
            if not provider:
                raise ValueError(f"provider '{name}' 不存在")
            audio_cap = provider.get_capability(Capability.AUDIO)
            if not audio_cap:
                raise ValueError(
                    f"provider '{name}' 不支持语音能力"
                )
            return await audio_cap.text_to_speech(
                text, use_model, use_voice
            )

        return await provider_router.call_with_failover(
            candidates, _call
        )

    async def image_generate(
        self,
        prompt: str,
        model: str | None = None,
        size: str = "1024x1024",
        n: int = 1,
        provider_name: str | None = None,
    ) -> list[str]:
        """图片生成

        参数:
            prompt: 生成提示
            model: 图片模型名
            size: 图片尺寸
            n: 生成数量
            provider_name: 指定provider

        返回:
            list[str]: 图片URL列表

        异常:
            ValueError: provider不支持图片生成
        """
        use_model = model or get_config("IMAGE_MODEL", "dall-e-3")
        candidates = self._build_candidates(
            Capability.IMAGE,
            provider_name or get_config("IMAGE_PROVIDER", None),
        )

        async def _call(name: str) -> list[str]:
            provider = llm_manager.get_provider(name)
            if not provider:
                raise ValueError(f"provider '{name}' 不存在")
            image_cap = provider.get_capability(Capability.IMAGE)
            if not image_cap:
                raise ValueError(
                    f"provider '{name}' 不支持图片生成"
                )
            return await image_cap.generate(
                prompt, use_model, size, n
            )

        return await provider_router.call_with_failover(
            candidates, _call
        )

    async def web_search(
        self,
        query: str,
        count: int = 5,
        provider_name: str | None = None,
    ) -> list[dict[str, str]]:
        """联网搜索

        优先使用普通百度搜索（web_search模式），
        通过统一 Provider 的 WebSearchCapability 调用。

        参数:
            query: 搜索查询
            count: 结果数量
            provider_name: 指定provider

        返回:
            list[dict]: 搜索结果列表，每项含 title/url/snippet
        """
        candidates = self._build_candidates(
            Capability.WEB_SEARCH, provider_name
        )
        if not candidates:
            logger.warning(
                "未配置可用的 web_search provider，跳过网络搜索",
                command="AI",
            )
            return []

        async def _call(name: str) -> list[dict[str, str]]:
            provider = llm_manager.get_provider(name)
            if not provider:
                raise ValueError(f"provider '{name}' 不存在")
            search_cap = provider.get_capability(Capability.WEB_SEARCH)
            if not search_cap:
                raise ValueError(
                    f"provider '{name}' 不支持搜索能力"
                )
            response = await search_cap.search(
                query,
                count=count,
                options={"baidu_mode": "web_search"},
            )
            results: list[dict[str, str]] = []
            for item in response.web_pages:
                results.append(
                    {
                        "title": item.title,
                        "url": item.url,
                        "snippet": item.snippet,
                        "summary": item.summary or "",
                    }
                )
            if response.summary_text and not results:
                results.append(
                    {
                        "title": "搜索总结",
                        "url": "",
                        "snippet": response.summary_text,
                        "summary": "",
                    }
                )
            return results

        return await provider_router.call_with_failover(
            candidates, _call
        )


llm_helper = LLMHelper()
"""LLM助手单例"""
