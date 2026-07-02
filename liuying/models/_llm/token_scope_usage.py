"""LLM 作用域 Token 消耗统计模型 - 按用户/群/频道/Bot维度"""
import time
from typing import ClassVar

from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model

_EMPTY_SUMMARY: dict[str, int] = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "request_count": 0,
}
# _UPDATE_FIELDS = [
#     "prompt_tokens",
#     "completion_tokens",
#     "total_tokens",
#     "request_count",
#     "updated_at",
# ]


class ScopeTokenUsage(Model):
    """LLM 作用域 Token 消耗统计模型

    按 user_id + group_id + channel_id + bot_id + window(1/7/30天)
    聚合存储 Token 消耗，支持按维度查询不同时间跨度的统计。
    """

    __tablename__ = "llm_token_scope_usage"
    __table_args__: ClassVar[dict] = {
        "comment": "LLM 作用域 Token 消耗统计表"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    """自增id"""
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
        default="", comment="用户id (空串表示无用户维度)"
    )
    """用户id"""
    group_id: Mapped[str | None] = mapped_column(
        String(255), default="", comment="群id"
    )
    """群id"""
    channel_id: Mapped[str | None] = mapped_column(
        String(255), default="", comment="频道id"
    )
    """频道id"""
    bot_id: Mapped[str | None] = mapped_column(
        String(255), default="", comment="Bot id"
    )
    """Bot id"""
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
    platform: Mapped[str | None] = mapped_column(
        String(255), default="", comment="平台")
    """平台"""
