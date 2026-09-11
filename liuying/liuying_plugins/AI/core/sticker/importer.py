"""表情包导入与扫描

负责表情包文件的扫描入库、去重、自动标签、LLM视觉标注、
本地图床上传、缺失文件清理与标签刷新。情绪体系常量统一从
constants 模块导入。
"""

from asyncio import to_thread
import hashlib
from pathlib import Path

from liuying.utils.bed_layout import BedLayout
from liuying.utils.log import logger

from ...agent.sticker_semantics import sticker_semantics_analyzer
from ...models.sticker_item import StickerItem
from ..llm import llm_helper
from ..llm.model_router import ROLE_STICKER, model_router
from ..tools.json_utils import extract_json_payload
from ..vision import summarize_image
from .constants import MOOD_FILENAMES, SOURCE_AI_STICKER

_DEFAULT_STICKER_ROOT = Path("data") / "ai_plugin" / "stickers"
"""默认表情包根目录"""

_DELETE_BATCH_SIZE = 500
"""缺失清理批量删除的每批ID数量"""

SEMANTIC_HINTS: dict[str, list[str]] = {
    "greet": ["hi", "hello", "wave", "嗨", "你好"],
    "bye": ["bye", "再见", "拜拜"],
    "thanks": ["thanks", "thank", "谢谢", "感谢"],
    "apology": ["sorry", "道歉", "抱歉"],
    "ridicule": ["laugh", "haha", "嘲讽", "笑话"],
    "encourage": ["cheer", "encourage", "加油", "鼓励"],
    "love": ["love", "heart", "喜欢", "爱"],
}
"""语义场景关键词"""


def resolve_sticker_path(
    root_dir: Path, file_path: str
) -> Path | None:
    """安全解析表情包相对路径，防止路径穿越

    参数:
        root_dir: 表情包根目录
        file_path: 数据库中记录的相对路径

    返回:
        Path | None: 校验通过的绝对路径，越界或非法返回 None
    """
    try:
        full = (root_dir / file_path).resolve()
        full.relative_to(root_dir.resolve())
    except (ValueError, OSError):
        return None
    return full


