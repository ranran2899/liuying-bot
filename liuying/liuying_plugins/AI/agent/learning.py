"""主动学习模块

检测 AI 回复中的不确定性问题，对高价值不确定性问题
做深度查证（LLM 自检 + 知识库查询），将查证结果
写入记忆系统。受 ACTIVE_LEARNING_ENABLED 配置开关控制，
配合每日配额避免成本失控。
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

from liuying.utils.log import logger

from ..config import get_config
from ..core.llm import llm_helper
from ..core.llm.model_router import ROLE_AGENT, ROLE_INTENT, model_router
from ..core.memory import memory_manager
from ..core.tools.json_utils import extract_json_payload
from ..models.memory_item import MemoryTier

_DAILY_QUOTA = 10
"""每日主动学习配额"""

_MIN_CONFIDENCE_TO_RESEARCH = 0.5
"""触发查证的最高置信度阈值"""

_DEFAULT_PERSONA = "default"
"""默认人格名"""

_QUOTA_LOCK = asyncio.Lock()
"""配额临界区锁

保护检查-查证-写入-递增整个临界区，防止并发查证
绕过 _check_quota 超发每日配额。每日配额仅 10 次，
锁内 LLM 查证串行化的代价可忽略。
"""


@dataclass(slots=True)
class UncertaintyAnalysis:
    """不确定性分析结果

    Attributes:
        has_uncertainty: 是否包含不确定信息
        uncertain_points: 不确定点列表
        confidence: 整体置信度
        worth_researching: 是否值得查证
    """

    has_uncertainty: bool
    uncertain_points: list[str]
    confidence: float
    worth_researching: bool


@dataclass(slots=True)
class ResearchResult:
    """查证结果

    Attributes:
        question: 查证问题
        finding: 查证发现
        confidence: 置信度
        success: 是否查证成功
    """

    question: str
    finding: str
    confidence: float
    success: bool


class ActiveLearning:
    """主动学习管理器

    检测 AI 回复不确定性，对高价值问题做深度查证，
    将结果写入记忆系统。
    """

    def __init__(self) -> None:
        """初始化主动学习管理器"""
        self._daily_count: int = 0
        self._day_start: datetime = datetime.now()
        self._bg_tasks: set[asyncio.Task] = set()

    async def analyze_reply(
        self,
        user_question: str,
        ai_reply: str,
    ) -> UncertaintyAnalysis | None:
        """分析AI回复的不确定性

        参数:
            user_question: 用户原始问题
            ai_reply: AI生成的回复

        返回:
            UncertaintyAnalysis | None: 分析结果，未启用返回None
        """
        if not get_config("ACTIVE_LEARNING_ENABLED", False):
            return None
        if not ai_reply or not ai_reply.strip():
            return None
        prompt = (
            "请分析以下AI回复中是否包含不确定或可能不准确的信息。\n\n"
            f"用户问题：{user_question[:200]}\n"
            f"AI回复：{ai_reply[:500]}\n\n"
            "请输出JSON格式（只输出JSON，不要其他内容）：\n"
            "{\n"
            '  "has_uncertainty": true/false,\n'
            '  "uncertain_points": ["不确定点1", "不确定点2"],\n'
            '  "confidence": 0.0-1.0,\n'
            '  "worth_researching": true/false\n'
            "}\n\n"
            "判定标准：\n"
            "- has_uncertainty: 是否包含不确定信息\n"
            "- uncertain_points: 具体的不确定点列表\n"
            "- confidence: 整体置信度（0-1）\n"
            "- worth_researching: 是否值得深入查证（高价值问题为true）"
        )
        try:
            role = model_router.resolve(ROLE_INTENT)
            _, content = await llm_helper.chat(
                [{"role": "user", "content": prompt}],
                model=role.model or None,
                options=role.apply_to_options({"temperature": 0.1}),
                provider_name=role.provider or None,
            )
            return self._parse_uncertainty(content)
        except Exception as e:
            logger.debug(
                f"不确定性分析失败: {e}",
                command="AI",
                e=e,
            )
            return None

    async def research_and_remember(
        self,
        user_id: str,
        question: str,
        context: str = "",
        persona_name: str = _DEFAULT_PERSONA,
    ) -> ResearchResult | None:
        """对问题做深度查证并写入记忆

        配额检查、LLM 查证、记忆写入与配额递增在
        _QUOTA_LOCK 临界区内串行执行；配额递增移到
        memory_manager.add 成功之后，写入失败不扣减配额。

        参数:
            user_id: 用户ID
            question: 查证问题
            context: 背景信息
            persona_name: bot人格名

        返回:
            ResearchResult | None: 查证结果，配额不足返回None
        """
        if not get_config("ACTIVE_LEARNING_ENABLED", False):
            return None
        async with _QUOTA_LOCK:
            if not self._check_quota():
                return None
            prompt = (
                "请对以下问题进行深度查证，给出准确的事实和来源说明。\n\n"
                f"查证问题：{question}\n"
                f"背景信息：{context[:300]}\n\n"
                "要求：\n"
                "1. 给出准确的事实陈述\n"
                "2. 说明信息来源（如已知）\n"
                "3. 标注置信度（0-1）\n"
                "4. 只返回查证结果，不要其他内容"
            )
            try:
                role = model_router.resolve(ROLE_AGENT)
                finding = await llm_helper.chat_text(
                    [{"role": "user", "content": prompt}],
                    model=role.model or None,
                    options=role.apply_to_options({"temperature": 0.3}),
                    provider_name=role.provider or None,
                )
                finding = finding.strip()
                if not finding:
                    return ResearchResult(
                        question=question,
                        finding="",
                        confidence=0.0,
                        success=False,
                    )
                confidence = self._estimate_confidence(finding)
                await memory_manager.add(
                    user_id=user_id,
                    content=f"查证: {question}",
                    summary=finding[:200],
                    tier=MemoryTier.SEMANTIC,
                    salience=0.8,
                    persona_name=persona_name,
                )
                # 写入成功后才递增配额，写入失败不扣减
                self._increment_quota()
            except Exception as e:
                logger.warning(
                    f"主动学习查证失败: {e}",
                    command="AI",
                    e=e,
                )
                return None
        logger.info(
            f"主动学习查证完成: user={user_id} "
            f"question={question[:50]}",
            command="AI",
        )
        return ResearchResult(
            question=question,
            finding=finding,
            confidence=confidence,
            success=True,
        )

    def process_reply_async(
        self,
        user_id: str,
        user_question: str,
        ai_reply: str,
        persona_name: str = _DEFAULT_PERSONA,
    ) -> None:
        """异步处理回复（fire-and-forget，不阻塞主流程）

        参数:
            user_id: 用户ID
            user_question: 用户原始问题
            ai_reply: AI生成的回复
            persona_name: bot人格名
        """
        # 持有Task强引用防止被GC回收导致任务静默取消
        task = asyncio.create_task(
            self._safe_process_reply(
                user_id=user_id,
                user_question=user_question,
                ai_reply=ai_reply,
                persona_name=persona_name,
            )
        )
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def _safe_process_reply(
        self,
        user_id: str,
        user_question: str,
        ai_reply: str,
        persona_name: str,
    ) -> None:
        """安全处理回复（吞异常）

        参数:
            user_id: 用户ID
            user_question: 用户原始问题
            ai_reply: AI生成的回复
            persona_name: bot人格名
        """
        try:
            analysis = await self.analyze_reply(
                user_question, ai_reply
            )
            if analysis is None or not analysis.worth_researching:
                return
            if analysis.confidence > _MIN_CONFIDENCE_TO_RESEARCH:
                return
            for point in analysis.uncertain_points[:2]:
                await self.research_and_remember(
                    user_id=user_id,
                    question=point,
                    context=user_question,
                    persona_name=persona_name,
                )
        except Exception as e:
            logger.debug(
                f"主动学习后台处理失败: {e}",
                command="AI",
                e=e,
            )

    @staticmethod
    def _parse_uncertainty(
        raw: str
    ) -> UncertaintyAnalysis:
        """解析不确定性分析结果

        参数:
            raw: LLM 返回的原始文本

        返回:
            UncertaintyAnalysis: 分析结果
        """
        data = extract_json_payload(raw)
        if data is None:
            return UncertaintyAnalysis(
                has_uncertainty=False,
                uncertain_points=[],
                confidence=1.0,
                worth_researching=False,
            )
        points = data.get("uncertain_points", [])
        if not isinstance(points, list):
            points = []
        return UncertaintyAnalysis(
            has_uncertainty=bool(data.get("has_uncertainty", False)),
            uncertain_points=[str(p) for p in points],
            confidence=float(data.get("confidence", 1.0)),
            worth_researching=bool(
                data.get("worth_researching", False)
            ),
        )

    @staticmethod
    def _estimate_confidence(finding: str) -> float:
        """估算查证结果的置信度

        参数:
            finding: 查证发现文本

        返回:
            float: 置信度（0-1）
        """
        if not finding:
            return 0.0
        low_confidence_markers = (
            "可能",
            "也许",
            "大概",
            "不确定",
            "尚无定论",
            "有待查证",
        )
        high_confidence_markers = (
            "根据",
            "数据显示",
            "研究表明",
            "事实是",
            "确认",
        )
        low_count = sum(
            1
            for marker in low_confidence_markers
            if marker in finding
        )
        high_count = sum(
            1
            for marker in high_confidence_markers
            if marker in finding
        )
        base = 0.6
        base += high_count * 0.1
        base -= low_count * 0.15
        return max(0.1, min(1.0, base))

    def _check_quota(self) -> bool:
        """检查每日配额是否充足

        返回:
            bool: 是否可用
        """
        now = datetime.now()
        if now - self._day_start >= timedelta(days=1):
            self._day_start = now
            self._daily_count = 0
        return self._daily_count < _DAILY_QUOTA

    def _increment_quota(self) -> None:
        """增加配额计数"""
        self._daily_count += 1


active_learning = ActiveLearning()
"""主动学习管理器单例"""
