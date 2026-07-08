"""调用统计路由

提供基于 Statistics 表的插件调用统计聚合查询。
"""

from collections import Counter
from typing import Any

from fastapi import APIRouter

from liuying.models.statistics import Statistics

__all__ = ["build_stats_router"]


def build_stats_router() -> APIRouter:
    """构建调用统计路由"""
    router = APIRouter(prefix="/stats", tags=["WebUI-调用统计"])

    @router.get("")
    async def stats_summary(limit: int = 100) -> dict[str, Any]:
        """获取调用统计摘要

        参数:
            limit: 最近记录条数上限（默认100，最大500）
        """
        limit = max(1, min(int(limit), 500))
        total = await Statistics.filter().count()
        recent_rows = (
            await Statistics.filter()
            .order_by("-create_time")
            .limit(limit)
            .all()
        )
        by_plugin: Counter[str] = Counter()
        by_group: Counter[str] = Counter()
        by_user: Counter[str] = Counter()
        recent: list[dict[str, Any]] = []
        for row in recent_rows:
            if row.plugin_name:
                by_plugin[row.plugin_name] += 1
            if row.group_id:
                by_group[row.group_id] += 1
            if row.user_id:
                by_user[row.user_id] += 1
            create_time = ""
            if row.create_time:
                create_time = row.create_time.isoformat()
            recent.append(
                {
                    "user_id": row.user_id or "",
                    "group_id": row.group_id or "",
                    "plugin_name": row.plugin_name or "",
                    "bot_id": row.bot_id or "",
                    "create_time": create_time,
                }
            )
        return {
            "total": total,
            "by_plugin": dict(by_plugin.most_common(20)),
            "by_group": dict(by_group.most_common(20)),
            "by_user": dict(by_user.most_common(20)),
            "recent": recent,
            "recent_count": len(recent),
        }

    @router.get("/plugin/{plugin_name}")
    async def stats_by_plugin(plugin_name: str) -> dict[str, Any]:
        """获取指定插件的调用统计"""
        rows = await Statistics.filter(plugin_name=plugin_name).all()
        by_group: Counter[str] = Counter()
        by_user: Counter[str] = Counter()
        for row in rows:
            if row.group_id:
                by_group[row.group_id] += 1
            if row.user_id:
                by_user[row.user_id] += 1
        return {
            "plugin_name": plugin_name,
            "total": len(rows),
            "by_group": dict(by_group.most_common(50)),
            "by_user": dict(by_user.most_common(50)),
        }

    return router
