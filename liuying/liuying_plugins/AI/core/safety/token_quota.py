"""用户对话 Token 额度服务

直接对接 liuying.models._llm.token_quota.UserToken，提供：
- 对话前的额度可用性检查（不足时阻止对话继续）
- 对话后的实际 token 消耗扣费（委托 UserToken.consume，
  不足时自动尝试铜币抵扣）
- 余额不足提醒的冷却（CD）控制，避免同一用户被反复提示刷屏

额度设置（set_token）由流萤其他插件实现，AI 插件不自主实现。
本服务仅负责用户级对话额度的检查与扣费，token 实际用量由
pipeline.processor 在对话周期内通过 token_ledger 的会话级
累加器（start_conversation_tracking / stop_conversation_tracking）
统计得到，确保扣费额度准确反映本轮对话所有 LLM 调用的实际消耗。
"""

from dataclasses import dataclass
import time
from typing import Any

from liuying.models._llm.token_quota import UserToken
from liuying.utils.log import logger

from ...config import get_config

__all__ = [
    "QuotaCheckResult",
    "TokenQuotaService",
    "token_quota_service",
]


@dataclass(slots=True)
class QuotaCheckResult:
    """额度检查结果

    Attributes:
        allowed: 是否允许继续对话
        remaining: 当前剩余 token 数（-1 表示未知/未启用）
        reason: 不允许时的原因（用于日志）
        need_remind: 是否需要发送余额不足提醒（满足 CD 条件时为 True）
    """

    allowed: bool
    remaining: int = -1
    reason: str = ""
    need_remind: bool = False


class TokenQuotaService:
    """用户对话 Token 额度服务

    提供对话前的额度可用性检查与对话后的实际消耗扣费，
    并通过内存字典维护余额不足提醒的 CD，避免重复提醒刷屏。
    """

    _DEFAULT_REMINDER_CD: int = 300
    """默认提醒冷却（秒）"""

    _DEFAULT_MIN_THRESHOLD: int = 1
    """默认最低可用阈值（剩余低于此值视为不足）"""

    def __init__(self) -> None:
        """初始化额度服务"""
        self._reminder_ts: dict[str, float] = {}
        """用户上次发送余额不足提醒的时间戳"""

    def _is_enabled(self) -> bool:
        """额度服务是否启用

        返回:
            bool: 是否启用
        """
        return bool(get_config("TOKEN_QUOTA_ENABLED", True))

    def _get_reminder_cd(self) -> int:
        """获取提醒 CD（秒）

        返回:
            int: 提醒冷却秒数
        """
        try:
            cd = int(get_config("TOKEN_QUOTA_REMINDER_CD", self._DEFAULT_REMINDER_CD))
            return max(0, cd)
        except (TypeError, ValueError):
            return self._DEFAULT_REMINDER_CD

    def _get_min_threshold(self) -> int:
        """获取最低可用阈值

        返回:
            int: 最低可用 token 数
        """
        try:
            threshold = int(
                get_config("TOKEN_QUOTA_MIN_THRESHOLD", self._DEFAULT_MIN_THRESHOLD)
            )
            return max(1, threshold)
        except (TypeError, ValueError):
            return self._DEFAULT_MIN_THRESHOLD

    def _should_remind(self, user_id: str) -> bool:
        """检查是否应发送余额不足提醒（满足 CD 条件）

        参数:
            user_id: 用户ID

        返回:
            bool: 是否应提醒
        """
        if not user_id:
            return False
        now = time.time()
        cd = self._get_reminder_cd()
        last = self._reminder_ts.get(user_id, 0.0)
        if cd <= 0:
            return True
        return (now - last) >= cd

    def _record_reminder(self, user_id: str) -> None:
        """记录本次提醒时间戳

        参数:
            user_id: 用户ID
        """
        if user_id:
            self._reminder_ts[user_id] = time.time()

    def clear_reminder(self, user_id: str) -> None:
        """清除用户提醒记录（用户补足额度后调用）

        参数:
            user_id: 用户ID
        """
        self._reminder_ts.pop(user_id, None)

    async def check_before_conversation(
        self, user_id: str
    ) -> QuotaCheckResult:
        """对话前的额度可用性检查

        通过 UserToken.get_available 获取可用额度（已包含铜币兜底），
        不足时按 CD 控制是否发送提醒。

        参数:
            user_id: 用户ID

        返回:
            QuotaCheckResult: 检查结果
        """
        if not self._is_enabled() or not user_id:
            return QuotaCheckResult(allowed=True, remaining=-1)

        try:
            available = await UserToken.get_available(user_id)
        except Exception as e:
            logger.debug(
                f"查询用户 token 额度失败，放行: {e}",
                command="AI",
                e=e,
            )
            return QuotaCheckResult(allowed=True, remaining=-1)

        threshold = self._get_min_threshold()
        if available >= threshold:
            return QuotaCheckResult(
                allowed=True, remaining=available
            )

        need_remind = self._should_remind(user_id)
        if need_remind:
            self._record_reminder(user_id)
        return QuotaCheckResult(
            allowed=False,
            remaining=available,
            reason=(
                f"用户 token 额度不足: "
                f"available={available} threshold={threshold}"
            ),
            need_remind=need_remind,
        )

    async def consume_after_conversation(
        self,
        user_id: str,
        usage: dict[str, int],
    ) -> dict[str, Any]:
        """对话后按实际消耗扣费

        委托 UserToken.consume 扣除 token；UserToken 不足时
        自动以铜币抵扣（1 铜币 = 1 token），铜币也不足时
        记录日志但不抛异常（避免影响已完成的回复发送）。

        参数:
            user_id: 用户ID
            usage: 会话级累计用量（含 total_tokens 等字段）

        返回:
            dict: 扣费结果，含 consumed/ok/error 字段
        """
        if not self._is_enabled() or not user_id:
            return {"consumed": 0, "ok": True, "error": ""}
        tokens = int(usage.get("total_tokens", 0) or 0)
        if tokens <= 0:
            return {"consumed": 0, "ok": True, "error": ""}

        try:
            instance = await UserToken.consume(user_id, tokens)
            logger.debug(
                f"用户 {user_id} 消耗 token: {tokens}，"
                f"剩余 {instance.user_token}",
                command="AI",
            )
            # 用户扣费后额度恢复，清除提醒记录
            if instance.user_token > 0:
                self.clear_reminder(user_id)
            return {
                "consumed": tokens,
                "ok": True,
                "error": "",
                "remaining": instance.user_token,
            }
        except Exception as e:
            logger.info(
                f"用户 {user_id} 扣费失败（token 与铜币均不足或其他错误）"
                f": {e}",
                command="AI",
                e=e,
            )
            return {
                "consumed": 0,
                "ok": False,
                "error": str(e),
            }


token_quota_service = TokenQuotaService()
"""用户对话 token 额度服务单例"""
