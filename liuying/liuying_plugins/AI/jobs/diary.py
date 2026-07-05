"""日记系统定时任务

每晚通过LLM生成流萤的日记，持久化到记忆系统。
"""

from datetime import datetime
import random

from liuying.utils.apscheduler import task_manager
from liuying.utils.log import logger

from ..config import get_config
from ..core.context import context_manager
from ..core.llm import llm_helper
from ..core.memory import memory_manager

__all__ = ["DiaryHelper", "setup_diary_job"]


_DIARY_PROMPT = """你是流萤，请根据今天的互动写一篇日记。

日期: {date}
时段: {time_period}

今日对话摘要:
{conversation_summary}

要求：
- 第一人称，像写私密日记
- 100-200字
- 记录今天印象最深的事、心情变化、对某个用户的感受
- 自然口语化，不要书面语
- 不要使用模板化用语

直接输出日记内容，不要标题。"""


_DIARY_ANGLE_POOL: tuple[str, ...] = (
    "眼前的一个生活小观察",
    "突然冒出来的一个念头或联想",
    "此刻的心情或身体感觉",
    "一个无聊的小吐槽",
    "今天的游戏或动漫里一个很小的细节",
    "对某件小事的一句反问或牢骚",
)
"""日记切入角度池"""


class DiaryHelper:
    """日记系统辅助工具类

    封装日记生成与定时任务执行逻辑。
    """

    @staticmethod
    async def generate_diary() -> str:
        """生成今日日记

        返回:
            str: 日记文本
        """
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d %A")

        try:
            summaries = await memory_manager.get_memory_summary(
                user_id="diary", limit=10
            )
            summary = "\n".join(
                s["summary"]
                for s in summaries
                if s.get("summary")
            )
        except Exception:
            summary = ""

        if not summary:
            summary = "今天没有特别的互动记录。"

        angle = random.choice(_DIARY_ANGLE_POOL)
        prompt = _DIARY_PROMPT.format(
            date=date_str,
            time_period=context_manager.get_current_time_period(),
            conversation_summary=summary[:1500],
        )
        prompt += f"\n\n[切入角度参考] {angle}"

        try:
            diary_text = await llm_helper.chat_text(
                [{"role": "user", "content": prompt}],
                options={"temperature": 0.7},
            )
            if diary_text:
                await memory_manager.add(
                    user_id="diary",
                    content=f"[日记-{date_str}]\n{diary_text}",
                    tier="episodic",
                    group_id=None,
                )
                logger.info(
                    f"日记已生成并存储: {date_str}",
                    command="AI",
                )
            return diary_text
        except Exception as e:
            logger.warning(
                f"生成日记失败: {e}",
                command="AI",
                e=e,
            )
            return ""

    @staticmethod
    async def _diary_job() -> None:
        """日记定时任务"""
        if not get_config("DIARY_ENABLED", True):
            return

        await DiaryHelper.generate_diary()


async def setup_diary_job() -> None:
    """注册日记定时任务（每晚23:00）"""
    if not get_config("DIARY_ENABLED", True):
        logger.info(
            "日记功能已禁用，跳过任务注册",
            command="AI",
        )
        return

    await task_manager.add_cron_task(
        task_id="ai_diary",
        func=DiaryHelper._diary_job,
        hour=23,
        minute=0,
    )

    logger.info(
        "日记任务已注册（每晚23:00）",
        command="AI",
    )
