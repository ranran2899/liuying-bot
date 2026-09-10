"""Token账本记录数据模型

定义 TokenLedgerRecord，按 group_id/user_id/purpose/model 维度
记录Token消耗。
"""

from datetime import datetime, timedelta
import json
from typing import Any, ClassVar

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model
from liuying.utils.log import logger


class TokenLedgerRecord(Model):
    """Token账本记录模型

    按 group_id/user_id/purpose/model 维度记录Token消耗。
    """

    __tablename__ = "ai_token_ledger"
    __table_args__: ClassVar[dict] = {
        "comment": "AI Token消耗账本表",
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增ID"
    )
    """自增ID"""

    group_id: Mapped[str] = mapped_column(
        String(255), default="", index=True, comment="群组ID"
    )
    """群组ID（空串表示全局）"""

    user_id: Mapped[str] = mapped_column(
        String(255), default="", index=True, comment="用户ID"
    )
    """用户ID（空串表示全局）"""

    purpose: Mapped[str] = mapped_column(
        String(64), default="chat", index=True, comment="调用用途"
    )
    """调用用途：chat/embedding/tts/image/agent/summary"""

    provider: Mapped[str] = mapped_column(
        String(64), default="", comment="供应商名"
    )
    """供应商名"""

    model: Mapped[str] = mapped_column(
        String(128), default="", index=True, comment="模型名"
    )
    """模型名"""

    prompt_tokens: Mapped[int] = mapped_column(
        Integer, default=0, comment="提示Token数"
    )
    """提示Token数"""

    completion_tokens: Mapped[int] = mapped_column(
        Integer, default=0, comment="补全Token数"
    )
    """补全Token数"""

    total_tokens: Mapped[int] = mapped_column(
        Integer, default=0, comment="总Token数"
    )
    """总Token数"""

    cost_score: Mapped[float] = mapped_column(
        Float, default=0.0, comment="成本评分（按模型权重计算）"
    )
    """成本评分（按模型权重计算）"""

    extra: Mapped[str] = mapped_column(
        Text, default="{}", comment="额外信息JSON"
    )
    """额外信息JSON"""

    create_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, index=True, comment="记录时间"
    )
    """记录时间"""

    @classmethod
    def _run_script(cls):
        """数据库初始化脚本"""
        return [
            "CREATE INDEX IF NOT EXISTS idx_ai_token_ledger_group_time "
            "ON ai_token_ledger (group_id, create_time)",
            "CREATE INDEX IF NOT EXISTS idx_ai_token_ledger_user_time "
            "ON ai_token_ledger (user_id, create_time)",
        ]

    @classmethod
    async def add_record(
        cls,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        group_id: str = "",
        user_id: str = "",
        purpose: str = "chat",
        cost_score: float = 0.0,
        extra: dict[str, Any] | None = None,
    ) -> "TokenLedgerRecord":
        """添加Token消耗记录

        参数:
            provider: 供应商名
            model: 模型名
            prompt_tokens: 提示Token数
            completion_tokens: 补全Token数
            total_tokens: 总Token数
            group_id: 群组ID
            user_id: 用户ID
            purpose: 调用用途
            cost_score: 成本评分
            extra: 额外信息

        返回:
            TokenLedgerRecord: 创建的记录
        """
        return await cls.create(
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            group_id=group_id,
            user_id=user_id,
            purpose=purpose,
            cost_score=cost_score,
            extra=json.dumps(extra or {}, ensure_ascii=False),
        )

    @classmethod
    async def get_summary(
        cls,
        group_id: str = "",
        user_id: str = "",
        purpose: str = "",
        hours: int = 24,
    ) -> dict[str, Any]:
        """获取Token消耗摘要

        使用SQL聚合查询避免全量加载记录到内存。
        单次多列 GROUP BY (purpose, model) 扫描后在Python侧
        汇总出 total/by_purpose/by_model 三份结果，避免同条件
        下三条SQL重复扫描。

        参数:
            group_id: 群组ID（空串表示全部）
            user_id: 用户ID（空串表示全部）
            purpose: 调用用途（空串表示全部）
            hours: 统计时间窗口（小时）

        返回:
            dict: 摘要字典，含 total/by_purpose/by_model
        """
        cutoff = datetime.now() - timedelta(hours=hours)
        conditions = ["create_time > :cutoff"]
        params: dict[str, Any] = {"cutoff": cutoff}
        if group_id:
            conditions.append("group_id = :group_id")
            params["group_id"] = group_id
        if user_id:
            conditions.append("user_id = :user_id")
            params["user_id"] = user_id
        if purpose:
            conditions.append("purpose = :purpose")
            params["purpose"] = purpose
        where_clause = " AND ".join(conditions)

        summary_sql = (
            "SELECT purpose, model, "
            "COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens, "
            "COALESCE(SUM(completion_tokens), 0) AS completion_tokens, "
            "COALESCE(SUM(total_tokens), 0) AS total_tokens, "
            "COUNT(id) AS request_count "
            f"FROM ai_token_ledger WHERE {where_clause} "
            "GROUP BY purpose, model"
        )
        result = await cls.filter().raw(summary_sql, params)
        rows = result.fetchall()

        if not rows:
            return {
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "request_count": 0,
                "by_purpose": {},
                "by_model": {},
            }

        def _bucket(
            target: dict[str, dict[str, int]], key: str
        ) -> dict[str, int]:
            """取分组累计桶，不存在时初始化零值"""
            if key not in target:
                target[key] = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "request_count": 0,
                }
            return target[key]

        total = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "request_count": 0,
        }
        by_purpose: dict[str, dict[str, int]] = {}
        by_model: dict[str, dict[str, int]] = {}

        for row in rows:
            row_vals = {
                "prompt_tokens": int(row.prompt_tokens or 0),
                "completion_tokens": int(row.completion_tokens or 0),
                "total_tokens": int(row.total_tokens or 0),
                "request_count": int(row.request_count or 0),
            }
            purpose_bucket = _bucket(by_purpose, row.purpose)
            model_bucket = _bucket(by_model, row.model or "unknown")
            for name, value in row_vals.items():
                total[name] += value
                purpose_bucket[name] += value
                model_bucket[name] += value

        return {
            "total_tokens": total["total_tokens"],
            "prompt_tokens": total["prompt_tokens"],
            "completion_tokens": total["completion_tokens"],
            "request_count": total["request_count"],
            "by_purpose": by_purpose,
            "by_model": by_model,
        }

    @classmethod
    async def prune_old_records(cls, days: int = 90) -> int:
        """清理过期记录（批量DELETE）

        参数:
            days: 保留天数

        返回:
            int: 删除的记录数
        """
        cutoff = datetime.now() - timedelta(days=days)
        count = await cls.filter(create_time__lt=cutoff).delete()
        if count > 0:
            logger.info(
                f"清理过期Token记录{count}条",
                command="AI",
            )
        return count
