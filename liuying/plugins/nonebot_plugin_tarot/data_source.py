"""
塔罗牌插件数据源
"""
import asyncio
from bisect import bisect_right
from datetime import datetime
from io import BytesIO
from pathlib import Path
import random

from nonebot_plugin_alconna import Button
from nonebot_plugin_uninfo import Uninfo
from PIL import Image

from liuying.configs.path_config import TEMP_PATH
from liuying.models.tarot import TarotCollection, TarotDailyRecord
from liuying.services.cache import Cache
from liuying.ui.services import render
from liuying.utils.bed_layout import BedLayout
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.utils.platform import PlatformUtils

from .config import TAROT_JSON_PATH, ResourceError, get_tarot, tarot_config

try:
    import orjson as json
except ModuleNotFoundError:
    import json

ALL_SUB_TYPES: list[str] = [
    "MajorArcana", "Cups", "Pentacles", "Swords", "Wands"
]

TYPE_NAMES: dict[str, str] = {
    "MajorArcana": "大阿卡纳",
    "Cups": "圣杯",
    "Pentacles": "星币",
    "Swords": "宝剑",
    "Wands": "权杖",
}

FORTUNE_WEIGHTS: dict[str, int] = {
    "MajorArcana": 5,
    "Cups": 3,
    "Pentacles": 4,
    "Swords": 2,
    "Wands": 4,
}

_FORTUNE_THRESHOLDS = [20, 40, 60, 80]
_FORTUNE_LEVELS = ["大凶", "小凶", "末吉", "中吉", "大吉"]

_IMG_LOAD_ERROR = "图片下载出错，请重试或将资源部署本地..."

_tarot_data_cache = Cache("TAROT_DATA", result_type=dict)
_tarot_name_cache = Cache("TAROT_NAME_INDEX", result_type=dict)


async def _load_tarot_data() -> dict:
    """加载塔罗牌JSON数据

    返回:
        dict: 塔罗牌数据字典
    """
    return json.loads(TAROT_JSON_PATH.read_text(encoding="utf-8"))


def _get_fortune_level(score: int) -> str:
    """根据运势分数获取运势等级描述

    参数:
        score: 运势分数(1-100)

    返回:
        str: 运势等级描述
    """
    return _FORTUNE_LEVELS[bisect_right(_FORTUNE_THRESHOLDS, score)]


def calc_fortune_score(card_info: dict, is_upright: bool) -> int:
    """计算运势分数

    基于卡牌类型基础分 + 正逆位修正 + 随机波动

    参数:
        card_info: 卡牌信息字典
        is_upright: 是否正位

    返回:
        int: 运势分数(1-100)
    """
    base = FORTUNE_WEIGHTS.get(card_info.get("type", "MajorArcana"), 3) * 10
    modifier = random.randint(10, 30) if is_upright else random.randint(-10, 10)
    return max(1, min(100, base + modifier))


def pick_theme() -> str:
    """随机选择一个主题（本地与官方主题的并集）"""
    local_themes = {
        f.name for f in tarot_config.tarot_path.iterdir() if f.is_dir()
    }
    available = local_themes | set(tarot_config.tarot_official_themes)
    return random.choice(list(available)) if available else random.choice(
        tarot_config.tarot_official_themes
    )


def pick_sub_types(theme: str) -> list[str]:
    """根据主题选择可用的子类型"""
    if theme == "BilibiliTarot":
        return ALL_SUB_TYPES
    return [
        f.name
        for f in (tarot_config.tarot_path / theme).iterdir()
        if f.is_dir() and f.name in ALL_SUB_TYPES
    ]


def _is_qq_bot(session: Uninfo) -> bool:
    """判断是否为QQ官方Bot且非频道场景

    参数:
        session: 多平台会话信息

    返回:
        bool: 是否使用QQ MD消息
    """
    return PlatformUtils.is_qbot(session) and not PlatformUtils.is_qq_guild(session)


