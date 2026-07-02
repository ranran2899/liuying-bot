"""记忆策展器与演化引擎

负责记忆质量评估、去重合并、主题聚合、矛盾检测、
主动学习（实体识别与画像更新）。
作为记忆系统的上层策展层，定期对已有记忆进行演化。
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from typing import Any

from liuying.utils.log import logger

from ...models.conversation_record import ConversationRecord
from ...models.memory_item import MemoryItem
from ...models.user_persona import UserPersonaProfile
from ._common import _hash_bow_embedding
from .extractors import CurationExtractor
from .manager import memory_manager

_QUALITY_THRESHOLD = 0.4
"""低质量记忆阈值（低于此值标记为待清理）"""

_DEDUP_SIMILARITY = 0.85
"""去重相似度阈值"""

_TOPIC_MIN_MEMBERS = 2
"""主题聚合最小成员数"""

_ACTIVE_LEARN_BATCH = 20
"""主动学习单批处理条数"""


@dataclass(slots=True)
class CurationReport:
    """策展报告

    Attributes:
        evaluated: 评估的记忆数
        low_quality: 低质量记忆数
        deduplicated: 去重的记忆数
        merged: 合并的记忆数
        topics_formed: 形成的主题数
        entities_extracted: 提取的实体数
        personas_updated: 更新的画像数
        duration: 耗时（秒）
    """

    evaluated: int = 0
    low_quality: int = 0
    deduplicated: int = 0
    merged: int = 0
    topics_formed: int = 0
    entities_extracted: int = 0
    personas_updated: int = 0
    duration: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """导出字典

        返回:
            dict: 报告字典
        """
        return {
            "evaluated": self.evaluated,
            "low_quality": self.low_quality,
            "deduplicated": self.deduplicated,
            "merged": self.merged,
            "topics_formed": self.topics_formed,
            "entities_extracted": self.entities_extracted,
            "personas_updated": self.personas_updated,
            "duration": round(self.duration, 3),
        }


class MemoryCurator:
    """记忆策展器

    定期对记忆进行质量评估、去重合并、主题聚合、主动学习。
    作为记忆系统的上层策展层，不参与实时召回。
    """

    def __init__(self) -> None:
        """初始化策展器"""
        self._last_curation: datetime | None = None
        self._curating = False

    async def curate_all(
        self,
        user_id: str | None = None,
        max_memories: int = 500,
    ) -> CurationReport:
        """执行完整策展流程

        参数:
            user_id: 限定用户ID，None时处理所有用户
            max_memories: 单次处理上限

        返回:
            CurationReport: 策展报告
        """
        if self._curating:
            logger.debug(
                "记忆策展正在进行中，跳过本次",
                command="AI",
            )
            return CurationReport()
        self._curating = True
        start_ts = datetime.now().timestamp()
        report = CurationReport()

        try:
            report.evaluated = await self._evaluate_quality(
                user_id, max_memories, report
            )
            report.deduplicated = await self._deduplicate(
                user_id, max_memories // 2
            )
            report.topics_formed = await self._aggregate_topics(
                user_id
            )
            report.entities_extracted, report.personas_updated = (
                await self._active_learn(user_id)
            )

            self._last_curation = datetime.now()
            report.duration = (
                datetime.now().timestamp() - start_ts
            )
            logger.info(
                f"记忆策展完成: {report.to_dict()}",
                command="AI",
            )
            return report
        finally:
            self._curating = False

    async def _evaluate_quality(
        self,
        user_id: str | None,
        max_count: int,
        report: CurationReport,
    ) -> int:
        """评估记忆质量

        参数:
            user_id: 用户ID
            max_count: 最大处理数
            report: 策展报告

        返回:
            int: 评估的记忆数
        """
        try:
            query = MemoryItem.filter()
            if user_id:
                query = query.filter(user_id=user_id)
            memories = await query.limit(max_count).all()
            count = 0
            for mem in memories:
                count += 1
                score = CurationExtractor.score_memory_quality(
                    mem
                )
                if score < _QUALITY_THRESHOLD:
                    report.low_quality += 1
                    if (
                        mem.tier == "background"
                        and mem.reinforcement_count == 0
                    ):
                        try:
                            await mem.delete()
                        except Exception:
                            pass
            return count
        except Exception as e:
            logger.debug(
                f"记忆质量评估失败: {e}", command="AI", e=e
            )
            return 0

    async def _deduplicate(
        self,
        user_id: str | None,
        max_count: int,
    ) -> int:
        """去重合并相似记忆

        参数:
            user_id: 用户ID
            max_count: 最大处理数

        返回:
            int: 去重的记忆数
        """
        try:
            query = MemoryItem.filter()
            if user_id:
                query = query.filter(user_id=user_id)
            memories = await query.order_by("-create_time").limit(
                max_count
            ).all()
            if len(memories) < 2:
                return 0

            vectors: list[tuple[int, list[float]]] = []
            for mem in memories:
                vec = _hash_bow_embedding(
                    mem.summary or mem.content or ""
                )
                vectors.append((mem.id, vec))

            dedup_count = 0
            # 映射: 被删除记忆ID -> 保留者ID，避免引用过期循环变量
            to_delete: dict[int, int] = {}
            for i in range(len(vectors)):
                if vectors[i][0] in to_delete:
                    continue
                for j in range(i + 1, len(vectors)):
                    if vectors[j][0] in to_delete:
                        continue
                    sim = CurationExtractor.cosine_similarity(
                        vectors[i][1], vectors[j][1]
                    )
                    if sim >= _DEDUP_SIMILARITY:
                        older_id = vectors[j][0]
                        keeper_id = vectors[i][0]
                        to_delete[older_id] = keeper_id
                        dedup_count += 1

            for mid, keeper_id in to_delete.items():
                try:
                    mem = await MemoryItem.filter(id=mid).first()
                    if mem:
                        await memory_manager.reinforce(keeper_id)
                        await mem.delete()
                except Exception:
                    pass

            return dedup_count
        except Exception as e:
            logger.debug(
                f"记忆去重失败: {e}", command="AI", e=e
            )
            return 0

    async def _aggregate_topics(
        self, user_id: str | None
    ) -> int:
        """主题聚合

        将语义相似的记忆聚合成主题，提升为semantic层。

        参数:
            user_id: 用户ID

        返回:
            int: 形成的主题数
        """
        try:
            query = MemoryItem.filter(tier="episodic")
            if user_id:
                query = query.filter(user_id=user_id)
            memories = await query.limit(100).all()
            if len(memories) < _TOPIC_MIN_MEMBERS:
                return 0

            clusters: list[list[MemoryItem]] = []
            for mem in memories:
                placed = False
                mem_vec = _hash_bow_embedding(mem.summary or "")
                for cluster in clusters:
                    rep = cluster[0]
                    rep_vec = _hash_bow_embedding(
                        rep.summary or ""
                    )
                    if (
                        CurationExtractor.cosine_similarity(
                            mem_vec, rep_vec
                        )
                        >= 0.6
                    ):
                        cluster.append(mem)
                        placed = True
                        break
                if not placed:
                    clusters.append([mem])

            topic_count = 0
            for cluster in clusters:
                if len(cluster) < _TOPIC_MIN_MEMBERS:
                    continue
                summaries = [m.summary or "" for m in cluster]
                combined = " | ".join(summaries[:5])
                persona_name = (
                    cluster[0].persona_name or "default"
                )
                existing = await MemoryItem.filter(
                    user_id=cluster[0].user_id,
                    persona_name=persona_name,
                    tier="semantic",
                    summary=combined[:200],
                ).first()
                if existing:
                    continue
                await memory_manager.add(
                    user_id=cluster[0].user_id,
                    content=combined[:500],
                    summary=combined[:200],
                    group_id=cluster[0].group_id,
                    tier="semantic",
                    topic_tags=[cluster[0].user_id],
                    salience=0.7,
                    persona_name=persona_name,
                )
                topic_count += 1
            return topic_count
        except Exception as e:
            logger.debug(
                f"主题聚合失败: {e}", command="AI", e=e
            )
            return 0

    async def _active_learn(
        self, user_id: str | None
    ) -> tuple[int, int]:
        """主动学习

        从最近对话中提取实体与偏好，更新用户画像。

        参数:
            user_id: 用户ID

        返回:
            tuple[int, int]: (提取的实体数, 更新的画像数)
        """
        try:
            cutoff = datetime.now() - timedelta(hours=24)
            query = ConversationRecord.filter(
                create_time__gt=cutoff,
                role="user",
            )
            if user_id:
                query = query.filter(user_id=user_id)
            records = await query.order_by("-create_time").limit(
                _ACTIVE_LEARN_BATCH
            ).all()
            if not records:
                return 0, 0

            entity_counter: dict[str, dict[str, Any]] = (
                defaultdict(
                    lambda: {"count": 0, "type": "generic"}
                )
            )
            preference_counter: dict[str, dict[str, int]] = (
                defaultdict(lambda: {"count": 0, "type": ""})
            )

            for record in records:
                entities = CurationExtractor.extract_entities(
                    record.content or ""
                )
                for ent in entities:
                    entity_counter[ent.name]["count"] += 1
                    entity_counter[ent.name]["type"] = (
                        ent.entity_type
                    )

                prefs = CurationExtractor.detect_preferences(
                    record.content or ""
                )
                for pref in prefs:
                    key = pref["target"]
                    preference_counter[key]["count"] += 1
                    preference_counter[key]["type"] = pref["type"]

            extracted_count = 0
            user_ids_processed: set[str] = set()
            for record in records:
                if record.user_id in user_ids_processed:
                    continue
                user_ids_processed.add(record.user_id)

                user_entities = [
                    {
                        "name": name,
                        "count": info["count"],
                        "type": info["type"],
                    }
                    for name, info in entity_counter.items()
                ][:10]
                user_prefs = [
                    {
                        "target": target,
                        "count": info["count"],
                        "type": info["type"],
                    }
                    for target, info in preference_counter.items()
                ][:10]

                if not user_entities and not user_prefs:
                    continue

                updated = await self._update_user_persona(
                    user_id=record.user_id,
                    entities=user_entities,
                    preferences=user_prefs,
                )
                if updated:
                    extracted_count += len(user_entities)

            persona_updated = len(user_ids_processed)
            return extracted_count, persona_updated
        except Exception as e:
            logger.debug(
                f"主动学习失败: {e}", command="AI", e=e
            )
            return 0, 0

    async def _update_user_persona(
        self,
        user_id: str,
        entities: list[dict[str, Any]],
        preferences: list[dict[str, Any]],
    ) -> bool:
        """更新用户画像

        将提取的实体与偏好写入 structured_json 字段。

        参数:
            user_id: 用户ID
            entities: 实体列表
            preferences: 偏好列表

        返回:
            bool: 是否更新成功
        """
        try:
            profile, _ = await UserPersonaProfile.get_or_create(
                user_id=user_id
            )
            try:
                structured = json.loads(
                    profile.structured_json or "{}"
                )
                if not isinstance(structured, dict):
                    structured = {}
            except (json.JSONDecodeError, TypeError):
                structured = {}

            existing_entities = structured.get("entities", [])
            if not isinstance(existing_entities, list):
                existing_entities = []
            existing_set = {
                e.get("name", "")
                for e in existing_entities
                if isinstance(e, dict)
            }
            for ent in entities:
                if ent["name"] not in existing_set:
                    existing_entities.append(
                        {
                            "name": ent["name"],
                            "type": ent["type"],
                            "count": ent["count"],
                        }
                    )
                    existing_set.add(ent["name"])
            structured["entities"] = existing_entities[-50:]

            existing_prefs = structured.get("preferences", [])
            if not isinstance(existing_prefs, list):
                existing_prefs = []
            for pref in preferences:
                existing_prefs.append(
                    {
                        "target": pref["target"],
                        "type": pref["type"],
                        "count": pref["count"],
                    }
                )
            structured["preferences"] = existing_prefs[-50:]

            profile.structured_json = json.dumps(
                structured, ensure_ascii=False
            )
            profile.updated_at = datetime.now()
            await profile.save(
                update_fields=["structured_json", "updated_at"]
            )
            return True
        except Exception as e:
            logger.debug(
                f"更新用户画像失败: {e}", command="AI", e=e
            )
            return False

    def get_last_curation_time(self) -> datetime | None:
        """获取最后策展时间

        返回:
            datetime | None: 最后策展时间
        """
        return self._last_curation


memory_curator = MemoryCurator()
"""记忆策展器单例"""
