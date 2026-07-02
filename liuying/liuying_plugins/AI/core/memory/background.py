"""后台智能处理

异步后台分析用户对话，提取潜在记忆点、更新画像、
巩固记忆等，不阻塞主回复流程。受
BACKGROUND_INTELLIGENCE_ENABLED 配置开关控制。
"""

import asyncio
from datetime import datetime

from liuying.utils.log import logger

from ...config import get_config
from ..llm import llm_helper
from .manager import memory_manager

_ANALYZE_PROMPT = """请分析以下对话，提取关键信息：
{history}

请用JSON格式返回，字段：
- topics: 话题标签列表
- entities: 关键实体列表
- summary: 一句话总结
只返回JSON，不要其他内容。"""


class BackgroundIntelligence:
    """后台智能处理器

    在主回复完成后异步执行分析任务，将结果写回记忆与画像系统。
    """

    def __init__(self) -> None:
        """初始化后台智能处理器"""
        self._running: set[str] = set()
        """正在处理中的 user_id 集合"""
        self._lock = asyncio.Lock()
        """并发锁"""

    async def process_background(
        self, user_id: str, messages: list[dict]
    ) -> None:
        """异步处理用户对话

        提取记忆点、更新画像、巩固记忆。失败不影响主流程。

        参数:
            user_id: 用户ID
            messages: 对话消息列表
        """
        if not get_config("BACKGROUND_INTELLIGENCE_ENABLED", True):
            return
        if not messages or len(messages) < 2:
            return
        async with self._lock:
            if user_id in self._running:
                logger.debug(
                    f"后台处理已在进行: {user_id}",
                    command="AI",
                )
                return
            self._running.add(user_id)
        try:
            await self._do_process(user_id, messages)
        except Exception as e:
            logger.warning(
                f"后台智能处理失败: {e}",
                command="AI",
                e=e,
            )
        finally:
            async with self._lock:
                self._running.discard(user_id)

    async def _do_process(
        self, user_id: str, messages: list[dict]
    ) -> None:
        """执行后台分析任务

        参数:
            user_id: 用户ID
            messages: 对话消息列表
        """
        history = self._format_history(messages)
        prompt = _ANALYZE_PROMPT.format(history=history[:1500])
        try:
            summary = await llm_helper.chat_text(
                [{"role": "user", "content": prompt}],
                options={"temperature": 0.3},
            )
        except Exception as e:
            logger.debug(
                f"后台LLM分析失败，跳过: {e}",
                command="AI",
                e=e,
            )
            return
        try:
            await memory_manager.add(
                user_id=user_id,
                content=history[:500],
                summary=summary[:200] or history[:100],
                tier="background",
                salience=0.4,
            )
        except Exception as e:
            logger.debug(
                f"后台记忆写入失败: {e}",
                command="AI",
                e=e,
            )
        logger.debug(
            f"后台智能处理完成: user={user_id}",
            command="AI",
        )

    def _format_history(self, messages: list[dict]) -> str:
        """格式化对话历史为文本

        参数:
            messages: 对话消息列表

        返回:
            str: 格式化后的历史文本
        """
        lines: list[str] = []
        for msg in messages[-20:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            lines.append(f"{role}: {content}")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines.append(f"[分析时间] {ts}")
        return "\n".join(lines)


background_intelligence = BackgroundIntelligence()
"""后台智能处理器单例"""
