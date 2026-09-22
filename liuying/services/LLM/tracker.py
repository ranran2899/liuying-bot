"""LLM Token 消耗追踪器 - 持久化统计"""
from collections.abc import Callable

from liuying.models._llm import TokenUsage
from liuying.utils.log import logger

TokenRecordListener = Callable[
    [str, str, int, int, int], None
]
"""Token 记录监听回调签名：
(provider, model, prompt_tokens, completion_tokens, total_tokens)
-> None，同步调用，异常由追踪器内部吞掉不影响记账主流程"""


class TokenUsageTracker:
    """LLM Token 消耗追踪器

    按供应商与模型维度统计对话类请求消耗的 token，
    数据直接写入持久化存储，重启后不丢失。
    提供 add_listener 官方扩展点，供插件（如 AI 会话级扣费）
    在不猴补丁的前提下旁路观察每次消耗。
    """

    def __init__(self) -> None:
        """初始化追踪器"""
        self._listeners: list[TokenRecordListener] = []

    def add_listener(self, listener: TokenRecordListener) -> None:
        """注册消耗记录监听回调

        重复注册同一回调时自动去重。

        参数:
            listener: 同步回调，参数为
                (provider, model, prompt_tokens,
                 completion_tokens, total_tokens)
        """
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: TokenRecordListener) -> bool:
        """移除已注册的监听回调

        参数:
            listener: 待移除的回调

        返回:
            bool: 是否移除成功
        """
        try:
            self._listeners.remove(listener)
            return True
        except ValueError:
            return False

    async def record(
        self,
        provider: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
    ) -> None:
        """记录一次 Token 消耗，直接写入持久化

        统计写入是 LLM 调用的副作用，失败时仅记录日志，
        不影响 LLM 调用的正常返回；监听回调异常同样吞掉。

        参数:
            provider: 供应商名称
            model: 模型名称
            prompt_tokens: 提示 token 数
            completion_tokens: 补全 token 数
            total_tokens: 总 token 数
        """
        if total_tokens <= 0 and prompt_tokens <= 0 and completion_tokens <= 0:
            return

        for listener in self._listeners:
            try:
                listener(
                    provider,
                    model,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                )
            except Exception as e:
                logger.warning(
                    f"Token 监听回调执行失败（不影响记账）: {e}",
                    command="LLM",
                    e=e,
                )

        try:
            await TokenUsage.accumulate(
                provider=provider,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )
        except Exception as e:
            # 持久化失败不应影响 LLM 调用主流程
            logger.warning(
                f"Token 统计写入失败（不影响调用）: {e}",
                command="LLM",
                e=e,
            )

    async def get_model_summary(self) -> dict[str, dict[str, int]]:
        """按模型获取今日统计摘要

        返回:
            模型名到统计字典的映射
        """
        return await TokenUsage.get_daily_summary()

    async def get_provider_summary(self) -> dict[str, dict[str, int]]:
        """按供应商获取今日统计摘要

        返回:
            供应商名到统计字典的映射
        """
        return await TokenUsage.get_daily_provider_summary()

    async def get_total(self) -> dict[str, int]:
        """获取今日全局总计

        返回:
            全局统计字典
        """
        return await TokenUsage.get_daily_total()

    async def reset(self) -> None:
        """重置所有统计 (保留历史，仅清空今日)"""
        await TokenUsage.clear_today()


token_tracker = TokenUsageTracker()


__all__ = ["TokenUsageTracker", "token_tracker"]
