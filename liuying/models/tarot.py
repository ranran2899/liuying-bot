"""塔罗牌用户数据模型"""

from datetime import date, datetime
from typing import ClassVar

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class TarotDailyRecord(Model):
    """每日塔罗记录模型"""

    __tablename__ = "tarot_daily_record"
    __table_args__: ClassVar[dict] = {
        "comment": "每日塔罗记录表，记录用户每日抽牌结果"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    user_id: Mapped[str] = mapped_column(
        String(255), index=True, comment="用户id"
    )
    card_id: Mapped[str] = mapped_column(String(32), comment="卡牌编号")
    card_name: Mapped[str] = mapped_column(String(64), comment="卡牌中文名")
    is_upright: Mapped[int] = mapped_column(
        default=1, comment="是否正位，1正位0逆位"
    )
    fortune_score: Mapped[int] = mapped_column(default=0, comment="运势分数")
    record_date: Mapped[date] = mapped_column(Date, comment="记录日期")
    created_at: Mapped[datetime | None] = mapped_column(
        nullable=True, comment="创建时间"
    )

    @classmethod
    async def get_today_record(cls, user_id: str) -> "TarotDailyRecord | None":
        """获取用户今日塔罗记录

        参数:
            user_id: 用户ID

        返回:
            TarotDailyRecord | None: 今日记录，不存在返回None
        """
        today = date.today()
        return await cls.safe_get_or_none(user_id=user_id, record_date=today)

    @classmethod
    async def create_daily_record(
        cls,
        user_id: str,
        card_id: str,
        card_name: str,
        is_upright: bool,
        fortune_score: int,
    ) -> "TarotDailyRecord":
        """创建每日塔罗记录

        参数:
            user_id: 用户ID
            card_id: 卡牌编号
            card_name: 卡牌中文名
            is_upright: 是否正位
            fortune_score: 运势分数

        返回:
            TarotDailyRecord: 创建的记录
        """
        today = date.today()
        record, _ = await cls.get_or_create(
            user_id=user_id,
            record_date=today,
            defaults={
                "card_id": card_id,
                "card_name": card_name,
                "is_upright": 1 if is_upright else 0,
                "fortune_score": fortune_score,
                "created_at": datetime.now(),
            },
        )
        return record

    @classmethod
    async def get_ranking(
        cls, target_date: date | None = None, limit: int = 10
    ) -> list["TarotDailyRecord"]:
        """获取指定日期运势排行榜

        参数:
            target_date: 目标日期，默认为今天
            limit: 返回数量上限

        返回:
            list[TarotDailyRecord]: 排行榜记录列表，按运势分数降序
        """
        if target_date is None:
            target_date = date.today()
        records = (
            await cls.filter(record_date=target_date)
            .order_by("-fortune_score")
            .all()
        )
        return records[:limit]

    @classmethod
    async def get_user_total_days(cls, user_id: str) -> int:
        """获取用户累计占卜天数

        参数:
            user_id: 用户ID

        返回:
            int: 累计占卜天数
        """
        records = await cls.filter(user_id=user_id).all()
        return len(records)

    # @classmethod
    # def _run_script(cls):
    #     """运行数据库迁移脚本"""
    #     return [

    #     ]


class TarotCollection(Model):
    """塔罗牌图鉴收集模型"""

    __tablename__ = "tarot_collection"
    __table_args__: ClassVar[dict] = {
        "comment": "塔罗牌图鉴收集表，记录用户收集的卡牌"
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    user_id: Mapped[str] = mapped_column(
        String(255), index=True, comment="用户id"
    )
    card_id: Mapped[str] = mapped_column(String(32), comment="卡牌编号")
    card_name: Mapped[str] = mapped_column(String(64), comment="卡牌中文名")
    upright_count: Mapped[int] = mapped_column(
        default=0, comment="正位出现次数"
    )
    reversed_count: Mapped[int] = mapped_column(
        default=0, comment="逆位出现次数"
    )
    first_seen_at: Mapped[datetime | None] = mapped_column(
        nullable=True, comment="首次出现时间"
    )

    @classmethod
    async def add_or_update(
        cls,
        user_id: str,
        card_id: str,
        card_name: str,
        is_upright: bool,
    ) -> "TarotCollection":
        """添加或更新图鉴收集记录

        参数:
            user_id: 用户ID
            card_id: 卡牌编号
            card_name: 卡牌中文名
            is_upright: 是否正位

        返回:
            TarotCollection: 收集记录
        """
        record, created = await cls.get_or_create(
            user_id=user_id,
            card_id=card_id,
            defaults={
                "card_name": card_name,
                "upright_count": 1 if is_upright else 0,
                "reversed_count": 0 if is_upright else 1,
                "first_seen_at": datetime.now(),
            },
        )
        if not created:
            if is_upright:
                record.upright_count += 1
            else:
                record.reversed_count += 1
            await record.save(
                update_fields=["upright_count", "reversed_count"]
            )
        return record

    @classmethod
    async def get_user_collection(
        cls, user_id: str
    ) -> list["TarotCollection"]:
        """获取用户图鉴收集列表

        参数:
            user_id: 用户ID

        返回:
            list[TarotCollection]: 收集记录列表
        """
        return await cls.filter(user_id=user_id).order_by("card_id").all()

    @classmethod
    async def get_user_collected_count(cls, user_id: str) -> int:
        """获取用户已收集卡牌数量

        参数:
            user_id: 用户ID

        返回:
            int: 已收集卡牌数量
        """
        records = await cls.filter(user_id=user_id).all()
        return len(records)

    @classmethod
    async def get_user_card_record(
        cls, user_id: str, card_id: str
    ) -> "TarotCollection | None":
        """获取用户某张卡牌的收集记录

        参数:
            user_id: 用户ID
            card_id: 卡牌编号

        返回:
            TarotCollection | None: 收集记录，不存在返回None
        """
        return await cls.safe_get_or_none(user_id=user_id, card_id=card_id)
