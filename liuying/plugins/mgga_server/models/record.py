"""单局战绩明细模型。

每局结算写入一条记录，与 :class:`~.account.GameAccount` 通过 ``uid`` 关联。
保留明细便于后续做排行榜细分、胜负趋势与关卡种子复盘。
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class GameRecord(Model):
    """单局战绩明细。"""

    __tablename__ = "mgga_record"
    __table_args__ = ({"comment": "猛鬼公寓联机服 单局战绩表"},)

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增 id"
    )
    """自增 id"""
    uid: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True, comment="玩家 ID"
    )
    """玩家 ID"""
    escaped: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否逃脱"
    )
    """是否逃脱"""
    survive_time: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, comment="存活/逃脱耗时（秒）"
    )
    """存活/逃脱耗时（秒）"""
    seed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="关卡随机种子"
    )
    """关卡随机种子"""
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, index=True, comment="结算时间"
    )
    """结算时间"""

    @classmethod
    def _run_script(cls) -> list[str]:
        """数据库迁移sql脚本。

        """
        return [
           # "DROP TABLE IF EXISTS mgga_record;",
        ]
