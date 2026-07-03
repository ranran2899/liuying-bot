"""典当行当票模型"""

from datetime import datetime, timedelta
from typing import ClassVar

import orjson as json
from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model

_TO_DICT_FIELDS = (
    "id",
    "name",
    "description",
    "type",
    "image_url",
    "name_color",
    "description_color",
)


class PawnTicket(Model):
    """典当行当票模型"""

    __tablename__ = "pawn_ticket"
    __table_args__: ClassVar[dict] = {"comment": "典当行当票表"}

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增id"
    )
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="当铺用户ID"
    )
    item_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="道具ID"
    )
    item_data: Mapped[str] = mapped_column(
        Text, default="{}", comment="道具信息JSON"
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1, comment="当入数量")
    loan_amount: Mapped[int] = mapped_column(
        BigInteger, default=0, comment="借款金额（按估价借出的金币）"
    )
    interest_rate: Mapped[float] = mapped_column(
        Float, default=0.1, comment="利率（10%）"
    )
    pawn_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="当入时间"
    )
    redeem_due: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="赎回截止时间"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="active", comment="状态：active/redeemed/foreclosed"
    )
    redeemed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None, comment="赎回时间"
    )

    def get_data(self) -> dict:
        """解析道具信息JSON

        返回:
            dict: 道具信息字典
        """
        try:
            data = json.loads(self.item_data)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_data(self, data: dict):
        """设置道具信息JSON

        参数:
            data: 道具信息字典
        """
        self.item_data = json.dumps(data).decode()

    def to_dict(self) -> dict:
        """转换为统一展示字典

        返回:
            dict: 包含道具信息和当票信息的字典
        """
        data = self.get_data()
        return {
            **{key: data.get(key, "") for key in _TO_DICT_FIELDS},
            "quantity": self.quantity,
            "loan_amount": self.loan_amount,
            "interest_rate": self.interest_rate,
            "pawn_at": str(self.pawn_at) if self.pawn_at else None,
            "redeem_due": str(self.redeem_due) if self.redeem_due else None,
            "status": self.status,
            "redeemed_at": (
                str(self.redeemed_at) if self.redeemed_at else None
            ),
            "user_id": self.user_id,
            "item_id": self.item_id,
        }

    @classmethod
    async def create_ticket(
        cls,
        user_id: str,
        item_id: str,
        quantity: int,
        loan_amount: int,
        interest_rate: float,
        item_data: dict,
        redeem_days: int = 7,
    ) -> "PawnTicket":
        """创建当票

        参数:
            user_id: 当铺用户ID
            item_id: 道具ID
            quantity: 当入数量
            loan_amount: 借款金额
            interest_rate: 利率
            item_data: 道具信息字典
            redeem_days: 赎回期限天数，默认7天

        返回:
            PawnTicket: 创建的当票实例
        """
        now = datetime.now()
        redeem_due = now + timedelta(days=redeem_days)
        return await cls.create(
            user_id=user_id,
            item_id=item_id,
            quantity=quantity,
            loan_amount=loan_amount,
            interest_rate=interest_rate,
            item_data=json.dumps({"id": item_id, **item_data}).decode(),
            pawn_at=now,
            redeem_due=redeem_due,
            status="active",
        )

    @classmethod
    async def get_user_tickets(
        cls, user_id: str, status: str = "active"
    ) -> list[dict]:
        """获取用户当票列表

        参数:
            user_id: 当铺用户ID
            status: 当票状态，默认active

        返回:
            list[dict]: 当票字典列表
        """
        tickets = await cls.filter(user_id=user_id).all()
        result = [
            ticket
            for ticket in tickets
            if status == "all" or ticket.status == status
        ]
        result.sort(key=lambda t: t.pawn_at, reverse=True)
        return [ticket.to_dict() for ticket in result]

    @classmethod
    async def get_ticket(cls, ticket_id: int) -> "PawnTicket | None":
        """获取单张当票

        参数:
            ticket_id: 当票ID

        返回:
            PawnTicket | None: 当票实例
        """
        return await cls.filter(id=ticket_id).first()

    @classmethod
    async def redeem(
        cls, ticket_id: int, user_id: str
    ) -> tuple[bool, int, str]:
        """赎回当票

        赎回金额 = 借款本金 * (1 + 利率)，取整数

        参数:
            ticket_id: 当票ID
            user_id: 赎回用户ID

        返回:
            tuple[bool, int, str]: (是否成功, 赎回金额, 消息)
        """
        ticket = await cls.get_ticket(ticket_id)
        if not ticket:
            return False, 0, "当票不存在"
        if ticket.user_id != user_id:
            return False, 0, "这张当票不属于你"
        if ticket.status != "active":
            return False, 0, "该当票已不在活跃状态"

        redeem_amount = int(ticket.loan_amount * (1 + ticket.interest_rate))
        ticket.status = "redeemed"
        ticket.redeemed_at = datetime.now()
        await ticket.save(
            update_fields=["status", "redeemed_at"]
        )
        return True, redeem_amount, "赎回成功"

    @classmethod
    async def foreclose_expired(cls) -> list["PawnTicket"]:
        """查找已逾期未赎回的当票

        返回:
            list[PawnTicket]: 已逾期的活跃当票列表
        """
        now = datetime.now()
        tickets = await cls.filter(status="active").all()
        return [ticket for ticket in tickets if ticket.redeem_due <= now]

    @classmethod
    def _run_script(cls):
        """数据库迁移脚本"""
        return [
            "CREATE TABLE IF NOT EXISTS pawn_ticket ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "user_id VARCHAR(255), "
            "item_id VARCHAR(255), "
            "item_data TEXT DEFAULT '{}', "
            "quantity INTEGER DEFAULT 1, "
            "loan_amount INTEGER DEFAULT 0, "
            "interest_rate FLOAT DEFAULT 0.1, "
            "pawn_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
            "redeem_due DATETIME, "
            "status VARCHAR(20) DEFAULT 'active', "
            "redeemed_at DATETIME DEFAULT NULL);",
            "CREATE INDEX IF NOT EXISTS ix_pawn_ticket_user_id "
            "ON pawn_ticket (user_id);",
            "CREATE INDEX IF NOT EXISTS ix_pawn_ticket_item_id "
            "ON pawn_ticket (item_id);",
            "ALTER TABLE pawn_ticket ADD COLUMN redeemed_at DATETIME "
            "DEFAULT NULL;",
        ]
