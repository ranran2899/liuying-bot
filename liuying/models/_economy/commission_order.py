"""委托求购板求购单模型"""

from datetime import datetime, timedelta
from typing import ClassVar

import orjson as json
from sqlalchemy import BigInteger, DateTime, Integer, String, Text
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


class CommissionOrder(Model):
    """委托求购板求购单模型"""

    __tablename__ = "commission_order"
    __table_args__: ClassVar[dict] = {"comment": "委托求购板求购单表"}

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="自增id",
    )
    buyer_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="求购者用户ID"
    )
    item_data: Mapped[str] = mapped_column(
        Text, default="{}", comment="道具信息JSON（含id字段）"
    )
    quantity: Mapped[int] = mapped_column(
        Integer, default=1, comment="求购数量"
    )
    fulfilled_quantity: Mapped[int] = mapped_column(
        Integer, default=0, comment="已满足数量"
    )
    unit_price: Mapped[int] = mapped_column(
        Integer, default=0, comment="单价"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="创建时间"
    )
    expire_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None, comment="到期时间"
    )

    @property
    def item_id(self) -> str:
        """道具ID（从item_data JSON的id字段读取）"""
        return self.get_data().get("id", "")

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

    def set_data(self, data: dict) -> None:
        """设置道具信息JSON

        参数:
            data: 道具信息字典
        """
        self.item_data = json.dumps(data).decode()

    def to_dict(self) -> dict:
        """转换为统一展示字典

        返回:
            dict: 包含道具信息和求购信息的字典
        """
        data = self.get_data()
        return {
            **{key: data.get(key, "") for key in _TO_DICT_FIELDS},
            "quantity": self.quantity,
            "fulfilled_quantity": self.fulfilled_quantity,
            "unit_price": self.unit_price,
            "buyer_id": self.buyer_id,
            "item_id": data.get("id", ""),
            "expire_at": str(self.expire_at) if self.expire_at else None,
        }

    @classmethod
    async def add_order(
        cls,
        buyer_id: str,
        item_id: str,
        quantity: int,
        unit_price: int,
        item_data: dict,
        expire_days: int = 3,
    ) -> bool:
        """创建求购单，同一买家对同一道具的求购单累加数量并更新价格

        参数:
            buyer_id: 求购者用户ID
            item_id: 道具ID
            quantity: 求购数量
            unit_price: 单价
            item_data: 道具信息字典
            expire_days: 到期天数，默认3天

        返回:
            bool: 是否创建成功
        """
        if quantity <= 0 or unit_price < 0:
            return False

        expire_at = datetime.now() + timedelta(days=expire_days)

        existing = await cls._find_by_buyer_and_item(buyer_id, item_id)
        if existing:
            existing.quantity += quantity
            existing.unit_price = unit_price
            existing.set_data({"id": item_id, **item_data})
            existing.expire_at = expire_at
            await existing.save(
                update_fields=[
                    "quantity",
                    "unit_price",
                    "item_data",
                    "expire_at",
                ]
            )
            return True

        await cls.create(
            buyer_id=buyer_id,
            quantity=quantity,
            unit_price=unit_price,
            item_data=json.dumps({"id": item_id, **item_data}).decode(),
            expire_at=expire_at,
        )
        return True

    @classmethod
    async def _find_by_buyer_and_item(
        cls, buyer_id: str, item_id: str
    ) -> "CommissionOrder | None":
        """通过买家ID和道具ID查找求购单

        参数:
            buyer_id: 求购者用户ID
            item_id: 道具ID

        返回:
            CommissionOrder | None: 求购单实例
        """
        orders = await cls.filter(buyer_id=buyer_id).all()
        return next((o for o in orders if o.item_id == item_id), None)

    @classmethod
    async def get_user_orders(cls, buyer_id: str) -> list[dict]:
        """获取用户求购单列表

        参数:
            buyer_id: 求购者用户ID

        返回:
            list[dict]: 求购单字典列表
        """
        orders = await cls.filter(buyer_id=buyer_id).all()
        return [order.to_dict() for order in orders]

    @classmethod
    async def get_active_orders(cls) -> list[dict]:
        """获取所有活跃求购单（排除已过期和已满足的）

        返回:
            list[dict]: 活跃求购单字典列表
        """
        now = datetime.now()
        orders = await cls.filter(
            cls.fulfilled_quantity < cls.quantity
        ).all()
        return [
            order.to_dict()
            for order in orders
            if not order.expire_at or order.expire_at > now
        ]

    @classmethod
    async def find_by_keyword(cls, keyword: str) -> list[dict]:
        """按关键字搜索求购单（支持ID或名称模糊匹配）

        参数:
            keyword: 搜索关键字

        返回:
            list[dict]: 匹配的求购单字典列表
        """
        all_orders = await cls.get_active_orders()
        return [
            order
            for order in all_orders
            if keyword in order.get("name", "")
            or keyword in order.get("id", "")
            or keyword == order.get("id", "")
            or keyword == order.get("name", "")
        ]

    @classmethod
    async def fulfill(
        cls, buyer_id: str, item_id: str, quantity: int
    ) -> bool:
        """增加已满足数量，满足全部时自动删除

        参数:
            buyer_id: 求购者用户ID
            item_id: 道具ID
            quantity: 满足数量

        返回:
            bool: 是否满足成功
        """
        if quantity <= 0:
            return False

        order = await cls._find_by_buyer_and_item(buyer_id, item_id)
        if not order:
            return False

        remaining = order.quantity - order.fulfilled_quantity
        if remaining < quantity:
            return False

        order.fulfilled_quantity += quantity
        if order.fulfilled_quantity >= order.quantity:
            await order.delete()
        else:
            await order.save(update_fields=["fulfilled_quantity"])
        return True

    @classmethod
    async def cancel_order(
        cls, buyer_id: str, item_id: str, quantity: int
    ) -> tuple[int, dict | None]:
        """取消求购单，减少数量或删除，返回取消数量和求购单信息

        参数:
            buyer_id: 求购者用户ID
            item_id: 道具ID
            quantity: 取消数量

        返回:
            tuple[int, dict | None]: (实际取消数量, 求购单信息字典)
        """
        if quantity <= 0:
            return 0, None

        order = await cls._find_by_buyer_and_item(buyer_id, item_id)
        if not order:
            return 0, None

        remaining = order.quantity - order.fulfilled_quantity
        cancel_qty = min(quantity, remaining)
        if cancel_qty <= 0:
            return 0, None

        order_data = order.to_dict()
        order.quantity -= cancel_qty
        if order.quantity <= order.fulfilled_quantity:
            await order.delete()
        else:
            await order.save(update_fields=["quantity"])

        return cancel_qty, order_data

    @classmethod
    async def expire_orders(cls) -> list["CommissionOrder"]:
        """查找所有已过期的求购单

        返回:
            list[CommissionOrder]: 已过期的求购单列表
        """
        now = datetime.now()
        return await cls.filter(cls.expire_at <= now).all()

    @classmethod
    def _run_script(cls):
        """数据库迁移脚本"""
        return [
            "CREATE TABLE IF NOT EXISTS commission_order ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "buyer_id VARCHAR(255), "
            "item_data TEXT DEFAULT '{}', "
            "quantity INTEGER DEFAULT 1, "
            "fulfilled_quantity INTEGER DEFAULT 0, "
            "unit_price INTEGER DEFAULT 0, "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
            "expire_at DATETIME DEFAULT NULL);",
            "CREATE INDEX IF NOT EXISTS ix_commission_order_buyer_id "
            "ON commission_order (buyer_id);",
            "ALTER TABLE commission_order ADD COLUMN fulfilled_quantity "
            "INTEGER DEFAULT 0;",
            "ALTER TABLE commission_order ADD COLUMN expire_at DATETIME "
            "DEFAULT NULL;",
        ]