class QqTarotMessage:
    """QQ塔罗牌消息构建器"""

    @staticmethod
    async def upload_image(image_bytes: bytes) -> tuple[str, str, str]:
        """上传图片到云存储

        参数:
            image_bytes: 图片字节数据

        返回:
            tuple[str, str, str]: 图片URL、宽度、高度，失败则返回空字符串元组
        """
        filename = (
            f"tarot/{datetime.now().strftime('%Y%m%d%H%M%S')}_"
            f"{random.randint(1000, 9999)}.png"
        )
        result = await BedLayout.save_image_bytes(
            file_data=image_bytes,
            filename=filename,
            extension=".png",
            content_type="image/png",
            delete_after_minutes=1,
        )
        image_url = result.get("url", "")
        if not image_url:
            logger.warning("上传塔罗牌图片到云存储失败")
            return "", "", ""
        return image_url, result.get("width", ""), result.get("height", "")

    @staticmethod
    def build_markdown(
        text: str,
        image_url: str,
        width: str,
        height: str,
        user_id: str = "",
    ) -> str:
        """构建QQ Markdown内容

        参数:
            text: 文字描述
            image_url: 图片URL
            width: 图片宽度
            height: 图片高度
            user_id: 被艾特用户的ID，为空则不艾特

        返回:
            str: Markdown格式字符串
        """
        at_prefix = (
            f'<qqbot-at-user id="{user_id}" /> ' if user_id else ""
        )
        return (
            # f"# {at_prefix}\n"
            f"***{text}***\n"
            f"![塔罗牌 #{width}px #{height}px]({image_url})\n"
            # f"---"
        )

    @staticmethod
    def build_divine_markdown(
        formation_name: str,
        cards: list[tuple[str, str, str, str]],
    ) -> str:
        """构建牌阵占卜的QQ Markdown内容，所有卡牌合并在一条消息中

        参数:
            formation_name: 牌阵名称
            cards: 卡牌列表，每项为 (header, text, image_url, size_str)

        返回:
            str: Markdown格式字符串
        """
        parts = [f"## {formation_name}\n"]
        for header, text, image_url, size_str in cards:
            parts.append(f"> **{header}** {text}\n")
            parts.append(f"![塔罗牌 {size_str}]({image_url})\n")
            parts.append(">")
        parts.append("---")
        return "\n".join(parts)

    @staticmethod
    def build_keyboard() -> list[list[Button]]:
        """构建QQ消息按钮

        返回:
            list[list[Button]]: 按钮行列表
        """
        return [
            [
                Button(
                    flag="enter",
                    label="塔罗牌",
                    clicked_label="塔罗牌",
                    id="btn_divine",
                    text="/塔罗牌",
                    permission="all",
                ),
            ],
            [
                Button(
                    flag="enter",
                    label="每日塔罗",
                    clicked_label="每日塔罗",
                    id="btn_daily",
                    text="/每日塔罗",
                    permission="all",
                ),
                Button(
                    flag="enter",
                    label="运势排行",
                    clicked_label="运势排行",
                    id="btn_rank",
                    text="/运势排行",
                    permission="all",
                ),
            ],
        ]


