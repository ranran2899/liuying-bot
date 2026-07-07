"""搜索模块表结构定义与初始化

定义 FTS5 全文索引、向量存储、实体关系等表结构 DDL，
并提供统一初始化入口。表名统一加 `search_` 前缀以避免与
业务表冲突。

注意：FTS5 虚拟表无法由 SQLAlchemy ``Base.metadata.create_all``
创建，必须通过原生 SQL 执行 DDL，因此独立于 ORM 体系。
"""

from sqlalchemy import text as sql_text

from liuying.configs.config import BotConfig
from liuying.utils.log import logger

from ..config import LOG_COMMAND
from ..session import session_manager

SEARCH_DDL: list[str] = [
    # FTS5 全文索引原始文本表（保留可读原文，便于排查）
    """
    CREATE TABLE IF NOT EXISTS search_fts(
        doc_id INTEGER PRIMARY KEY,
        text TEXT,
        metadata TEXT
    )
    """,
    # FTS5 虚拟表（content 列被索引；metadata 不参与索引）
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS search_fts_idx
    USING fts5(
        doc_id UNINDEXED,
        content,
        tokenize = 'unicode61'
    )
    """,
    # 向量嵌入主表（一个文档对应一个嵌入向量）
    """
    CREATE TABLE IF NOT EXISTS search_embeddings(
        doc_id INTEGER PRIMARY KEY,
        embedding TEXT NOT NULL,
        model_version TEXT DEFAULT 'hash_bow',
        dim INTEGER DEFAULT 64
    )
    """,
    (
        "CREATE INDEX IF NOT EXISTS idx_search_embeddings_filter "
        "ON search_embeddings(dim, model_version)"
    ),
    # 向量分块表（一个文档可拆为多个分块向量）
    """
    CREATE TABLE IF NOT EXISTS search_vector_chunks(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_id INTEGER NOT NULL,
        chunk_index INTEGER DEFAULT 0,
        vector TEXT NOT NULL,
        salience REAL DEFAULT 0.5,
        confidence REAL DEFAULT 0.5,
        model_version TEXT DEFAULT 'hash_bow',
        embedding_dim INTEGER DEFAULT 64
    )
    """,
    (
        "CREATE INDEX IF NOT EXISTS idx_search_vec_chunks_doc "
        "ON search_vector_chunks(doc_id)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS idx_search_vec_chunks_filter "
        "ON search_vector_chunks(embedding_dim, model_version)"
    ),
    # 实体表（一个文档可关联多个实体）
    """
    CREATE TABLE IF NOT EXISTS search_entities(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_id INTEGER NOT NULL,
        entity_name TEXT NOT NULL,
        entity_type TEXT DEFAULT 'general',
        weight REAL DEFAULT 1.0
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_search_entities_doc ON search_entities(doc_id)",
    (
        "CREATE INDEX IF NOT EXISTS idx_search_entities_name "
        "ON search_entities(entity_name)"
    ),
    # 实体关系表（知识图谱三元组存储）
    """
    CREATE TABLE IF NOT EXISTS search_relations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT NOT NULL,
        relation TEXT NOT NULL,
        object TEXT NOT NULL,
        weight REAL DEFAULT 1.0,
        doc_id INTEGER
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_search_relations_sub ON search_relations(subject)",
    "CREATE INDEX IF NOT EXISTS idx_search_relations_obj ON search_relations(object)",
]
"""搜索相关表的 DDL 列表"""


async def init_search_tables(db_name: str = "default") -> None:
    """初始化搜索相关表结构

    仅对 SQLite 数据库执行 FTS5/向量/实体表 DDL，其他数据库跳过。
    重复执行安全（所有 DDL 均 IF NOT EXISTS）。

    参数:
        db_name: 数据库名称，默认 'default'
    """
    sql_type = BotConfig.get_sql_type(db_name)
    if not sql_type.startswith("sqlite"):
        logger.debug(
            f"跳过搜索表初始化：数据库 {db_name} 非 SQLite (类型={sql_type})",
            LOG_COMMAND,
        )
        return

    logger.debug(f"开始初始化搜索表结构 (db={db_name})", LOG_COMMAND)
    async with session_manager.get_session(db_name) as session:
        for ddl in SEARCH_DDL:
            await session.execute(sql_text(ddl))
        await session.commit()
    logger.debug(f"搜索表结构初始化完成 (db={db_name})", LOG_COMMAND)
