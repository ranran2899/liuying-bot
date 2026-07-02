"""表情包条目数据模型

定义 StickerItem，存储表情包元数据：文件路径、内容哈希、
情绪标签、语义标签、使用统计、来源、禁用状态等。
"""

from datetime import datetime
import json
from typing import Any, ClassVar

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from liuying.services.liuying_db import Model


class StickerItem(Model):
    """表情包条目模型

    存储表情包元数据：文件路径、内容哈希、情绪标签、语义标签、
    使用统计、来源、禁用状态等。
    """

    __tablename__ = "ai_sticker_item"
    __table_args__: ClassVar[dict] = {
        "comment": "AI表情包条目表",
    }

    id: Mapped[int] = mapped_column(
        primary_key=True, autoincrement=True, comment="自增ID"
    )
    """自增ID"""

    name: Mapped[str] = mapped_column(
        String(255), default="", comment="表情包名（文件名）"
    )
    """表情包名（文件名）"""

    file_path: Mapped[str] = mapped_column(
        String(512), default="", comment="相对路径"
    )
    """相对路径（相对于表情包根目录）"""

    file_hash: Mapped[str] = mapped_column(
        String(64), default="", index=True, comment="文件内容哈希"
    )
    """文件内容哈希（去重用）"""

    file_size: Mapped[int] = mapped_column(
        Integer, default=0, comment="文件大小（字节）"
    )
    """文件大小（字节）"""

    file_ext: Mapped[str] = mapped_column(
        String(16), default="", comment="文件扩展名"
    )
    """文件扩展名"""

    mood_tags: Mapped[str] = mapped_column(
        Text, default="[]", comment="情绪标签JSON数组"
    )
    """情绪标签JSON数组（happy/sad/excited/angry/shy/calm/warm等）"""

    semantic_tags: Mapped[str] = mapped_column(
        Text, default="[]", comment="语义标签JSON数组"
    )
    """语义标签JSON数组（如打招呼/感谢/告别/嘲讽等场景标签）"""

    description: Mapped[str] = mapped_column(
        Text, default="", comment="表情包描述（LLM标注）"
    )
    """表情包描述（LLM标注）"""

    source: Mapped[str] = mapped_column(
        String(64), default="local", comment="来源"
    )
    """来源（local/remote/imported/user_upload）"""

    source_url: Mapped[str] = mapped_column(
        String(512), default="", comment="来源URL（远程时）"
    )
    """来源URL"""

    bed_layout_filename: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True, comment="bed_layout存储文件名"
    )
    """bed_layout存储文件名"""

    usage_count: Mapped[int] = mapped_column(
        Integer, default=0, index=True, comment="使用次数"
    )
    """使用次数"""

    positive_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="正向反馈次数"
    )
    """正向反馈次数"""

    negative_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="负向反馈次数"
    )
    """负向反馈次数"""

    last_used_time: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="最后使用时间"
    )
    """最后使用时间"""

    is_disabled: Mapped[bool] = mapped_column(
        Boolean, default=False, index=True, comment="是否禁用"
    )
    """是否禁用"""

    create_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, index=True, comment="入库时间"
    )
    """入库时间"""

    update_time: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="更新时间"
    )
    """更新时间"""

    extra: Mapped[str] = mapped_column(
        Text, default="{}", comment="额外信息JSON"
    )
    """额外信息JSON（如尺寸/分辨率/作者等）"""

    cache_type = "AI_STICKER_ITEM"
    """缓存类型"""

    cache_key_field = "id"
    """缓存键字段"""

    @classmethod
    def _run_script(cls):
        """数据库初始化脚本"""
        return [
            "CREATE INDEX IF NOT EXISTS idx_ai_sticker_item_mood "
            "ON ai_sticker_item (mood_tags)",
            "CREATE INDEX IF NOT EXISTS idx_ai_sticker_item_disabled "
            "ON ai_sticker_item (is_disabled, usage_count)",
            "ALTER TABLE ai_sticker_item ADD COLUMN "
            "bed_layout_filename VARCHAR(255)",
            "CREATE INDEX IF NOT EXISTS "
            "idx_ai_sticker_item_bed_layout_filename "
            "ON ai_sticker_item (bed_layout_filename)",
        ]

    @classmethod
    async def add_item(
        cls,
        name: str,
        file_path: str,
        file_hash: str = "",
        file_size: int = 0,
        file_ext: str = "",
        mood_tags: list[str] | None = None,
        semantic_tags: list[str] | None = None,
        description: str = "",
        source: str = "local",
        source_url: str = "",
        bed_layout_filename: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> "StickerItem":
        """添加表情包条目

        参数:
            name: 表情包名
            file_path: 文件相对路径
            file_hash: 文件哈希
            file_size: 文件大小
            file_ext: 扩展名
            mood_tags: 情绪标签
            semantic_tags: 语义标签
            description: 描述
            source: 来源
            source_url: 来源URL
            bed_layout_filename: bed_layout存储文件名
            extra: 额外信息

        返回:
            StickerItem: 创建的条目
        """
        return await cls.create(
            name=name,
            file_path=file_path,
            file_hash=file_hash,
            file_size=file_size,
            file_ext=file_ext,
            mood_tags=json.dumps(mood_tags or [], ensure_ascii=False),
            semantic_tags=json.dumps(
                semantic_tags or [], ensure_ascii=False
            ),
            description=description,
            source=source,
            source_url=source_url,
            bed_layout_filename=bed_layout_filename,
            extra=json.dumps(extra or {}, ensure_ascii=False),
        )

    @classmethod
    async def get_by_hash(
        cls, file_hash: str
    ) -> "StickerItem | None":
        """按哈希查询

        参数:
            file_hash: 文件哈希

        返回:
            StickerItem | None: 表情包条目
        """
        if not file_hash:
            return None
        return await cls.filter(file_hash=file_hash).first()

    @classmethod
    async def list_active(
        cls,
        mood: str | None = None,
        limit: int = 100,
    ) -> list["StickerItem"]:
        """列出活动表情包

        参数:
            mood: 过滤情绪标签，None时不过滤
            limit: 返回上限

        返回:
            list[StickerItem]: 表情包列表
        """
        query = cls.filter(is_disabled=False)
        if mood:
            # 简化的LIKE匹配（mood_tags为JSON数组字符串）
            query = query.filter(mood_tags__contains=mood)
        return await query.order_by("-usage_count").limit(limit).all()

    @classmethod
    async def list_disabled(
        cls, limit: int = 100
    ) -> list["StickerItem"]:
        """列出禁用表情包

        参数:
            limit: 返回上限

        返回:
            list[StickerItem]: 禁用表情包列表
        """
        return await cls.filter(is_disabled=True).limit(limit).all()

    @classmethod
    async def increment_usage(cls, item_id: int) -> None:
        """增加使用计数

        参数:
            item_id: 表情包ID
        """
        item = await cls.filter(id=item_id).first()
        if not item:
            return
        item.usage_count += 1
        item.last_used_time = datetime.now()
        await item.save(
            update_fields=["usage_count", "last_used_time"]
        )

    @classmethod
    async def update_feedback(
        cls, item_id: int, is_positive: bool
    ) -> None:
        """更新反馈计数

        参数:
            item_id: 表情包ID
            is_positive: 是否正向反馈
        """
        item = await cls.filter(id=item_id).first()
        if not item:
            return
        if is_positive:
            item.positive_count += 1
        else:
            item.negative_count += 1
        item.update_time = datetime.now()
        await item.save(
            update_fields=[
                "positive_count", "negative_count", "update_time"
            ]
        )

    @classmethod
    async def update_tags(
        cls,
        item_id: int,
        mood_tags: list[str] | None = None,
        semantic_tags: list[str] | None = None,
        description: str | None = None,
    ) -> None:
        """更新表情包标签

        参数:
            item_id: 表情包ID
            mood_tags: 情绪标签
            semantic_tags: 语义标签
            description: 描述
        """
        item = await cls.filter(id=item_id).first()
        if not item:
            return
        update_fields: list[str] = ["update_time"]
        if mood_tags is not None:
            item.mood_tags = json.dumps(mood_tags, ensure_ascii=False)
            update_fields.append("mood_tags")
        if semantic_tags is not None:
            item.semantic_tags = json.dumps(
                semantic_tags, ensure_ascii=False
            )
            update_fields.append("semantic_tags")
        if description is not None:
            item.description = description
            update_fields.append("description")
        item.update_time = datetime.now()
        await item.save(update_fields=update_fields)

    @classmethod
    async def set_disabled(
        cls, item_id: int, disabled: bool
    ) -> None:
        """设置禁用状态

        参数:
            item_id: 表情包ID
            disabled: 是否禁用
        """
        item = await cls.filter(id=item_id).first()
        if not item:
            return
        item.is_disabled = disabled
        item.update_time = datetime.now()
        await item.save(update_fields=["is_disabled", "update_time"])

    def get_mood_tags(self) -> list[str]:
        """解析情绪标签

        返回:
            list[str]: 情绪标签列表
        """
        try:
            tags = json.loads(self.mood_tags or "[]")
            return [str(t) for t in tags if t]
        except (json.JSONDecodeError, TypeError):
            return []

    def get_semantic_tags(self) -> list[str]:
        """解析语义标签

        返回:
            list[str]: 语义标签列表
        """
        try:
            tags = json.loads(self.semantic_tags or "[]")
            return [str(t) for t in tags if t]
        except (json.JSONDecodeError, TypeError):
            return []

    def get_extra(self) -> dict[str, Any]:
        """解析额外信息

        返回:
            dict: 额外信息字典
        """
        try:
            return json.loads(self.extra or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}

    @property
    def score(self) -> float:
        """综合评分（用于排序）

        基于使用次数和正负反馈计算评分。
        正向反馈加0.1，负向减0.2，使用次数加0.01。

        返回:
            float: 综合评分
        """
        usage_score = self.usage_count * 0.01
        feedback_score = (
            self.positive_count * 0.1 - self.negative_count * 0.2
        )
        return max(0.0, usage_score + feedback_score)
