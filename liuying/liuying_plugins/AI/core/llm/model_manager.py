"""LLM模型管理

整合轻量模型对话、严格主模型模式、Provider动态优先级、
月度额度记账、提示词加载、提示词钩子、回复风格策略、
回复文本策略等增强能力。
"""

from collections.abc import Callable
from datetime import datetime
import re
import threading
import time
from typing import Any

from liuying.utils.log import logger

from ...config import get_config
from .helper import llm_helper


class ModelManager:
    """LLM模型管理器

    整合模型选择、额度控制、提示词与风格处理等增强功能。
    """

    def __init__(self) -> None:
        """初始化模型管理器"""
        self._provider_stats: dict[str, dict[str, float]] = {}
        """provider -> {latency, success_rate, calls, failures}"""
        self._stats_lock = threading.RLock()
        self._monthly_tokens: dict[str, int] = {}
        """年月 -> token用量"""
        self._prompt_cache: dict[str, str] = {}
        """提示词模板缓存"""
        self._hooks: dict[str, list[Callable[[dict], dict]]] = {}
        """事件 -> 钩子处理器列表"""

    async def lite_chat(
        self,
        messages: list[dict[str, str]],
        options: dict[str, Any] | None = None,
    ) -> str:
        """轻量模型对话

        用于intent分类等轻量任务。LITE_MODEL_ENABLED 关闭或未配置
        轻量模型时，回退到主模型。STRICT_MAIN_MODEL 开启时直接用主模型。

        参数:
            messages: 消息列表
            options: 额外调用选项

        返回:
            str: 模型回复文本
        """
        if not get_config("LITE_MODEL_ENABLED", False):
            return await llm_helper.chat_text(messages, options=options)
        if get_config("STRICT_MAIN_MODEL", False):
            return await llm_helper.chat_text(messages, options=options)
        provider_name = get_config("LITE_MODEL_PROVIDER", None)
        model_name = get_config("LITE_MODEL_NAME", None)
        start = time.monotonic()
        try:
            text = await llm_helper.chat_text(
                messages,
                model=model_name,
                options=options,
                provider_name=provider_name,
            )
            self._record_success(
                provider_name or "lite",
                time.monotonic() - start,
            )
            return text
        except Exception as e:
            self._record_failure(provider_name or "lite")
            logger.warning(
                f"轻量模型调用失败，回退主模型: {e}",
                command="AI",
                e=e,
            )
            return await llm_helper.chat_text(messages, options=options)

    def _record_success(
        self, provider: str, latency: float
    ) -> None:
        """记录provider成功调用

        参数:
            provider: provider名
            latency: 本次延迟（秒）
        """
        with self._stats_lock:
            stat = self._provider_stats.setdefault(
                provider,
                {"latency": 0.0, "calls": 0.0, "failures": 0.0},
            )
            alpha = 0.3
            stat["latency"] = (
                stat["latency"] * (1 - alpha) + latency * alpha
            )
            stat["calls"] += 1
            stat["success_rate"] = (
                (stat["calls"] - stat["failures"]) / stat["calls"]
            )

    def _record_failure(self, provider: str) -> None:
        """记录provider调用失败

        参数:
            provider: provider名
        """
        with self._stats_lock:
            stat = self._provider_stats.setdefault(
                provider,
                {"latency": 0.0, "calls": 0.0, "failures": 0.0},
            )
            stat["failures"] += 1
            stat["calls"] += 1
            stat["success_rate"] = (
                (stat["calls"] - stat["failures"]) / stat["calls"]
            )

    def get_provider_priority(self) -> list[str]:
        """基于latency/success_rate计算provider动态优先级

        返回:
            list[str]: provider名列表，优先级由高到低
        """
        with self._stats_lock:
            items = list(self._provider_stats.items())
        if not items:
            return []
        scored: list[tuple[str, float]] = []
        for name, stat in items:
            latency = stat.get("latency", 0.0) or 0.001
            success = stat.get("success_rate", 1.0)
            score = success / max(latency, 0.001)
            scored.append((name, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in scored]

    async def check_monthly_quota(self) -> bool:
        """检查月度token额度

        MONTHLY_TOKEN_QUOTA 为 0 视为不限额。

        返回:
            bool: True表示未超限，False表示已超额
        """
        quota = get_config("MONTHLY_TOKEN_QUOTA", 0) or 0
        if quota <= 0:
            return True
        month_key = datetime.now().strftime("%Y-%m")
        used = self._monthly_tokens.get(month_key, 0)
        return used < quota

    def record_tokens(self, tokens: int) -> None:
        """记录token用量

        参数:
            tokens: 本次调用消耗的token数
        """
        if tokens <= 0:
            return
        month_key = datetime.now().strftime("%Y-%m")
        self._monthly_tokens[month_key] = (
            self._monthly_tokens.get(month_key, 0) + tokens
        )
        logger.debug(
            f"记录月度token: {month_key} += {tokens}",
            command="AI",
        )

    def get_monthly_usage(self) -> int:
        """获取本月token用量

        返回:
            int: 本月已用token数
        """
        month_key = datetime.now().strftime("%Y-%m")
        return self._monthly_tokens.get(month_key, 0)

    def load_prompt(self, name: str) -> str:
        """加载提示词模板

        命中缓存后直接返回，否则按内置模板表加载并缓存。
        未知名返回空串。

        参数:
            name: 模板名

        返回:
            str: 提示词模板文本
        """
        if name in self._prompt_cache:
            return self._prompt_cache[name]
        template = _BUILTIN_PROMPTS.get(name, "")
        if template:
            self._prompt_cache[name] = template
        return template

    def register_prompt(self, name: str, template: str) -> None:
        """注册自定义提示词模板

        参数:
            name: 模板名
            template: 模板文本
        """
        self._prompt_cache[name] = template

    def register_hook(
        self, event: str, handler: Callable[[dict], dict]
    ) -> None:
        """注册提示词钩子

        参数:
            event: 事件名（如 before_prompt/after_response）
            handler: 处理器，接收data字典返回更新后的data
        """
        self._hooks.setdefault(event, []).append(handler)

    def apply_hooks(self, event: str, data: dict) -> dict:
        """应用指定事件的全部钩子

        参数:
            event: 事件名
            data: 数据字典

        返回:
            dict: 处理后的数据字典
        """
        handlers = self._hooks.get(event, [])
        result = data
        for handler in handlers:
            try:
                result = handler(result)
            except Exception as e:
                logger.warning(
                    f"钩子执行失败 event={event}: {e}",
                    command="AI",
                    e=e,
                )
        return result

    def apply_style(self, text: str, style: str) -> str:
        """应用回复风格策略

        参数:
            text: 原始文本
            style: 风格名（concise/casual/formal等）

        返回:
            str: 处理后的文本
        """
        if not text or not style:
            return text
        handler = _STYLE_STRATEGIES.get(style)
        if not handler:
            return text
        try:
            return handler(text)
        except Exception as e:
            logger.warning(
                f"应用风格失败 style={style}: {e}",
                command="AI",
                e=e,
            )
            return text

    def clean_text(self, text: str) -> str:
        """清理回复文本

        移除多余空白、Markdown代码块包裹、首尾空白。

        参数:
            text: 原始文本

        返回:
            str: 清理后的文本
        """
        if not text:
            return ""
        cleaned = text.strip()
        cleaned = _CODE_BLOCK_RE.sub("", cleaned)
        cleaned = _MULTI_BLANK_RE.sub("\n", cleaned)
        return cleaned.strip()


_CODE_BLOCK_RE = re.compile(r"```(?:\w+)?\n?", re.MULTILINE)
"""代码块标记正则"""

_MULTI_BLANK_RE = re.compile(r"\n{3,}", re.MULTILINE)
"""多余空行正则"""

_BUILTIN_PROMPTS: dict[str, str] = {
    "intent_classify": (
        "请对用户消息进行意图分类，可选类别：chat/qa/command/offtopic。"
        "只返回类别名，不要其他内容。\n用户消息：{text}"
    ),
    "summary": (
        "请将以下对话摘要成不超过50字的简短总结。\n对话：{history}"
    ),
    "sentiment": (
        "请判断以下文本的情感倾向（正向/中性/负向），"
        "只返回倾向词。\n文本：{text}"
    ),
}
"""内置提示词模板表"""

_STYLE_STRATEGIES: dict[str, Callable[[str], str]] = {
    "concise": lambda t: t[:200] + ("..." if len(t) > 200 else ""),
    "casual": lambda t: t.replace("您好", "你好").replace(
        "请问", "问下"
    ),
    "formal": lambda t: t.replace("你", "您").replace("咋", "如何"),
    "terse": lambda t: "\n".join(
        line for line in t.splitlines() if line.strip()
    )[:150],
}
"""内置回复风格策略表"""


model_manager = ModelManager()
"""LLM模型管理器单例"""