class StickerImporter:
    """表情包导入器

    扫描本地目录入库，提供去重、自动标注、LLM视觉标注、
    本地图床上传、缺失文件清理与标签刷新能力。
    """

    @staticmethod
    def compute_file_hash_safe(file_path: Path) -> str:
        """计算文件内容的SHA256哈希（前32位）

        参数:
            file_path: 文件路径

        返回:
            str: 哈希摘要，失败返回空串
        """
        try:
            h = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            return h.hexdigest()[:32]
        except Exception:
            return ""

    def __init__(
        self,
        root_dir: Path | None = None,
    ) -> None:
        """初始化表情包导入器

        参数:
            root_dir: 表情包根目录，None时用默认
        """
        self.root_dir = root_dir or _DEFAULT_STICKER_ROOT
        self._supported_ext = {
            ".png", ".jpg", ".jpeg", ".gif", ".webp",
        }

    async def _upload_to_bed_layout(
        self,
        file_path: Path,
        mood_tags: list[str],
        semantic_tags: list[str],
        description: str = "",
    ) -> str | None:
        """上传表情包到 bed_layout 本地图床

        参数:
            file_path: 表情包文件路径
            mood_tags: 情绪标签
            semantic_tags: 语义标签
            description: 描述

        返回:
            str | None: bed_layout 文件名，失败返回 None
        """
        try:
            category = mood_tags[0] if mood_tags else "general"
            tags = list(dict.fromkeys(mood_tags + semantic_tags))
            _, _, filename = await BedLayout.upload_from_file(
                file_path,
                source=SOURCE_AI_STICKER,
                category=category,
                tags=tags,
                original_filename=file_path.name,
                description=description or file_path.stem,
            )
            return filename
        except Exception as e:
            logger.warning(
                f"表情包上传 bed_layout 失败: {file_path.name}: {e}",
                command="AI",
                e=e,
            )
            return None

    async def _read_item_bytes(
        self, item: StickerItem
    ) -> bytes | None:
        """读取表情包二进制数据

        优先从 bed_layout 读取，失败时回退到本地文件。

        参数:
            item: 表情包条目

        返回:
            bytes | None: 图片二进制数据
        """
        if item.bed_layout_filename:
            try:
                data = await BedLayout.get_bytes(
                    item.bed_layout_filename
                )
                if data:
                    return data
            except Exception as e:
                logger.debug(
                    f"从 bed_layout 读取表情包失败: {e}",
                    command="AI",
                    e=e,
                )
        if not item.file_path:
            return None
        full_path = resolve_sticker_path(self.root_dir, item.file_path)
        if full_path and full_path.exists():
            return full_path.read_bytes()
        return None

    def _auto_tag_by_filename(
        self, name: str
    ) -> tuple[list[str], list[str]]:
        """基于文件名自动打情绪与语义标签

        参数:
            name: 文件名（不含扩展名）

        返回:
            tuple[list[str], list[str]]: (情绪标签, 语义标签)
        """
        name_lower = name.lower()
        mood_tags: list[str] = []
        for mood, keywords in MOOD_FILENAMES.items():
            if any(kw in name_lower for kw in keywords):
                mood_tags.append(mood)

        semantic_tags: list[str] = []
        for semantic, keywords in SEMANTIC_HINTS.items():
            if any(kw in name_lower for kw in keywords):
                semantic_tags.append(semantic)

        return mood_tags, semantic_tags

    async def scan_directory(
        self,
        rescan: bool = False,
        llm_describe: bool = False,
    ) -> dict[str, int]:
        """扫描根目录入库

        参数:
            rescan: 是否重新扫描已入库文件（更新标签）
            llm_describe: 是否调用LLM视觉标注（耗时）

        返回:
            dict: 统计字典 {added/updated/skipped/failed}
        """
        if not self.root_dir.exists():
            logger.info(
                f"表情包目录不存在: {self.root_dir}",
                command="AI",
            )
            return {
                "added": 0,
                "updated": 0,
                "skipped": 0,
                "failed": 0,
            }

        added = 0
        updated = 0
        skipped = 0
        failed = 0

        for file_path in self.root_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in self._supported_ext:
                continue

            try:
                rel_path = str(
                    file_path.relative_to(self.root_dir)
                )
                # 同步哈希计算在线程池执行，避免阻塞事件循环
                file_hash = await to_thread(
                    self.compute_file_hash_safe, file_path
                )
                file_size = file_path.stat().st_size
                file_ext = file_path.suffix.lower()
                name = file_path.stem

                existing = await StickerItem.get_by_hash(file_hash)
                if existing and not rescan:
                    # 对已有但尚未迁移到 bed_layout 的记录补上传
                    if not existing.bed_layout_filename:
                        bed_filename = (
                            await self._upload_to_bed_layout(
                                file_path,
                                existing.get_mood_tags(),
                                existing.get_semantic_tags(),
                                description=existing.description,
                            )
                        )
                        if bed_filename:
                            existing.bed_layout_filename = (
                                bed_filename
                            )
                            await existing.save(
                                update_fields=[
                                    "bed_layout_filename"
                                ]
                            )
                            updated += 1
                            continue
                    skipped += 1
                    continue

                mood_tags, semantic_tags = (
                    self._auto_tag_by_filename(name)
                )
                bed_filename = await self._upload_to_bed_layout(
                    file_path,
                    mood_tags,
                    semantic_tags,
                )

                if existing and rescan:
                    await StickerItem.update_tags(
                        existing.id,
                        mood_tags=mood_tags,
                        semantic_tags=semantic_tags,
                    )
                    if (
                        bed_filename
                        and not existing.bed_layout_filename
                    ):
                        existing.bed_layout_filename = (
                            bed_filename
                        )
                        await existing.save(
                            update_fields=[
                                "bed_layout_filename"
                            ]
                        )
                    updated += 1
                else:
                    item = await StickerItem.add_item(
                        name=name,
                        file_path=rel_path,
                        file_hash=file_hash,
                        file_size=file_size,
                        file_ext=file_ext,
                        mood_tags=mood_tags,
                        semantic_tags=semantic_tags,
                        description="",
                        source="local",
                        bed_layout_filename=bed_filename,
                    )
                    added += 1
                    if llm_describe:
                        try:
                            image_bytes = await to_thread(
                                file_path.read_bytes
                            )
                            await self._llm_describe_item(
                                item, image_bytes
                            )
                        except Exception as e:
                            logger.debug(
                                f"LLM标注失败 {name}: {e}",
                                command="AI",
                            )
            except Exception as e:
                failed += 1
                logger.debug(
                    f"扫描入库失败 {file_path}: {e}",
                    command="AI",
                    e=e,
                )

        logger.info(
            f"表情包扫描完成: 新增{added} 更新{updated} "
            f"跳过{skipped} 失败{failed}",
            command="AI",
        )
        return {
            "added": added,
            "updated": updated,
            "skipped": skipped,
            "failed": failed,
        }

    async def _llm_describe_item(
        self, item: StickerItem, image_bytes: bytes
    ) -> None:
        """调用LLM视觉能力标注表情包

        参数:
            item: 表情包条目
            image_bytes: 图片二进制数据
        """
        try:
            summary = await summarize_image(image_bytes)
            if not summary.success or not summary.description:
                return

            describe_prompt = (
                "请描述这个表情包的内容、情绪和适用场景。\n"
                "按JSON格式返回，字段：\n"
                "- description: 简洁描述（不超过30字）\n"
                "- mood_tags: 情绪标签数组（从 happy/sad/excited/angry/shy/calm/warm/\n"
                "  playful/greet/bye/thanks/apology/ridicule/encourage/love 中选择）\n"
                "- semantic_tags: 语义标签数组"
                "（greet/bye/thanks/apology/ridicule/"
                "encourage/love等）\n"
                "\n"
                "只返回JSON。"
            )
            role = model_router.resolve(ROLE_STICKER)
            response = await llm_helper.chat_text(
                [
                    {
                        "role": "system",
                        "content": describe_prompt,
                    },
                    {
                        "role": "user",
                        "content": (
                            f"图片描述: {summary.description}\n"
                            f"文件名: {item.name}"
                        ),
                    },
                ],
                model=role.model or None,
                options=role.apply_to_options({"temperature": 0.2}),
                provider_name=role.provider or None,
            )

            description = ""
            semantic_tags: list[str] = []
            parsed = extract_json_payload(response)
            if parsed is not None:
                description = str(
                    parsed.get("description", "")
                ).strip()
                mood_tags = [
                    str(t)
                    for t in parsed.get("mood_tags", [])
                    if t
                ]
                semantic_tags = [
                    str(t)
                    for t in parsed.get("semantic_tags", [])
                    if t
                ]
                await StickerItem.update_tags(
                    item.id,
                    mood_tags=mood_tags or None,
                    semantic_tags=semantic_tags or None,
                    description=description or None,
                )
            else:
                # 直接用视觉描述作为description
                await StickerItem.update_tags(
                    item.id, description=summary.description
                )

            # 语义分析：补充结构化 mood/scene 标签（带缓存，不会重复调用）
            try:
                final_desc = (
                    description
                    if description
                    else summary.description
                )
                semantics = await sticker_semantics_analyzer.analyze_sticker(
                    sticker_id=item.id,
                    description=final_desc or "",
                    filename=item.name or "",
                )
                if semantics.analyzed and semantics.mood:
                    extra_tags = [semantics.mood]
                    if semantics.scene:
                        extra_tags.append(semantics.scene)
                    merged = list(
                        set(semantic_tags) | set(extra_tags)
                    )
                    if merged:
                        await StickerItem.update_tags(
                            item.id,
                            semantic_tags=merged,
                        )
            except Exception as e:
                logger.debug(
                    f"贴纸语义补充失败 {item.name}: {e}",
                    command="AI",
                    e=e,
                )
        except Exception as e:
            logger.debug(
                f"LLM视觉标注失败 {item.name}: {e}",
                command="AI",
                e=e,
            )

    async def prune_missing(self) -> int:
        """清理本地已删除的文件对应的记录

        已迁移到 bed_layout 的记录不再依赖本地文件，因此跳过。
        仅拉取轻量字段元组（id/路径/图床名）判断缺失，
        收集缺失ID后按批批量删除，避免全表加载ORM对象。

        返回:
            int: 清理的记录数
        """
        rows = await StickerItem.filter().limit(5000).values_list(
            "id", "file_path", "bed_layout_filename"
        )
        missing_ids: list[int] = []
        for item_id, file_path, bed_filename in rows:
            if bed_filename or not file_path:
                continue
            full_path = resolve_sticker_path(self.root_dir, file_path)
            if not full_path or not full_path.exists():
                missing_ids.append(item_id)

        removed = 0
        for start in range(0, len(missing_ids), _DELETE_BATCH_SIZE):
            batch = missing_ids[start : start + _DELETE_BATCH_SIZE]
            removed += await StickerItem.filter().where_in(
                "id", batch
            ).delete()
        if removed > 0:
            logger.info(
                f"清理缺失表情包记录{removed}条",
                command="AI",
            )
        return removed

    async def refresh_tags(
        self, item_id: int, llm_describe: bool = False
    ) -> bool:
        """刷新单个表情包的标签

        参数:
            item_id: 表情包ID
            llm_describe: 是否调用LLM视觉标注

        返回:
            bool: 是否成功
        """
        item = await StickerItem.filter(id=item_id).first()
        if not item:
            return False

        mood_tags, semantic_tags = self._auto_tag_by_filename(
            item.name
        )
        await StickerItem.update_tags(
            item_id,
            mood_tags=mood_tags,
            semantic_tags=semantic_tags,
        )

        if llm_describe:
            image_bytes = await self._read_item_bytes(item)
            if image_bytes:
                await self._llm_describe_item(item, image_bytes)
        return True


sticker_importer = StickerImporter()
"""表情包导入器单例"""
