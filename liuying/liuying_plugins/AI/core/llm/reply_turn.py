"""回复轮次追踪

追踪每个用户的对话轮次与质量，为后续策略（如额度控制、
主动行为、记忆巩固）提供数据支撑。基于内存字典实现。
"""

from datetime import datetime

from liuying.utils.log import logger


class ReplyTurnTracker:
    """回复轮次追踪器

    按 user_id 维度记录当前轮次编号、累计轮次、质量统计。
    """

    def __init__(self) -> None:
        """初始化轮次追踪器"""
        self._current: dict[str, int] = {}
        """user_id -> 当前轮次编号"""
        self._stats: dict[str, dict] = {}
        """user_id -> {total_turns, quality_sum, quality_count, last_ts}"""

    def start_turn(self, user_id: str) -> int:
        """开始一轮新对话

        参数:
            user_id: 用户ID

        返回:
            int: 本轮轮次编号
        """
        turn = self._current.get(user_id, 0) + 1
        self._current[user_id] = turn
        stat = self._stats.setdefault(
            user_id,
            {
                "total_turns": 0,
                "quality_sum": 0.0,
                "quality_count": 0,
                "last_ts": "",
            },
        )
        stat["total_turns"] += 1
        stat["last_ts"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        logger.debug(
            f"开始轮次: user={user_id} turn={turn}",
            command="AI",
        )
        return turn

    def end_turn(
        self, user_id: str, quality: float
    ) -> None:
        """结束一轮对话并记录质量

        参数:
            user_id: 用户ID
            quality: 质量评分（0.0~1.0）
        """
        stat = self._stats.get(user_id)
        if not stat:
            stat = {
                "total_turns": 0,
                "quality_sum": 0.0,
                "quality_count": 0,
                "last_ts": "",
            }
            self._stats[user_id] = stat
        clamped = max(0.0, min(1.0, float(quality)))
        stat["quality_sum"] += clamped
        stat["quality_count"] += 1
        stat["last_ts"] = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self._current.pop(user_id, None)
        logger.debug(
            f"结束轮次: user={user_id} quality={clamped:.2f}",
            command="AI",
        )

    def get_stats(self, user_id: str) -> dict:
        """获取用户轮次统计

        参数:
            user_id: 用户ID

        返回:
            dict: 含 total_turns/avg_quality/last_ts/current_turn
        """
        stat = self._stats.get(user_id, {})
        quality_count = stat.get("quality_count", 0)
        quality_sum = stat.get("quality_sum", 0.0)
        avg = (
            quality_sum / quality_count
            if quality_count > 0
            else 0.0
        )
        return {
            "total_turns": stat.get("total_turns", 0),
            "avg_quality": round(avg, 3),
            "quality_count": quality_count,
            "last_ts": stat.get("last_ts", ""),
            "current_turn": self._current.get(user_id, 0),
        }

    def reset(self, user_id: str | None = None) -> None:
        """重置轮次统计

        参数:
            user_id: 指定用户时只重置该用户，None重置全部
        """
        if user_id is None:
            self._current.clear()
            self._stats.clear()
        else:
            self._current.pop(user_id, None)
            self._stats.pop(user_id, None)


reply_turn_tracker = ReplyTurnTracker()
"""回复轮次追踪器单例"""
