"""搜索管理器统一门面

组合 FTS、向量、实体三个子管理器，提供统一初始化、原子写入与删除等能力。
下游使用者只需 ``from liuying.services.liuying_db import search_manager``
即可访问所有搜索能力。
"""

import asyncio
from collections.abc import Awaitable, Callable
import functools
import json
import sqlite3

from sqlalchemy import text as sql_text

from liuying.utils.log import logger

from ..config import LOG_COMMAND
from ..session import nested_transaction, session_manager
from .entity import EntityManager
from .fts import FTSManager
from .schema import init_search_tables
from .vector import VectorManager

_WRITE_MAX_RETRIES = 4
"""写操作最大重试次数（含首次执行）"""

_WRITE_BASE_DELAY = 0.15
"""写操作重试初始延迟（秒），每次翻倍"""


def _is_database_locked_error(exc: Exception) -> bool:
    """判断异常是否为 SQLite database is locked 错误

    参数:
        exc: 异常实例

    返回:
        bool: 是否为锁冲突错误
    """
    for err in (exc, exc.__cause__, exc.__context__):
        if isinstance(err, sqlite3.OperationalError):
            msg = str(err).lower()
            if "database is locked" in msg or "is locked" in msg:
                return True
    return False


def _with_write_lock(func: Callable[..., Awaitable[None]]):
    """装饰器：为写操作添加全局写锁与重试机制

    串行化所有写操作，从根本上避免 SQLite 并发写锁竞争。
    遇到 ``database is locked`` 错误时自动重试（指数退避）。
    """

    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs) -> None:
        async with self._write_lock:
            for attempt in range(_WRITE_MAX_RETRIES):
                try:
                    await func(self, *args, **kwargs)
                    return
                except Exception as e:
                    if not (
                        _is_database_locked_error(e)
                        and attempt < _WRITE_MAX_RETRIES - 1
                    ):
                        raise
                    delay = _WRITE_BASE_DELAY * (2**attempt)
                    logger.debug(
                        f"数据库写锁冲突，{delay:.2f}s 后重试 "
                        f"({attempt + 1}/{_WRITE_MAX_RETRIES}): {e}",
                        LOG_COMMAND,
                    )
                    await asyncio.sleep(delay)

    return wrapper


