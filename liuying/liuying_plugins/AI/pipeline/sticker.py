"""贴纸选择（数据库存储版）

整合 StickerLibrary + StickerCuration，提供基于数据库的表情包选择。
图片数据优先存储在 bed_layout 本地图床，本模块负责将 StickerItem
元数据转换为可直接发送的 alc Image 对象。
保留旧 API（choose_sticker / maybe_choose_reply_sticker / list_stickers）
的兼容性，内部委托给 sticker_curation。
"""

from pathlib import Path

from nonebot_plugin_alconna import Image

from liuying.utils.bed_layout import BedLayout
from liuying.utils.log import logger

from ..core.sticker import sticker_curation, sticker_importer
from ..models.sticker_item import StickerItem

_DEFAULT_STICKER_DIR = Path("data") / "ai_plugin" / "stickers"
"""默认贴纸目录（与表情包库根目录一致）"""


class StickerManager:
    """贴纸管理器（数据库存储版）

    兼容旧 API，内部委托给 sticker_curation（基于数据库）。
    支持自动扫描入库、按情绪/偏好/反馈学习选择。
    """

    def __init__(self, sticker_dir: Path | None = None) -> None:
        """初始化贴纸管理器

        参数:
            sticker_dir: 贴纸目录，None时用默认目录
        """
        self.sticker_dir = sticker_dir or _DEFAULT_STICKER_DIR
        self._scanned = False

    async def _ensure_scanned(self) -> None:
        """确保表情包库已扫描入库（仅首次）

        扫描失败不影响主流程。
        """
        if self._scanned:
            return
        self._scanned = True
        try:
            stats = await sticker_importer.scan_directory(
                rescan=False, llm_describe=False
            )
            if stats["added"] > 0:
                logger.info(
                    f"表情包库首次扫描入库: {stats}",
                    command="AI",
                )
        except Exception as e:
            logger.debug(
                f"表情包库扫描失败（不影响主流程）: {e}",
                command="AI",
                e=e,
            )

    def should_send_sticker(
        self,
        group_id: str | None,
        is_private: bool,
        probability: float | None = None,
    ) -> bool:
        """决策是否发送贴纸

        参数:
            group_id: 群组ID，None为私聊
            is_private: 是否私聊
            probability: 触发概率，None时用配置默认

        返回:
            bool: 是否发送贴纸
        """
        return sticker_curation.should_send(
            group_id=group_id,
            is_private=is_private,
            probability=probability,
        )

    async def choose_sticker_item(
        self,
        text: str,
        persona_mood: str = "neutral",
        mood_hint: str = "",
        group_id: str | None = None,
        user_id: str = "",
        is_private: bool = False,
        force: bool = False,
    ) -> StickerItem | None:
        """选择一张表情包条目（数据库模型）

        参数:
            text: 回复文本（用于情绪检测）
            persona_mood: 人格情绪倾向
            mood_hint: 表情包情绪提示
            group_id: 群组ID
            user_id: 用户ID
            is_private: 是否私聊
            force: 是否强制发送

        返回:
            StickerItem | None: 表情包条目，无可用时返回None
        """
        await self._ensure_scanned()
        try:
            return await sticker_curation.choose_for_reply(
                text=text,
                persona_mood=persona_mood,
                mood_hint=mood_hint,
                group_id=group_id,
                user_id=user_id,
                is_private=is_private,
                force=force,
            )
        except Exception as e:
            logger.debug(
                f"表情包选择失败: {e}", command="AI", e=e
            )
            return None

    async def choose_reply_sticker_item(
        self,
        text: str,
        persona_mood: str = "neutral",
        mood_hint: str = "",
        group_id: str | None = None,
        is_private: bool = False,
        user_id: str = "",
    ) -> StickerItem | None:
        """决策并选择回复表情包条目

        综合判断是否发送贴纸，发送则返回选中的 StickerItem。

        参数:
            text: 回复文本
            persona_mood: 人格情绪倾向
            mood_hint: 表情包情绪提示（来自PersonaResponder）
            group_id: 群组ID
            is_private: 是否私聊
            user_id: 用户ID

        返回:
            StickerItem | None: 表情包条目，不发时返回None
        """
        if not self.should_send_sticker(group_id, is_private):
            return None
        try:
            return await self.choose_sticker_item(
                text=text,
                persona_mood=persona_mood,
                mood_hint=mood_hint,
                group_id=group_id,
                user_id=user_id,
                is_private=is_private,
                force=True,
            )
        except Exception as e:
            logger.debug(
                f"贴纸选择失败: {e}", command="AI", e=e
            )
            return None

    async def maybe_choose_reply_sticker(
        self,
        text: str,
        persona_mood: str = "neutral",
        mood_hint: str = "",
        group_id: str | None = None,
        is_private: bool = False,
        user_id: str = "",
    ) -> Image | None:
        """决策并选择回复贴纸

        综合判断是否发送贴纸，发送则选择一张。

        参数:
            text: 回复文本
            persona_mood: 人格情绪倾向
            mood_hint: 表情包情绪提示（来自PersonaResponder）
            group_id: 群组ID
            is_private: 是否私聊
            user_id: 用户ID

        返回:
            Image | None: 贴纸图片对象，不发时返回None
        """
        item = await self.choose_reply_sticker_item(
            text=text,
            persona_mood=persona_mood,
            mood_hint=mood_hint,
            group_id=group_id,
            is_private=is_private,
            user_id=user_id,
        )
        return await self.item_to_image(item)

    async def item_to_image(
        self, item: StickerItem | None
    ) -> Image | None:
        """将表情包条目转为可直接发送的图片对象

        优先使用 bed_layout 本地图床 URL，未迁移时回退到本地文件。

        参数:
            item: 表情包条目

        返回:
            Image | None: alc Image 对象
        """
        if not item:
            return None
        if item.bed_layout_filename:
            try:
                url = await BedLayout.get_url(item.bed_layout_filename)
                return Image(url=url)
            except Exception as e:
                logger.debug(
                    f"获取 bed_layout URL 失败: {e}",
                    command="AI",
                    e=e,
                )
        if not item.file_path:
            return None
        full_path = sticker_importer.root_dir / item.file_path
        if full_path.exists():
            return Image(path=full_path)
        # 兼容：直接使用 sticker_dir 解析
        alt_path = self.sticker_dir / item.file_path
        if alt_path.exists():
            return Image(path=alt_path)
        return None

    async def record_usage(
        self,
        sticker_id: int | None,
        context_text: str = "",
        detected_mood: str = "",
        persona_mood: str = "",
        group_id: str = "",
        user_id: str = "",
        bot_id: str = "",
    ) -> None:
        """记录贴纸使用

        参数:
            sticker_id: 表情包ID
            context_text: 触发文本
            detected_mood: 检测到的情绪
            persona_mood: 人格情绪
            group_id: 群组ID
            user_id: 用户ID
            bot_id: 机器人ID
        """
        if not sticker_id:
            return
        try:
            await sticker_curation.record_usage(
                sticker_id=sticker_id,
                context_text=context_text,
                detected_mood=detected_mood,
                persona_mood=persona_mood,
                group_id=group_id,
                user_id=user_id,
                bot_id=bot_id,
            )
        except Exception as e:
            logger.debug(
                f"记录贴纸使用失败: {e}", command="AI", e=e
            )


sticker_manager = StickerManager()
"""贴纸管理器单例"""