class Tarot:
    """塔罗牌管理器"""

    async def _get_tarot_data(self) -> dict:
        """获取塔罗牌数据（带缓存）

        返回:
            dict: 塔罗牌数据字典
        """
        return await _tarot_data_cache.get_or_load(
            "all", loader=_load_tarot_data
        )

    async def _get_cards(self) -> dict[str, dict[str, ...]]:
        """获取全部卡牌数据

        返回:
            dict: 卡牌数据字典
        """
        return (await self._get_tarot_data())["cards"]

    async def _build_name_index(self) -> dict[str, str]:
        """构建卡牌中文名到ID的反向索引（带缓存）

        返回:
            dict: name_cn -> card_id 映射
        """
        return await _tarot_name_cache.get_or_load(
            "name_index",
            loader=self._do_build_name_index,
        )

    async def _do_build_name_index(self) -> dict[str, str]:
        """实际构建卡牌中文名到ID的反向索引

        返回:
            dict: name_cn -> card_id 映射
        """
        all_cards = await self._get_cards()
        return {
            info["name_cn"]: card_id
            for card_id, info in all_cards.items()
        }

    async def _send_card_message(
        self,
        session: Uninfo,
        text: str,
        image_bytes: bytes,
        is_finish: bool = True,
    ) -> None:
        """发送含图片的塔罗牌消息，根据平台自动选择MD或普通消息

        参数:
            session: 多平台会话信息
            text: 文字描述
            image_bytes: 图片字节数据
            is_finish: 是否结束会话
        """
        if _is_qq_bot(session):
            url, width, height = await QqTarotMessage.upload_image(image_bytes)
            if url:
                md_content = QqTarotMessage.build_markdown(
                    text, url, width, height, session.user.id
                )
                keyboard = QqTarotMessage.build_keyboard()
                msg = MessageUtils.build_markdown_message(
                    md_content, keyboard
                )
                await msg.finish() if is_finish else await msg.send()
                return
            logger.warning("图片上传失败，回退到图片发送")

        msg = MessageUtils.build_message([text, image_bytes])
        await msg.finish() if is_finish else await msg.send()

    async def _send_text_message(
        self,
        session: Uninfo,
        text: str,
    ) -> None:
        """发送纯文本消息，QQ适配器使用MD格式

        参数:
            session: 多平台会话信息
            text: 文本内容
        """
        if _is_qq_bot(session):
            keyboard = QqTarotMessage.build_keyboard()
            await MessageUtils.build_markdown_message(
                f"{text}\n---", keyboard
            ).finish()
        await MessageUtils.build_message(text).finish()

    async def divine(self, session: Uninfo) -> None:
        """牌阵占卜

        参数:
            session: 多平台会话信息
        """
        theme = pick_theme()
        content = await self._get_tarot_data()
        all_cards = content["cards"]
        all_formations = content["formations"]

        formation_name = random.choice(list(all_formations))
        formation = all_formations[formation_name]

        await MessageUtils.build_message(
            f"启用{formation_name}，正在洗牌中"
        ).send()

        cards_num: int = formation["cards_num"]
        cards_info_list = self._random_cards(all_cards, theme, cards_num)
        is_cut: bool = formation["is_cut"]
        representations: list[str] = random.choice(
            formation["representations"]
        )

        if _is_qq_bot(session):
            await self._divine_qq(
                session, formation_name, cards_info_list,
                is_cut, representations,
            )
        else:
            await self._divine_normal(
                session, cards_info_list, is_cut, representations,
            )

    async def _divine_qq(
        self,
        session: Uninfo,
        formation_name: str,
        cards_info_list: list[dict],
        is_cut: bool,
        representations: list[str],
    ) -> None:
        """QQ适配器牌阵占卜，合并为单条MD消息发送

        参数:
            session: 多平台会话信息
            formation_name: 牌阵名称
            cards_info_list: 卡牌信息列表
            is_cut: 是否有切牌
            representations: 牌位描述列表
        """
        card_data: list[tuple[str, str, str, str]] = []
        for i, card_info in enumerate(cards_info_list):
            header = (
                f"切牌「{representations[i]}」"
                if is_cut and i == len(cards_info_list) - 1
                else f"第{i + 1}张牌「{representations[i]}」"
            )
            text, image_bytes = await self._get_card_info(
                pick_theme(), card_info
            )
            if image_bytes is None:
                await MessageUtils.build_message(_IMG_LOAD_ERROR).finish()
            url, width, height = await QqTarotMessage.upload_image(image_bytes)
            if not url:
                logger.warning("图片上传失败，回退到逐条发送")
                await self._divine_normal(
                    session, cards_info_list, is_cut, representations,
                )
                return
            size_str = f"#{width}px #{height}px"
            card_data.append((header, text, url, size_str))

        md_content = QqTarotMessage.build_divine_markdown(
            formation_name, card_data
        )
        keyboard = QqTarotMessage.build_keyboard()
        await MessageUtils.build_markdown_message(
            md_content, keyboard
        ).finish()

    async def _divine_normal(
        self,
        session: Uninfo,
        cards_info_list: list[dict],
        is_cut: bool,
        representations: list[str],
    ) -> None:
        """普通适配器牌阵占卜，逐条发送

        参数:
            session: 多平台会话信息
            cards_info_list: 卡牌信息列表
            is_cut: 是否有切牌
            representations: 牌位描述列表
        """
        for i in range(len(cards_info_list)):
            header = (
                f"切牌「{representations[i]}」\n"
                if is_cut and i == len(cards_info_list) - 1
                else f"第{i + 1}张牌「{representations[i]}」\n"
            )
            text, image_bytes = await self._get_card_info(
                pick_theme(), cards_info_list[i]
            )
            if image_bytes is None:
                await MessageUtils.build_message(_IMG_LOAD_ERROR).finish()

            full_text = header + text
            is_last = i == len(cards_info_list) - 1

            await self._send_card_message(
                session, full_text, image_bytes, is_finish=is_last
            )
            if not is_last:
                await asyncio.sleep(1)

    async def onetime_divine(self, session: Uninfo) -> None:
        """单张塔罗牌占卜

        参数:
            session: 多平台会话信息
        """
        theme = pick_theme()
        all_cards = await self._get_cards()
        card_info_list = self._random_cards(all_cards, theme)

        text, image_bytes = await self._get_card_info(
            theme, card_info_list[0]
        )
        if image_bytes is None:
            await MessageUtils.build_message(_IMG_LOAD_ERROR).finish()

        await self._send_card_message(
            session, f"回应是\n{text}", image_bytes
        )

    async def daily_divine(self, session: Uninfo) -> None:
        """每日塔罗占卜

        每人每天限一次，记录运势分数并更新图鉴

        参数:
            session: 多平台会话信息
        """
        user_id = session.user.id
        existing = await TarotDailyRecord.get_today_record(user_id)
        if existing:
            await self._send_existing_daily(session, existing)
            return

        theme = pick_theme()
        all_cards = await self._get_cards()
        card_info_list = self._random_cards(all_cards, theme)
        card_info = card_info_list[0]

        is_upright = random.random() < 0.5
        fortune_score = calc_fortune_score(card_info, is_upright)
        fortune_level = _get_fortune_level(fortune_score)

        name_index = await self._build_name_index()
        card_id = name_index.get(card_info["name_cn"], "0")

        await TarotDailyRecord.create_daily_record(
            user_id=user_id,
            card_id=card_id,
            card_name=card_info["name_cn"],
            is_upright=is_upright,
            fortune_score=fortune_score,
        )
        await TarotCollection.add_or_update(
            user_id=user_id,
            card_id=card_id,
            card_name=card_info["name_cn"],
            is_upright=is_upright,
        )

        text, image_bytes = await self._get_card_info(
            theme, card_info, force_upright=is_upright
        )
        if image_bytes is None:
            await MessageUtils.build_message(_IMG_LOAD_ERROR).finish()

        full_text = (
            f"今日塔罗 | 运势: {fortune_score}/100 ({fortune_level})\n"
            f"{text}"
        )
        await self._send_card_message(session, full_text, image_bytes)

    async def _send_existing_daily(
        self, session: Uninfo, record: TarotDailyRecord
    ) -> None:
        """发送已存在的每日塔罗记录

        参数:
            session: 多平台会话信息
            record: 今日已有的塔罗记录
        """
        all_cards = await self._get_cards()
        card_info = all_cards.get(record.card_id)
        if card_info:
            position = "正位" if record.is_upright else "逆位"
            meaning = (
                card_info["meaning"]["up"]
                if record.is_upright
                else card_info["meaning"]["down"]
            )
            fortune_level = _get_fortune_level(record.fortune_score)
            await self._send_text_message(
                session,
                f"你今日已抽过塔罗牌了\n"
                f"今日牌面: 「{record.card_name}{position}」\n"
                f"牌义: {meaning}\n"
                f"运势评分: {record.fortune_score}/100 ({fortune_level})",
            )
        await self._send_text_message(
            session, "你今日已抽过塔罗牌了，明天再来吧"
        )

    async def fortune_ranking(self, session: Uninfo) -> None:
        """运势排行榜

        参数:
            session: 多平台会话信息
        """
        records = await TarotDailyRecord.get_ranking(limit=10)
        if not records:
            await self._send_text_message(
                session, "今日还没有人抽过每日塔罗哦，快来第一个抽吧"
            )

        lines = ["--- 今日运势排行榜 ---"]
        for i, record in enumerate(records, 1):
            position = "正位" if record.is_upright else "逆位"
            fortune_level = _get_fortune_level(record.fortune_score)
            lines.append(
                f"{i}. {record.card_name}{position} | "
                f"运势: {record.fortune_score} ({fortune_level})"
            )

        await self._send_text_message(session, "\n".join(lines))

    async def collection_view(self, session: Uninfo) -> None:
        """查看图鉴收集情况

        参数:
            session: 多平台会话信息
        """
        user_id = session.user.id
        all_cards = await self._get_cards()
        total_cards = len(all_cards)

        collected = await TarotCollection.get_user_collection(user_id)
        collected_count = len(collected)

        if collected_count == 0:
            await self._send_text_message(
                session,
                f"你还没有收集任何塔罗牌，快来抽牌吧\n"
                f"收集进度: 0/{total_cards}",
            )

        collected_ids = {c.card_id for c in collected}
        type_stats: dict[str, dict[str, int]] = {}
        for card_id, card_info in all_cards.items():
            card_type = card_info.get("type", "Unknown")
            if card_type not in type_stats:
                type_stats[card_type] = {"total": 0, "collected": 0}
            type_stats[card_type]["total"] += 1
            if card_id in collected_ids:
                type_stats[card_type]["collected"] += 1

        template_data = {
            "collectedCount": str(collected_count),
            "totalCards": str(total_cards),
            "progressPercentage": str(
                int(collected_count / total_cards * 100)
            ),
            "typeStats": [
                {
                    "typeName": TYPE_NAMES.get(t, t),
                    "collected": str(v["collected"]),
                    "total": str(v["total"]),
                    "percentage": str(
                        int(v["collected"] / v["total"] * 100)
                        if v["total"] > 0 else 0
                    ),
                }
                for t, v in type_stats.items()
            ],
            "cards": [
                {
                    "cardId": c.card_id,
                    "cardName": c.card_name,
                    "uprightCount": str(c.upright_count),
                    "reversedCount": str(c.reversed_count),
                    "totalCount": str(c.upright_count + c.reversed_count),
                }
                for c in collected
            ],
        }

        tarot_image_path = TEMP_PATH / "tarot"
        tarot_image_path.mkdir(parents=True, exist_ok=True)

        image_bytes = await render(
            "pages/builtin/tarotCollection",
            data=template_data,
            user_id=user_id,
            wait=2,
        )

        image_path = tarot_image_path / f"collection_{user_id}.png"
        image_path.write_bytes(image_bytes)

        await self._send_card_message(
            session,
            f"塔罗图鉴 | 收集进度: {collected_count}/{total_cards}",
            image_bytes,
        )

    async def card_detail(
        self, session: Uninfo, card_name_query: str
    ) -> None:
        """查看指定卡牌详情

        参数:
            session: 多平台会话信息
            card_name_query: 查询的卡牌名称
        """
        all_cards = await self._get_cards()

        matched_cards: list[tuple[str, dict]] = [
            (card_id, info)
            for card_id, info in all_cards.items()
            if card_name_query in info["name_cn"]
        ]

        if not matched_cards:
            await self._send_text_message(
                session, f"未找到包含「{card_name_query}」的塔罗牌"
            )

        if len(matched_cards) > 1:
            names = "、".join(c["name_cn"] for _, c in matched_cards)
            await self._send_text_message(
                session, f"找到多张匹配的牌: {names}\n请输入更精确的名称"
            )

        card_id, card_info = matched_cards[0]
        card_type_name = TYPE_NAMES.get(card_info["type"], card_info["type"])

        theme = pick_theme()
        text, image_bytes = await self._get_card_info(
            theme, card_info, force_upright=True
        )
        if image_bytes is None:
            await MessageUtils.build_message(_IMG_LOAD_ERROR).finish()

        full_text = (
            f"「{card_info['name_cn']}」({card_info.get('name_en', '')})\n"
            f"类型: {card_type_name}\n"
            f"正位: {card_info['meaning']['up']}\n"
            f"逆位: {card_info['meaning']['down']}\n"
            f"{text}"
        )
        await self._send_card_message(session, full_text, image_bytes)

    def _random_cards(
        self,
        all_cards: dict[str, dict[str, ...]],
        theme: str,
        num: int = 1,
    ) -> list[dict[str, ...]]:
        """随机抽取指定数量的塔罗牌

        参数:
            all_cards: 全部卡牌数据
            theme: 主题名称
            num: 抽取数量

        返回:
            list[dict]: 抽取的卡牌信息列表
        """
        sub_types = pick_sub_types(theme)
        if not sub_types:
            raise ResourceError(f"本地塔罗牌主题 {theme} 为空！请检查资源！")

        subset = {
            k: v for k, v in all_cards.items() if v.get("type") in sub_types
        }
        return [subset[k] for k in random.sample(list(subset), num)]

    async def _get_card_info(
        self,
        theme: str,
        card_info: dict[str, ...],
        force_upright: bool | None = None,
    ) -> tuple[str, bytes | None]:
        """获取塔罗牌文字与图片数据

        参数:
            theme: 主题名称
            card_info: 卡牌信息
            force_upright: 强制指定正逆位，None为随机

        返回:
            tuple[str, bytes | None]: 文字描述和图片字节数据
        """
        _type: str = card_info["type"]
        _name: str = card_info["pic"]
        img_dir: Path = tarot_config.tarot_path / theme / _type

        img_name = next(
            (p.name for p in img_dir.glob(f"{_name}.*")), ""
        )

        if not img_name:
            if theme in tarot_config.tarot_official_themes:
                data = await get_tarot(theme, _type, _name)
                if data is None:
                    return "", None
                img = Image.open(BytesIO(data))
            else:
                raise ResourceError(
                    f"塔罗牌图片 {theme}/{_type}/{_name} 不存在！"
                    f"请确保类型 {_type} 完整。"
                )
        else:
            img = Image.open(img_dir / img_name)

        is_upright = (
            force_upright
            if force_upright is not None
            else random.random() < 0.5
        )
        name_cn: str = card_info["name_cn"]
        position = "正位" if is_upright else "逆位"
        meaning: str = card_info["meaning"]["up" if is_upright else "down"]

        if not is_upright:
            img = img.rotate(180)

        buf = BytesIO()
        img.save(buf, format="png")

        text = f"「{name_cn}{position}」「{meaning}」"
        return text, buf.getvalue()


tarot_manager = Tarot()
