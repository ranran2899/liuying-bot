"""LLM调用封装

对接 liuying.services.LLM.llm_manager，提供统一的对话/嵌入/TTS/图片调用接口。
通过 provider_router 实现多 provider 自动容错切换。
"""

from collections.abc import AsyncIterator
import time
from typing import Any

from liuying.services.LLM import Capability, llm_manager
from liuying.utils.log import logger

from ...config import get_config
from .ai_routes import ai_cli_router
from .provider_router import provider_router

_CANDIDATES_TTL = 60.0
"""provider候选列表缓存有效期（秒）

provider注册与能力集在运行期不变，冷却切换由
provider_router 在故障转移时处理，候选枚举无需每次重算。
"""

_VALID_EFFORTS = {"max", "high", "low"}
"""思考强度合法值：max（深度推理）/ high（增强推理）/ low（轻度推理）"""


def _build_thinking_options(cap: Any) -> dict[str, Any]:
    """按 provider 家族构建模型原生思考请求参数（原样透传）

    THINKING.enabled 开启时按 THINKING.effort 传思考强度，
    关闭时对智谱链路显式关闭思考（openai 兼容链路不传即无思考）。

    参数:
        cap: provider 的对话能力实例，用于识别 provider 家族

    返回:
        dict[str, Any]: 模型原生思考参数（reasoning_effort / thinking）
    """
    thinking_cfg = get_config("THINKING", {}) or {}
    enabled = bool(thinking_cfg.get("enabled", False))
    is_zhipu = "zhipu" in type(cap).__module__.lower()
    if not enabled:
        return {"thinking": {"type": "disabled"}} if is_zhipu else {}
    raw = str(thinking_cfg.get("effort", "high") or "").strip().lower()
    effort = raw if raw in _VALID_EFFORTS else "high"
    if is_zhipu:
        # 智谱思考仅有开关，强度由模型自行决定
        return {"thinking": {"type": "enabled"}}
    return {"reasoning_effort": effort}


class LLMHelper:
    """LLM调用助手

    封装llm_manager，提供统一的对话/嵌入/TTS/图片生成接口。
    通过provider_router实现多provider自动容错切换。
    """

    def __init__(self) -> None:
        """初始化LLM助手

        初始化provider候选列表缓存，避免每次调用
        全量遍历provider探测能力。
        """
        self._candidates_cache: dict[
            tuple[Capability, str], tuple[float, list[str]]
        ] = {}

    def _get_provider(self, name: str | None = None):
        """获取provider实例

        参数:
            name: provider名称，None时用配置或默认

        返回:
            BaseProvider: provider实例

        异常:
            ValueError: provider未配置或不存在
        """
        provider_name = name or get_config("CHAT_MODEL", {}).get("provider", None)
        if provider_name:
            provider = llm_manager.get_provider(provider_name)
            if provider:
                return provider
            raise ValueError(f"LLM provider '{provider_name}' 未找到")
        provider = llm_manager.get_default_provider()
        if not provider:
            raise ValueError("无可用LLM provider，请检查配置")
        return provider

    @staticmethod
    def _resolve_capability(
        name: str,
        capability: Capability,
        action: str,
    ):
        """获取provider的指定能力实例

        统一处理provider存在性检查与能力检查，
        供 chat/embedding/tts/image/web_search 的 _call 回调复用。

        参数:
            name: provider名
            capability: 能力类型
            action: 能力描述（用于错误信息）

        返回:
            能力实例

        异常:
            ValueError: provider不存在或不支持该能力
        """
        provider = llm_manager.get_provider(name)
        if not provider:
            raise ValueError(f"provider '{name}' 不存在")
        cap = provider.get_capability(capability)
        if not cap:
            raise ValueError(f"provider '{name}' 不支持{action}")
        return cap

    def _build_candidates(
        self,
        capability: Capability,
        preferred: str | None = None,
    ) -> list[str]:
        """构建支持指定能力的provider候选列表

        结果按（能力，首选provider）缓存短TTL，
        避免高频调用时重复遍历全部provider。

        参数:
            capability: 能力类型
            preferred: 优先使用的provider名

        返回:
            list[str]: 候选provider名列表
        """
        cache_key = (capability, preferred or "")
        now = time.monotonic()
        cached = self._candidates_cache.get(cache_key)
        if cached is not None and now - cached[0] < _CANDIDATES_TTL:
            return cached[1]

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

        chat_provider = get_config("CHAT_MODEL", {}).get("provider", None)
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
        self._candidates_cache[cache_key] = (now, names)
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
        根据 THINKING 配置（enabled/effort）向 provider
        传递模型原生思考参数（reasoning_effort / thinking，原样透传）。

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
        chat_cfg = get_config("CHAT_MODEL", {})
        use_model = model or chat_cfg.get("model", None) or ""
        candidates = self._build_candidates(
            Capability.CHAT,
            provider_name or chat_cfg.get("provider", None),
        )

        async def _call(name: str) -> tuple[str, str]:
            chat_cap = LLMHelper._resolve_capability(
                name, Capability.CHAT, "对话能力"
            )
            call_options = {
                **(options or {}),
                **_build_thinking_options(chat_cap),
            }
            return await chat_cap.chat(
                use_model, messages, call_options
            )

        try:
            result = await provider_router.call_with_failover(
                candidates, _call
            )
            logger.debug(
                f"LLM对话调用成功，模型: {use_model}",
                command="AI",
            )
            return result
        except Exception as http_err:
            # HTTP provider全部失败，尝试CLI路由降级。
            # 用户消息经 ai_cli_router 内部强制以 stdin 传递
            # （AiCliRoute.use_stdin 恒为True），不会拼入命令行参数
            cli_result = await ai_cli_router.call(
                prompt="",
                messages=messages,
            )
            if cli_result:
                logger.info(
                    "HTTP provider全部失败，CLI路由降级成功",
                    command="AI",
                )
                return "", cli_result
            raise http_err

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
        stream_cfg = get_config("CHAT_MODEL", {})
        preferred = provider_name or stream_cfg.get("provider", None)
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
        use_model = model or stream_cfg.get("model", None) or ""
        call_options = {
            **(options or {}),
            **_build_thinking_options(chat_cap),
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
        embedding_cfg = get_config("EMBEDDING", {})
        use_model = model or embedding_cfg.get("model", None) or ""
        candidates = self._build_candidates(
            Capability.EMBEDDING,
            provider_name or embedding_cfg.get("provider", None),
        )

        async def _call(name: str) -> list[float]:
            emb_cap = LLMHelper._resolve_capability(
                name, Capability.EMBEDDING, "嵌入能力"
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
        tts_cfg = get_config("TTS", {})
        use_model = model or tts_cfg.get("model", "tts-1")
        use_voice = voice or tts_cfg.get("voice", "alloy")
        candidates = self._build_candidates(
            Capability.AUDIO,
            provider_name or tts_cfg.get("provider", None),
        )

        async def _call(name: str) -> bytes:
            audio_cap = LLMHelper._resolve_capability(
                name, Capability.AUDIO, "语音能力"
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
        image_cfg = get_config("IMAGE", {})
        use_model = model or image_cfg.get("model", "dall-e-3")
        candidates = self._build_candidates(
            Capability.IMAGE,
            provider_name or image_cfg.get("provider", None),
        )

        async def _call(name: str) -> list[str]:
            image_cap = LLMHelper._resolve_capability(
                name, Capability.IMAGE, "图片生成"
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
            search_cap = LLMHelper._resolve_capability(
                name, Capability.WEB_SEARCH, "搜索能力"
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
