"""更新、删除和批量操作方法模块"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import delete, update

from ..utils import DbUtils
from .filter import FilterMixin


class UpdateDeleteBuilder(FilterMixin):
    """更新、删除和批量操作构建器"""

    __slots__ = ()

    model_class: type
    kwargs: dict[str, Any]
    args: tuple[Any, ...]
    _db_name: str
    _with_deleted: bool

    async def update(self, **values: Any) -> int:
        """批量更新

        参数:
            **values: 要更新的字段和值

        返回:
            int: 受影响的行数
        """
        async with self.model_class.get_session(db_name=self._db_name) as session:
            stmt = self._apply_filters(update(self.model_class))
            stmt = stmt.values(**values)
            result = await session.execute(stmt)
            await session.flush()
            return result.rowcount

    async def delete(self) -> int:
        """批量删除

        返回:
            int: 受影响的行数
        """
        async with self.model_class.get_session(db_name=self._db_name) as session:
            stmt = self._apply_filters(delete(self.model_class))
            result = await session.execute(stmt)
            await session.flush()
            return result.rowcount

    @staticmethod
    def _build_mapping(obj: Any, fields: list[str] | None = None) -> dict:
        """构建对象映射字典

        参数:
            obj: 模型对象
            fields: 要映射的字段列表

        返回:
            dict: 映射字典
        """
        match fields:
            case None:
                return {
                    col.name: getattr(obj, col.name) for col in obj.__table__.columns
                }
            case _:
                mapping = {f: getattr(obj, f) for f in fields if hasattr(obj, f)}
                for pk_name in DbUtils.get_primary_key_names(obj.__class__):
                    if hasattr(obj, pk_name):
                        mapping[pk_name] = getattr(obj, pk_name)
                return mapping

    async def bulk_create(
        self,
        objects: list[Any],
        batch_size: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[Any]:
        """批量创建记录

        参数:
            objects: 要创建的对象列表
            batch_size: 批量大小，用于分批创建
            progress_callback: 进度回调函数，参数为 (当前处理数量, 总数量)

        返回:
            list: 创建后的对象列表
        """
        if not objects:
            return []

        total = len(objects)
        pk_names = DbUtils.get_primary_key_names(self.model_class)

        for obj in objects:
            for pk_name in pk_names:
                if hasattr(obj, pk_name) and getattr(obj, pk_name) is None:
                    setattr(obj, pk_name, None)

        async with self.model_class.get_session(db_name=self._db_name) as session:
            if batch_size and batch_size > 0:
                processed = 0
                for i in range(0, total, batch_size):
                    batch = objects[i : i + batch_size]
                    session.add_all(batch)
                    await session.flush()
                    processed += len(batch)
                    if progress_callback:
                        progress_callback(processed, total)
            else:
                session.add_all(objects)
                await session.flush()
                if progress_callback:
                    progress_callback(total, total)

            for obj in objects:
                await session.refresh(obj)

            return objects

    async def bulk_update(
        self,
        objects: list[Any],
        fields: list[str] | None = None,
        batch_size: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> int:
        """批量更新多个记录

        参数:
            objects: 要更新的对象列表
            fields: 要更新的字段列表
            batch_size: 批量大小，用于分批更新
            progress_callback: 进度回调函数，参数为 (当前处理数量, 总数量)

        返回:
            int: 更新的记录数
        """
        if not objects:
            return 0

        total = len(objects)
        updated_count = 0

        async with self.model_class.get_session(db_name=self._db_name) as session:
            if batch_size and batch_size > 0:
                for i in range(0, total, batch_size):
                    batch = objects[i : i + batch_size]
                    mappings = [self._build_mapping(obj, fields) for obj in batch]
                    await session.run_sync(
                        lambda s: s.bulk_update_mappings(self.model_class, mappings)
                    )
                    updated_count += len(batch)
                    await session.flush()
                    if progress_callback:
                        progress_callback(min(i + batch_size, total), total)
            else:
                mappings = [self._build_mapping(obj, fields) for obj in objects]
                await session.run_sync(
                    lambda s: s.bulk_update_mappings(self.model_class, mappings)
                )
                updated_count = len(objects)
                await session.flush()
                if progress_callback:
                    progress_callback(total, total)

            return updated_count

    async def bulk_delete(
        self,
        objects: list[Any],
        batch_size: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> int:
        """批量删除多个记录

        参数:
            objects: 要删除的对象列表
            batch_size: 批量大小，用于分批删除
            progress_callback: 进度回调函数，参数为 (当前处理数量, 总数量)

        返回:
            int: 删除的记录数
        """
        if not objects:
            return 0

        total = len(objects)
        deleted_count = 0

        async with self.model_class.get_session(db_name=self._db_name) as session:
            if batch_size and batch_size > 0:
                for i in range(0, total, batch_size):
                    batch = objects[i : i + batch_size]
                    for obj in batch:
                        await session.delete(obj)
                        deleted_count += 1
                    await session.flush()
                    if progress_callback:
                        progress_callback(min(i + batch_size, total), total)
            else:
                for obj in objects:
                    await session.delete(obj)
                    deleted_count += 1
                await session.flush()
                if progress_callback:
                    progress_callback(total, total)

            return deleted_count

    async def _atomic_update(self, column: str | Any, amount: int) -> int:
        """原子性更新字段值（增减）

        参数:
            column: 列名或列对象
            amount: 变化量（正数为增加，负数为减少）

        返回:
            int: 受影响的行数
        """
        column = DbUtils.get_column(self.model_class, column)
        async with self.model_class.get_session(db_name=self._db_name) as session:
            stmt = self._apply_filters(update(self.model_class))
            stmt = stmt.values({column: column + amount})
            result = await session.execute(stmt)
            await session.flush()
            return result.rowcount

    async def increment(self, column: str | Any, amount: int = 1) -> int:
        """原子性增加字段值

        参数:
            column: 列名或列对象
            amount: 增加的值，默认为1

        返回:
            int: 受影响的行数
        """
        return await self._atomic_update(column, amount)

    async def decrement(self, column: str | Any, amount: int = 1) -> int:
        """原子性减少字段值

        参数:
            column: 列名或列对象
            amount: 减少的值，默认为1

        返回:
            int: 受影响的行数
        """
        return await self._atomic_update(column, -amount)

    async def soft_delete(self) -> int:
        """软删除符合条件的记录，设置 deleted_at 为当前时间

        仅对拥有 deleted_at 字段的模型生效。

        返回:
            int: 受影响的行数
        """
        if not hasattr(self.model_class, "deleted_at"):
            raise AttributeError(
                f"模型 {self.model_class.__name__} 没有 deleted_at 字段，无法执行软删除"
            )

        async with self.model_class.get_session(db_name=self._db_name) as session:
            stmt = self._apply_filters(update(self.model_class))
            stmt = stmt.values(deleted_at=datetime.now())
            result = await session.execute(stmt)
            await session.flush()
            return result.rowcount

    async def restore(self) -> int:
        """恢复软删除的记录，将 deleted_at 设为 None

        仅对拥有 deleted_at 字段的模型生效。

        返回:
            int: 受影响的行数
        """
        if not hasattr(self.model_class, "deleted_at"):
            raise AttributeError(
                f"模型 {self.model_class.__name__} 没有 deleted_at 字段，无法执行恢复"
            )

        self._with_deleted = True

        async with self.model_class.get_session(db_name=self._db_name) as session:
            stmt = self._apply_filters(update(self.model_class))
            stmt = stmt.values(deleted_at=None)
            result = await session.execute(stmt)
            await session.flush()
            return result.rowcount
