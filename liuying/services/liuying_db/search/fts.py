"""FTS5 全文检索管理器

提供文档级的全文索引写入、删除、检索能力。基于 SQLite FTS5
虚拟表实现，``tokenize='unicode61'`` 支持中文/英文混合分词。

每个 ``doc_id`` 对应一份可被全文检索的文本，FTS 索引与原始文本
分别存于 ``search_fts_idx``（虚拟表）与 ``search_fts``（普通表）。
"""

import json

from sqlalchemy import text as sql_text

from liuying.utils.log import logger

from ..config import LOG_COMMAND
from ..session import session_manager


class FTSManager:
    """FTS5 全文检索管理器

    示例:
        ```python
        fts = FTSManager("default")
        await fts.upsert(1, "流萤今天去星海了", {"topic": "diary"})
        results = await fts.search("星海", limit=5)
        ```
    """

    __slots__ = ("_db_name",)

    def __init__(self, db_name: str = "default") -> None:
        """初始化 FTS 管理器

        参数:
            db_name: 数据库名称，默认 'default'
        """
        self._db_name = db_name

    async def upsert(
        self,
        doc_id: int,
        text: str,
        metadata: dict | None = None,
    ) -> None:
        """插入或更新 FTS 索引

        参数:
            doc_id: 文档 ID
            text: 待索引文本
            metadata: 可选元数据，将序列化为 JSON 存储
        """
        metadata_str = json.dumps(metadata, ensure_ascii=False) if metadata else None
        async with session_manager.get_session(self._db_name) as session:
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
            await session.commit()

    async def delete(self, doc_id: int) -> None:
        """删除指定文档的 FTS 索引

        参数:
            doc_id: 文档 ID
        """
        async with session_manager.get_session(self._db_name) as session:
            await session.execute(
                sql_text("DELETE FROM search_fts_idx WHERE doc_id = :doc_id"),
                {"doc_id": doc_id},
            )
            await session.execute(
                sql_text("DELETE FROM search_fts WHERE doc_id = :doc_id"),
                {"doc_id": doc_id},
            )
            await session.commit()

    async def search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[tuple[int, float]]:
        """FTS5 全文检索

        参数:
            query: 查询文本
            limit: 返回条数上限

        返回:
            list[tuple[int, float]]: (doc_id, score) 列表，按分数降序
        """
        if not query.strip():
            return []
        escaped = query.replace('"', '""')
        sql = (
            "SELECT doc_id, rank FROM search_fts_idx "
            "WHERE content MATCH :q ORDER BY rank LIMIT :limit"
        )
        async with session_manager.get_session(self._db_name) as session:
            result = await session.execute(
                sql_text(sql), {"q": f'"{escaped}"', "limit": limit}
            )
            rows = result.fetchall()
        if not rows:
            return []
        results: list[tuple[int, float]] = []
        for row in rows:
            doc_id = row[0]
            rank = row[1]
            score = max(0.0, 1.0 / (1.0 + abs(rank)))
            results.append((doc_id, score))
        return results

    async def clear(self) -> None:
        """清空所有 FTS 索引数据"""
        async with session_manager.get_session(self._db_name) as session:
            await session.execute(sql_text("DELETE FROM search_fts_idx"))
            await session.execute(sql_text("DELETE FROM search_fts"))
            await session.commit()
            logger.debug("已清空 FTS 索引数据", LOG_COMMAND)

    async def get_text(self, doc_id: int) -> str | None:
        """获取指定文档的原始索引文本

        参数:
            doc_id: 文档 ID

        返回:
            str | None: 原始文本，不存在返回 None
        """
        async with session_manager.get_session(self._db_name) as session:
            result = await session.execute(
                sql_text("SELECT text FROM search_fts WHERE doc_id = :doc_id"),
                {"doc_id": doc_id},
            )
            row = result.fetchone()
        return row[0] if row else None
