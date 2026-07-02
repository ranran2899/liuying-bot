"""今日运势插件核心功能实现"""

from datetime import date, datetime
import random

from nonebot_plugin_alconna import Button
from nonebot_plugin_uninfo import Uninfo

from liuying.models._user.user_fortune import UserFortuneRecord
from liuying.utils.apscheduler import task_manager
from liuying.utils.bed_layout import BedLayout
from liuying.utils.enum import StorageType
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.utils.platform import PlatformUtils
from liuying.utils.rules import ensure_group

# 运势数据: (运势名称, 运势文案)，从低到高排列
FORTUNE_DATA: list[tuple[str, str]] = [
    ("大凶", "诸事不宜，静待风停，守得云开见月明。"),
    ("凶", "长夜漫漫，莫失本心，转机藏于不弃之间。"),
    ("小凶", "波折渐起，谨言慎行，暗流之后自有平川。"),
    ("平", "平淡如水，无风无浪，安稳亦是难得福分。"),
    ("稳", "微光不灭，跬步千里，黎明终将如约而至。"),
    ("小顺", "风起青萍，小有顺遂，细微之处见真章。"),
    ("顺", "心有所向，顺风而行，好事自会悄然降临。"),
    ("大顺", "阴霾散尽，机遇纷至，惊喜总在不期而遇。"),
    ("末吉", "吉兆初现，福运渐近，耐心等候终有回响。"),
    ("小吉", "小吉随身，逢凶化吉，幸运正与你并肩而行。"),
    ("吉", "吉星高照，所行皆坦途，所愿皆可期。"),
    ("大吉", "福泽绵长，大吉加身，万事顺遂花开有声。"),
    ("运", "七星同耀，鸿运当头，今日所求皆能如愿。"),
]

# 运势权重: 两端低中间高，星数越高越难抽到
FORTUNE_WEIGHTS: list[float] = [
    0.02, 0.04, 0.07, 0.12, 0.16, 0.15, 0.12, 0.09, 0.07, 0.06, 0.04, 0.03, 0.03
]

# 星星总数
STAR_COUNT = 13


class FortuneHandler:
    """运势命令处理器"""

    @staticmethod
    def _build_star_string(fortune_level: int) -> str:
        """根据运势等级生成星星字符串

        参数:
            fortune_level: 运势等级索引(0-12)

        返回:
            str: 由★和☆组成的星星字符串
        """
        return "★" * fortune_level + "☆" * (STAR_COUNT - fortune_level)

    @staticmethod
    async def _get_random_image_bytes() -> bytes | None:
        """从wife插件数据库中随机获取一张图片的字节数据

        返回:
            bytes | None: 图片字节数据，不存在返回None
        """
        from liuying.models.wife_image import WifeImageRecord

        image_record = await WifeImageRecord.get_random_image()
        if not image_record:
            return None
        return await BedLayout.get_bytes(
            image_record.file_path, storage_type=StorageType.LOCAL
        )

    @staticmethod
    async def _upload_fortune_image(
        user_id: str, image_bytes: bytes
    ) -> tuple[str, str, str]:
        """上传运势图片到云存储

        参数:
            user_id: 用户ID
            image_bytes: 图片字节数据

        返回:
            tuple[str, str, str]: 图片URL、宽度、高度，失败则返回空字符串元组
        """
        filename = (
            f"fortune/{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
        )
        result = await BedLayout.save_image_bytes(
            file_data=image_bytes,
            filename=filename,
            extension=".png",
            content_type="image/png",
            delete_after_minutes=1,
        )
        return result.get("url", ""), result.get("width", ""), result.get("height", "")

    @staticmethod
    def _build_markdown(
        fortune_name: str,
        star_str: str,
        fortune_text: str,
        image_url: str,
        width: str,
        height: str,
        user_id: str | None = None,
    ) -> str:
        """构建QQ Markdown内容

        参数:
            fortune_name: 运势名称
            star_str: 星星字符串
            fortune_text: 运势文案
            image_url: 图片URL
            width: 图片宽度
            height: 图片高度
            user_id: 用户ID，群聊时用于艾特

        返回:
            str: Markdown格式字符串
        """
        at_prefix = f'<qqbot-at-user id="{user_id}" /> ' if user_id else ""
        return "\n".join([
            f"### {at_prefix}今日运势：",
            fortune_name,
            star_str,
            f"> _{fortune_text}_\n",
            f"![运势卡片 #{width}px #{height}px]({image_url})",
        ])

    @staticmethod
    def _build_keyboard() -> list[list[Button]]:
        """构建QQ消息按钮

        返回:
            list[list[Button]]
        """
        return [
            [
                Button(
                    flag="enter", label="签到", clicked_label="签到",
                    id="btn_signin", text="/签到", permission="all",
                ),
                Button(
                    flag="enter", label="帮助", clicked_label="帮助",
                    id="btn_help", text="/帮助", permission="all",
                ),
            ],
            [
                Button(
                    flag="enter", label="看看我的运势", clicked_label="运势",
                    id="btn_fortune", text="/运势", permission="all",
                ),
            ],
        ]

    @classmethod
    async def fortune(cls, session: Uninfo) -> None:
        """处理今日运势命令

        参数:
            session: 用户会话信息
        """
        user_id = session.user.id
        today = date.today()

        record = await UserFortuneRecord.get_user_fortune(user_id, today)
        if record:
            fortune_level = record.fortune_level
        else:
            fortune_level = random.choices(
                range(len(FORTUNE_DATA)), weights=FORTUNE_WEIGHTS, k=1
            )[0]
            await UserFortuneRecord.set_user_fortune(user_id, fortune_level, today)

        fortune_name, fortune_text = FORTUNE_DATA[fortune_level]
        star_str = cls._build_star_string(fortune_level)
        image_bytes = await cls._get_random_image_bytes()

        # QQ官方适配器使用Markdown模板消息+按钮
        if (
            PlatformUtils.is_qbot(session)
            and not PlatformUtils.is_qq_guild(session)
            and image_bytes
        ):
            url, width, height = await cls._upload_fortune_image(user_id, image_bytes)
            if url:
                at_user_id = user_id if ensure_group(session) else None
                markdown_content = cls._build_markdown(
                    fortune_name, star_str, fortune_text,
                    url, width, height, at_user_id,
                )
                keyboard = cls._build_keyboard()
                await MessageUtils.build_markdown_message(
                    markdown_content, keyboard
                ).finish()
            logger.warning("运势图片上传失败，回退到图片发送")

        # 其他适配器使用普通消息
        msg_parts: list[str | bytes] = [
            f"今日运势: {fortune_name}\n{star_str}\n{fortune_text}"
        ]
        if image_bytes:
            msg_parts.append(image_bytes)

        await MessageUtils.build_message(msg_parts).finish(reply_to=True)

    @classmethod
    async def refresh_fortune(cls, session: Uninfo) -> None:
        """处理刷新今日运势命令

        参数:
            session: 用户会话信息
        """
        today = date.today()
        count = await UserFortuneRecord.clear_date_fortunes(today)
        await MessageUtils.build_message(
            f"已刷新今日运势，清除了 {count} 条记录"
        ).finish()


@task_manager.cron_task("fortune_daily_reset", hour=0, minute=0)
async def daily_reset_fortune():
    """每日零点重置运势"""
    count = await UserFortuneRecord.clear_all_fortunes()
    logger.info(f"每日运势重置完成，清除 {count} 条记录", command="今日运势")