class SearchManager:
    """搜索管理器

    示例:
        ```python
        from liuying.services.liuying_db import search_manager

        await search_manager.init()
        await search_manager.fts.upsert(1, "今天天气真好")
        results = await search_manager.fts.search("天气")
        await search_manager.delete_document(1)
        ```
    """

    __slots__ = ("_db_name", "_write_lock", "entity", "fts", "vector")

    def __init__(self, db_name: str = "default") -> None:
        """初始化搜索管理器

        参数:
            db_name: 数据库名称，默认 'default'
        """
        self._db_name = db_name
        self._write_lock = asyncio.Lock()
        self.fts = FTSManager(db_name)
        self.vector = VectorManager(db_name)
        self.entity = EntityManager(db_name)

    async def init(self) -> None:
        """初始化搜索表结构（幂等，重复调用安全）"""
        await init_search_tables(self._db_name)

    @_with_write_lock
    async def upsert_document(
        self,
        doc_id: int,
        text: str,
        embedding: list[float] | None = None,
        chunks: list[dict] | None = None,
        entities: list[dict] | None = None,
        metadata: dict | None = None,
        model_version: str = "hash_bow",
    ) -> None:
        """原子写入一个文档的所有索引数据

        在单个事务内同时写入 FTS、向量、实体数据，保证一致性。
        适用于记忆索引建立、知识库写入等场景。

        参数:
            doc_id: 文档 ID
            text: 索引文本
            embedding: 主嵌入向量，None 时跳过
            chunks: 分块向量列表，None 时跳过
            entities: 实体列表，None 时跳过
            metadata: 可选元数据
            model_version: 嵌入模型版本
        """
        metadata_str = json.dumps(metadata, ensure_ascii=False) if metadata else None
        async with session_manager.get_session(self._db_name) as session:
            async with nested_transaction(session):
                await session.execute(
                    sql_text("DELETE FROM search_fts_idx WHERE doc_id = :doc_id"),
                    {"doc_id": doc_id},
                )
                await session.execute(
                    sql_text(
                        "INSERT INTO search_fts_idx(doc_id, content) "
                        "VALUES(:doc_id, :content)"
                    ),
                    {"doc_id": doc_id, "content": text},
                )
                await session.execute(
                    sql_text(
                        "INSERT OR REPLACE INTO search_fts"
                        "(doc_id, text, metadata) VALUES(:doc_id, :text, :metadata)"
                    ),
                    {
                        "doc_id": doc_id,
                        "text": text,
                        "metadata": metadata_str,
                    },
                )
                if embedding is not None:
                    await session.execute(
                        sql_text(
                            "INSERT OR REPLACE INTO search_embeddings"
                            "(doc_id, embedding, model_version, dim) "
                            "VALUES(:doc_id, :embedding, :model_version, :dim)"
                        ),
                        {
                            "doc_id": doc_id,
                            "embedding": json.dumps(embedding),
                            "model_version": model_version,
                            "dim": len(embedding),
                        },
                    )
                if chunks:
                    await session.execute(
                        sql_text(
                            "DELETE FROM search_vector_chunks WHERE doc_id = :doc_id"
                        ),
                        {"doc_id": doc_id},
                    )
                    for idx, chunk in enumerate(chunks):
                        vec = chunk.get("vector", [])
                        await session.execute(
                            sql_text(
                                "INSERT INTO search_vector_chunks"
                                "(doc_id, chunk_index, vector, salience, confidence, "
                                "model_version, embedding_dim) "
                                "VALUES(:doc_id, :chunk_index, :vector, :salience, "
                                ":confidence, :model_version, :embedding_dim)"
                            ),
                            {
                                "doc_id": doc_id,
                                "chunk_index": idx,
                                "vector": json.dumps(vec),
                                "salience": chunk.get("salience", 0.5),
                                "confidence": chunk.get("confidence", 0.5),
                                "model_version": chunk.get(
                                    "model_version", model_version
                                ),
                                "embedding_dim": len(vec),
                            },
                        )
                if entities:
                    await session.execute(
                        sql_text("DELETE FROM search_entities WHERE doc_id = :doc_id"),
                        {"doc_id": doc_id},
                    )
                    for ent in entities:
                        await session.execute(
                            sql_text(
                                "INSERT INTO search_entities"
                                "(doc_id, entity_name, entity_type, weight) "
                                "VALUES(:doc_id, :name, :type, :weight)"
                            ),
                            {
                                "doc_id": doc_id,
                                "name": ent.get("name", ""),
                                "type": ent.get("type", "general"),
                                "weight": ent.get("weight", 1.0),
                            },
                        )

    async def delete_document(self, doc_id: int) -> None:
        """原子删除一个文档的所有索引数据

        在单个事务内删除 FTS、向量、实体数据，保证一致性。
        适用于记忆硬删、过期数据清理等场景。

        参数:
            doc_id: 文档 ID
        """
        async with session_manager.get_session(self._db_name) as session:
            async with nested_transaction(session):
                await session.execute(
                    sql_text("DELETE FROM search_fts_idx WHERE doc_id = :doc_id"),
                    {"doc_id": doc_id},
                )
                await session.execute(
                    sql_text("DELETE FROM search_fts WHERE doc_id = :doc_id"),
                    {"doc_id": doc_id},
                )
                await session.execute(
                    sql_text("DELETE FROM search_embeddings WHERE doc_id = :doc_id"),
                    {"doc_id": doc_id},
                )
                await session.execute(
                    sql_text("DELETE FROM search_vector_chunks WHERE doc_id = :doc_id"),
                    {"doc_id": doc_id},
                )
                await session.execute(
                    sql_text("DELETE FROM search_entities WHERE doc_id = :doc_id"),
                    {"doc_id": doc_id},
                )
                await session.execute(
                    sql_text("DELETE FROM search_relations WHERE doc_id = :doc_id"),
                    {"doc_id": doc_id},
                )

    @_with_write_lock
    async def clear_all(self) -> None:
        """清空所有搜索相关表数据

        谨慎使用：仅用于测试或重置场景。
        """
        async with session_manager.get_session(self._db_name) as session:
            async with nested_transaction(session):
                await session.execute(sql_text("DELETE FROM search_fts_idx"))
                await session.execute(sql_text("DELETE FROM search_fts"))
                await session.execute(sql_text("DELETE FROM search_embeddings"))
                await session.execute(sql_text("DELETE FROM search_vector_chunks"))
                await session.execute(sql_text("DELETE FROM search_entities"))
                await session.execute(sql_text("DELETE FROM search_relations"))
        logger.warning("已清空所有搜索表数据", LOG_COMMAND)


search_manager = SearchManager()
"""搜索管理器单例"""
