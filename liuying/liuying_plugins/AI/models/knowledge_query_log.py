"""知识库查询日志数据模型

定义 KnowledgeQueryLog，记录AI对插件知识库的查询历史，
用于热点统计与召回优化。
"""

from collections import Counter
from datetime import datetime, timedelta
import json
from typing import Any, ClassVar

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class KnowledgeQueryLog(Model):
    """知识库查询日志模型

    记录AI对插件知识库的查询历史，用于热点统计与召回优化。
    """

    __tablename__ = "ai_knowledge_query_log"
    __table_args__: ClassVar[dict] = {
        "comment": "AI知识库查询日志表",
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增ID"
    )
    """自增ID"""

    query_text: Mapped[str] = mapped_column(
        Text, default="", comment="查询文本"
    )
    """查询文本"""

    matched_plugin: Mapped[str] = mapped_column(
        String(128), default="", index=True, comment="命中插件名"
    )
    """命中插件名"""

    user_id: Mapped[str] = mapped_column(
        String(255), default="", index=True, comment="用户ID"
    )
    """用户ID"""

    group_id: Mapped[str] = mapped_column(
        String(255), default="", comment="群组ID"
    )
    """群组ID"""

    query_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, index=True, comment="查询时间"
    )
    """查询时间"""

    extra: Mapped[str] = mapped_column(
        Text, default="{}", comment="额外信息JSON"
    )
    """额外信息JSON"""

    cache_type = "AI_KNOWLEDGE_QUERY_LOG"
    """缓存类型"""

    cache_key_field = "id"
    """缓存键字段"""

    @classmethod
    def _run_script(cls):
        """数据库初始化脚本"""
        return [
            "CREATE INDEX IF NOT EXISTS idx_ai_kqlog_plugin_time "
            "ON ai_knowledge_query_log (matched_plugin, query_time)",
            "CREATE INDEX IF NOT EXISTS idx_ai_kqlog_user_time "
            "ON ai_knowledge_query_log (user_id, query_time)",
        ]

    @classmethod
    async def add_log(
        cls,
        query_text: str,
        matched_plugin: str = "",
        user_id: str = "",
        group_id: str = "",
        extra: dict[str, Any] | None = None,
    ) -> "KnowledgeQueryLog":
        """添加查询日志

        参数:
            query_text: 查询文本
            matched_plugin: 命中插件名
            user_id: 用户ID
            group_id: 群组ID
            extra: 额外信息

        返回:
            KnowledgeQueryLog: 创建的日志
        """
        return await cls.create(
            query_text=query_text[:500],
            matched_plugin=matched_plugin,
            user_id=user_id,
            group_id=group_id,
            extra=json.dumps(extra or {}, ensure_ascii=False),
        )

    @classmethod
    async def get_hot_plugins(
        cls, days: int = 7, limit: int = 20
    ) -> list[dict[str, Any]]:
        """获取热门插件（按命中次数排序）

        使用values_list仅拉取matched_plugin字段，避免完整对象序列化开销。

        参数:
            days: 统计天数
            limit: 返回上限

        返回:
            list[dict]: 热门插件列表（含plugin/count）
        """
        since = datetime.now() - timedelta(days=days)
        plugins = await cls.filter(
            query_time__gte=since
        ).values_list("matched_plugin", flat=True)
        counter = Counter(p for p in plugins if p)
        return [
            {"plugin": p, "count": c}
            for p, c in counter.most_common(limit)
        ]
