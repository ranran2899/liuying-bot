"""知识库表结构定义

定义知识条目、FTS5 全文索引、向量存储、实体关系等表结构 DDL。
表名统一加 ``kb_`` 前缀以避免与其他插件表冲突。

注意：FTS5 虚拟表必须通过原生 SQL 执行 DDL，无法由 ORM 创建。
"""

# 知识条目主表（供知识库 CRUD 使用）
KB_ENTRY_DDL = """
CREATE TABLE IF NOT EXISTS kb_entries(
    doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    tags TEXT DEFAULT '',
    source TEXT DEFAULT '',
    metadata TEXT,
    create_time TEXT DEFAULT (datetime('now')),
    update_time TEXT DEFAULT (datetime('now'))
)
"""

# FTS5 原始文本表（保留可读原文，便于排查）
KB_FTS_TEXT_DDL = """
CREATE TABLE IF NOT EXISTS kb_fts_text(
    doc_id INTEGER PRIMARY KEY,
    text TEXT,
    metadata TEXT
)
"""

# FTS5 虚拟表（content 列被索引）
KB_FTS_IDX_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts_idx
USING fts5(
    doc_id UNINDEXED,
    content,
    tokenize = 'unicode61'
)
"""

# 向量嵌入主表（一个文档对应一个嵌入向量）
KB_EMBEDDINGS_DDL = """
CREATE TABLE IF NOT EXISTS kb_embeddings(
    doc_id INTEGER PRIMARY KEY,
    embedding TEXT NOT NULL,
    model_version TEXT DEFAULT 'hash_bow',
    dim INTEGER DEFAULT 64
)
"""

# 向量分块表（一个文档可拆为多个分块向量）
KB_VECTOR_CHUNKS_DDL = """
CREATE TABLE IF NOT EXISTS kb_vector_chunks(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER NOT NULL,
    chunk_index INTEGER DEFAULT 0,
    vector TEXT NOT NULL,
    salience REAL DEFAULT 0.5,
    confidence REAL DEFAULT 0.5,
    model_version TEXT DEFAULT 'hash_bow',
    embedding_dim INTEGER DEFAULT 64
)
"""

# 实体表（一个文档可关联多个实体）
KB_ENTITIES_DDL = """
CREATE TABLE IF NOT EXISTS kb_entities(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER NOT NULL,
    entity_name TEXT NOT NULL,
    entity_type TEXT DEFAULT 'general',
    weight REAL DEFAULT 1.0
)
"""

# 实体关系表（知识图谱三元组存储）
KB_RELATIONS_DDL = """
CREATE TABLE IF NOT EXISTS kb_relations(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    relation TEXT NOT NULL,
    object TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    doc_id INTEGER
)
"""

# 辅助索引 DDL
KB_INDEX_DDL: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_kb_embeddings_filter "
    "ON kb_embeddings(dim, model_version)",
    "CREATE INDEX IF NOT EXISTS idx_kb_vec_chunks_doc "
    "ON kb_vector_chunks(doc_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_vec_chunks_filter "
    "ON kb_vector_chunks(embedding_dim, model_version)",
    "CREATE INDEX IF NOT EXISTS idx_kb_entities_doc "
    "ON kb_entities(doc_id)",
    "CREATE INDEX IF NOT EXISTS idx_kb_entities_name "
    "ON kb_entities(entity_name)",
    "CREATE INDEX IF NOT EXISTS idx_kb_relations_sub "
    "ON kb_relations(subject)",
    "CREATE INDEX IF NOT EXISTS idx_kb_relations_obj "
    "ON kb_relations(object)",
]
"""辅助索引 DDL 列表"""

ALL_DDL: list[str] = [
    KB_ENTRY_DDL,
    KB_FTS_TEXT_DDL,
    KB_FTS_IDX_DDL,
    KB_EMBEDDINGS_DDL,
    KB_VECTOR_CHUNKS_DDL,
    KB_ENTITIES_DDL,
    KB_RELATIONS_DDL,
    *KB_INDEX_DDL,
]
"""全部 DDL 列表，按依赖顺序排列"""
