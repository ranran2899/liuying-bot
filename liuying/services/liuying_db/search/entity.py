"""实体与关系管理器

提供文档级实体标注存储、实体检索与知识图谱三元组（subject-relation-object）
管理能力。实体检索用于按实体名召回文档，关系表用于存储实体间关系。
"""

from sqlalchemy import text as sql_text

from ..session import session_manager


class EntityManager:
    """实体与关系管理器

    示例:
        ```python
        ent = EntityManager("default")
        await ent.upsert_entities(1, [
            {"name": "流萤", "type": "character", "weight": 1.5},
        ])
        results = await ent.entity_search(["流萤"], top_k=5)
        ```
    """

    __slots__ = ("_db_name",)

    def __init__(self, db_name: str = "default") -> None:
        """初始化实体管理器

        参数:
            db_name: 数据库名称，默认 'default'
        """
        self._db_name = db_name

    async def upsert_entities(
        self,
        doc_id: int,
        entities: list[dict],
    ) -> None:
        """存储文档实体标注（先删后插）

        参数:
            doc_id: 文档 ID
            entities: 实体列表，每项含 name/type/weight
        """
        async with session_manager.get_session(self._db_name) as session:
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
            await session.commit()

    async def entity_search(
        self,
        entity_names: list[str],
        top_k: int = 10,
    ) -> list[tuple[int, float]]:
        """实体检索

        按实体名匹配文档，按权重求和后归一化打分。

        参数:
            entity_names: 实体名列表
            top_k: 返回条数上限

        返回:
            list[tuple[int, float]]: (doc_id, score) 列表，按分数降序
        """
        if not entity_names:
            return []
        placeholders = ",".join(f":p{i}" for i in range(len(entity_names)))
        params: dict[str, int | str] = {f"p{i}": v for i, v in enumerate(entity_names)}
        params["limit"] = top_k
        sql = (
            f"SELECT doc_id, SUM(weight) as total "
            f"FROM search_entities "
            f"WHERE entity_name IN ({placeholders}) "
            f"GROUP BY doc_id ORDER BY total DESC LIMIT :limit"
        )
        async with session_manager.get_session(self._db_name) as session:
            result = await session.execute(sql_text(sql), params)
            rows = result.fetchall()
        if not rows:
            return []
        max_score = rows[0][1] or 1.0
        return [(row[0], (row[1] or 0.0) / max_score) for row in rows]

    async def add_relation(
        self,
        subject: str,
        relation: str,
        obj: str,
        weight: float = 1.0,
        doc_id: int | None = None,
    ) -> None:
        """添加实体关系（知识图谱三元组）

        参数:
            subject: 主体实体名
            relation: 关系名
            obj: 客体实体名
            weight: 关系权重
            doc_id: 关联文档 ID，可选
        """
        async with session_manager.get_session(self._db_name) as session:
            await session.execute(
                sql_text(
                    "INSERT INTO search_relations"
                    "(subject, relation, object, weight, doc_id) "
                    "VALUES(:subject, :relation, :object, :weight, :doc_id)"
                ),
                {
                    "subject": subject,
                    "relation": relation,
                    "object": obj,
                    "weight": weight,
                    "doc_id": doc_id,
                },
            )
            await session.commit()

    async def get_relations_by_subject(
        self,
        subject: str,
        limit: int = 50,
    ) -> list[dict]:
        """按主体查询关系

        参数:
            subject: 主体实体名
            limit: 返回条数上限

        返回:
            list[dict]: 关系列表，每项含 subject/relation/object/weight/doc_id
        """
        async with session_manager.get_session(self._db_name) as session:
            result = await session.execute(
                sql_text(
                    "SELECT subject, relation, object, weight, doc_id "
                    "FROM search_relations WHERE subject = :subject "
                    "ORDER BY weight DESC LIMIT :limit"
                ),
                {"subject": subject, "limit": limit},
            )
            rows = result.fetchall()
        return [
            {
                "subject": row[0],
                "relation": row[1],
                "object": row[2],
                "weight": row[3],
                "doc_id": row[4],
            }
            for row in rows
        ]

    async def delete(self, doc_id: int) -> None:
        """删除指定文档的所有实体标注

        参数:
            doc_id: 文档 ID
        """
        async with session_manager.get_session(self._db_name) as session:
            await session.execute(
                sql_text("DELETE FROM search_entities WHERE doc_id = :doc_id"),
                {"doc_id": doc_id},
            )
            await session.execute(
                sql_text("DELETE FROM search_relations WHERE doc_id = :doc_id"),
                {"doc_id": doc_id},
            )
            await session.commit()
