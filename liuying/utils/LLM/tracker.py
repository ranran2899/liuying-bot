"""LLM Token 消耗追踪器 - 持久化统计"""
from liuying.models._llm import TokenUsage


class TokenUsageTracker:
    """LLM Token 消耗追踪器

    按供应商与模型维度统计对话类请求消耗的 token，
    数据直接写入持久化存储，重启后不丢失。
    """

    async def record(
        self,
        provider: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
    ) -> None:
        """记录一次 Token 消耗，直接写入持久化

        参数:
            provider: 供应商名称
            model: 模型名称
            prompt_tokens: 提示 token 数
            completion_tokens: 补全 token 数
            total_tokens: 总 token 数
        """
        if total_tokens <= 0 and prompt_tokens <= 0 and completion_tokens <= 0:
            return

        try:
            await TokenUsage.accumulate(
                provider=provider,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )
        except Exception:
            # 持久化失败不应影响正常调用
            pass

    async def get_model_summary(self) -> dict[str, dict[str, int]]:
        """按模型获取今日统计摘要

        返回:
            模型名到统计字典的映射
        """
        try:
            return await TokenUsage.get_daily_summary()
        except Exception:
            return {}

    async def get_provider_summary(self) -> dict[str, dict[str, int]]:
        """按供应商获取今日统计摘要

        返回:
            供应商名到统计字典的映射
        """
        try:
            return await TokenUsage.get_daily_provider_summary()
        except Exception:
            return {}

    async def get_total(self) -> dict[str, int]:
        """获取今日全局总计

        返回:
            全局统计字典
        """
        try:
            return await TokenUsage.get_daily_total()
        except Exception:
            return {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "request_count": 0,
            }

    async def reset(self) -> None:
        """重置所有统计 (保留历史，仅清空今日)"""
        try:
            await TokenUsage.clear_today()
        except Exception:
            pass


token_tracker = TokenUsageTracker()


__all__ = ["TokenUsageTracker", "token_tracker"]
