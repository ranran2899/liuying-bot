"""LLM Token 消耗持久化统计模型"""
import time
from typing import ClassVar

from sqlalchemy import BigInteger, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class TokenUsage(Model):
    """LLM Token 消耗持久化统计模型

    按日期 + 供应商 + 模型三维聚合，每次 LLM 调用后累加写入，
    重启后数据不丢失。
    """

    __tablename__ = "llm_token_usage"
    __table_args__: ClassVar[dict] = {
        "comment": "LLM Token 消耗持久化统计表"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    date: Mapped[str] = mapped_column(
        String(10), nullable=False, index=True, comment="日期 (YYYY-MM-DD)"
    )
    """统计日期"""
    provider: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="供应商名称"
    )
    """供应商名称"""
    model: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="模型名称"
    )
    """模型名称"""
    prompt_tokens: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False, comment="提示 token 累计"
    )
    """提示 token 累计"""
    completion_tokens: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False, comment="补全 token 累计"
    )
    """补全 token 累计"""
    total_tokens: Mapped[int] = mapped_column(
        BigInteger, default=0, nullable=False, comment="总 token 累计"
    )
    """总 token 累计"""
    request_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="请求次数"
    )
    """请求次数"""
    updated_at: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="最后更新时间戳"
    )
    """最后更新时间戳"""

    @classmethod
    async def accumulate(
        cls,
        provider: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
    ) -> None:
        """累加一次 Token 消耗到持久化统计

        使用 QueryWrapper.update 进行数据库原子累加
        (col = col + val)，避免读-改-写竞态导致的数据丢失。
        记录不存在时通过 get_or_create 创建，并发创建冲突
        时重试原子累加。

        参数:
            provider: 供应商名称
            model: 模型名称
            prompt_tokens: 提示 token 数
            completion_tokens: 补全 token 数
            total_tokens: 总 token 数
        """
        if total_tokens <= 0 and prompt_tokens <= 0 and completion_tokens <= 0:
            return

        today = time.strftime("%Y-%m-%d")
        now = int(time.time())

        # 原子累加已有记录（col = col + val，单条 SQL 无竞态）
        rowcount = await cls.filter(
            date=today, provider=provider, model=model
        ).update(
            prompt_tokens=cls.prompt_tokens + prompt_tokens,
            completion_tokens=cls.completion_tokens + completion_tokens,
            total_tokens=cls.total_tokens + total_tokens,
            request_count=cls.request_count + 1,
            updated_at=now,
        )
        if rowcount > 0:
            return

        # 记录不存在，创建初始记录
        _, created = await cls.get_or_create(
            date=today,
            provider=provider,
            model=model,
            defaults={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "request_count": 1,
                "updated_at": now,
            },
        )
        if not created:
            # 并发创建冲突，记录已被其他请求创建，原子累加
            await cls.filter(
                date=today, provider=provider, model=model
            ).update(
                prompt_tokens=cls.prompt_tokens + prompt_tokens,
                completion_tokens=cls.completion_tokens + completion_tokens,
                total_tokens=cls.total_tokens + total_tokens,
                request_count=cls.request_count + 1,
                updated_at=now,
            )

    @classmethod
    async def get_daily_summary(
        cls, date: str | None = None
    ) -> dict[str, dict[str, int]]:
        """获取指定日期按模型维度的汇总

        参数:
            date: 日期字符串 (YYYY-MM-DD)，默认今天

        返回:
            "供应商/模型" 到统计字典的映射
        """
        target = date or time.strftime("%Y-%m-%d")
        rows = await (
            cls.filter(date=target)
            .only("provider", "model")
            .annotate(
                prompt_tokens=func.sum(cls.prompt_tokens),
                completion_tokens=func.sum(cls.completion_tokens),
                total_tokens=func.sum(cls.total_tokens),
                request_count=func.sum(cls.request_count),
            )
            .group_by(cls.provider, cls.model)
            .all()
        )
        return {
            f"{r.provider}/{r.model}": {
                "prompt_tokens": int(r.prompt_tokens or 0),
                "completion_tokens": int(r.completion_tokens or 0),
                "total_tokens": int(r.total_tokens or 0),
                "request_count": int(r.request_count or 0),
            }
            for r in rows
        }

    @classmethod
    async def get_daily_provider_summary(
        cls, date: str | None = None
    ) -> dict[str, dict[str, int]]:
        """获取指定日期按供应商维度的汇总

        参数:
            date: 日期字符串 (YYYY-MM-DD)，默认今天

        返回:
            供应商名到统计字典的映射
        """
        target = date or time.strftime("%Y-%m-%d")
        rows = await (
            cls.filter(date=target)
            .only("provider")
            .annotate(
                prompt_tokens=func.sum(cls.prompt_tokens),
                completion_tokens=func.sum(cls.completion_tokens),
                total_tokens=func.sum(cls.total_tokens),
                request_count=func.sum(cls.request_count),
            )
            .group_by(cls.provider)
            .all()
        )
        return {
            r.provider: {
                "prompt_tokens": int(r.prompt_tokens or 0),
                "completion_tokens": int(r.completion_tokens or 0),
                "total_tokens": int(r.total_tokens or 0),
                "request_count": int(r.request_count or 0),
            }
            for r in rows
        }

    @classmethod
    async def get_daily_total(
        cls, date: str | None = None
    ) -> dict[str, int]:
        """获取指定日期的全局总计

        参数:
            date: 日期字符串 (YYYY-MM-DD)，默认今天

        返回:
            全局统计字典
        """
        target = date or time.strftime("%Y-%m-%d")
        result = await cls.filter(date=target).aggregate(
            prompt_tokens=func.sum(cls.prompt_tokens),
            completion_tokens=func.sum(cls.completion_tokens),
            total_tokens=func.sum(cls.total_tokens),
            request_count=func.sum(cls.request_count),
        )
        return {
            "prompt_tokens": int(result.get("prompt_tokens") or 0),
            "completion_tokens": int(result.get("completion_tokens") or 0),
            "total_tokens": int(result.get("total_tokens") or 0),
            "request_count": int(result.get("request_count") or 0),
        }

    @classmethod
    async def get_range_summary(
        cls, days: int = 7
    ) -> dict[str, dict[str, int]]:
        """获取最近 N 天的聚合汇总

        参数:
            days: 天数

        返回:
            "供应商/模型" 到统计字典的映射
        """
        cutoff = int(time.time()) - days * 86400
        cutoff_date = time.strftime("%Y-%m-%d", time.localtime(cutoff))
        rows = await (
            cls.filter(date__gte=cutoff_date)
            .only("provider", "model")
            .annotate(
                prompt_tokens=func.sum(cls.prompt_tokens),
                completion_tokens=func.sum(cls.completion_tokens),
                total_tokens=func.sum(cls.total_tokens),
                request_count=func.sum(cls.request_count),
            )
            .group_by(cls.provider, cls.model)
            .all()
        )
        return {
            f"{r.provider}/{r.model}": {
                "prompt_tokens": int(r.prompt_tokens or 0),
                "completion_tokens": int(r.completion_tokens or 0),
                "total_tokens": int(r.total_tokens or 0),
                "request_count": int(r.request_count or 0),
            }
            for r in rows
        }

    @classmethod
    async def get_total_summary(cls) -> dict[str, int]:
        """获取全部时间的总计

        返回:
            全局统计字典
        """
        result = await cls.filter().aggregate(
            prompt_tokens=func.sum(cls.prompt_tokens),
            completion_tokens=func.sum(cls.completion_tokens),
            total_tokens=func.sum(cls.total_tokens),
            request_count=func.sum(cls.request_count),
        )
        return {
            "prompt_tokens": int(result.get("prompt_tokens") or 0),
            "completion_tokens": int(result.get("completion_tokens") or 0),
            "total_tokens": int(result.get("total_tokens") or 0),
            "request_count": int(result.get("request_count") or 0),
        }

    @classmethod
    async def clear_today(cls) -> None:
        """清空今日统计记录"""
        today = time.strftime("%Y-%m-%d")
        await cls.filter(date=today).delete()
