"""意图规则

提供基于关键词的回合意图匹配能力，作为LLM规划的快速决策路径。
"""

from dataclasses import dataclass, field
from typing import Any

from ....config import get_config
from ..constants import (
    DEFAULT_AGENT_MAX_STEPS,
    INTENT_TAG_ADMIN,
    INTENT_TAG_IMAGE,
    INTENT_TAG_LOCAL,
    INTENT_TAG_MEMORY,
    INTENT_TAG_NETWORK,
    INTENT_TAG_REALTIME,
    OUTPUT_MODE_CHAT_ANSWER,
    OUTPUT_MODE_CHAT_SHORT,
    OUTPUT_MODE_SILENCE,
    OUTPUT_MODE_SOURCE_SUMMARY,
    OUTPUT_MODE_STRUCTURED_HELP,
    TURN_ACTION_REPLY,
    TURN_ACTION_SILENCE,
)
from .types import TurnPlan


def _get_agent_max_steps() -> int:
    """从配置读取Agent最大步数

    允许运行时通过 AGENT_MAX_STEPS 配置项调整Agent循环上限，
    未配置或类型异常时回退到 DEFAULT_AGENT_MAX_STEPS 常量。

    返回:
        int: Agent最大步数
    """
    raw = get_config("AGENT_MAX_STEPS", DEFAULT_AGENT_MAX_STEPS)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return DEFAULT_AGENT_MAX_STEPS


@dataclass(slots=True)
class IntentRule:
    """意图规则配置

    将关键词匹配到对应的回合动作和工具配置，
    由 IntentRuleManager 管理和匹配。

    Attributes:
        name: 规则名称
        keywords: 关键词列表
        priority: 优先级（数字越小优先级越高）
        action: 对应的回合动作
        output_mode: 输出模式
        intent_tags: 意图标签
        need_tool: 是否需要工具调用
        tool_candidates: 候选工具列表
        tool_name: 指定工具名
        tool_args_template: 工具参数模板（支持 {message}/{message_short}）
        need_memory: 是否需要记忆召回
        memory_query_template: 记忆查询模板（支持 {message}）
        need_research: 是否需要多步研究
        reason: 决策理由
    """

    name: str
    keywords: list[str]
    priority: int = 100
    action: str = TURN_ACTION_REPLY
    output_mode: str = OUTPUT_MODE_CHAT_SHORT
    intent_tags: list[str] = field(default_factory=list)
    need_tool: bool = False
    tool_candidates: list[str] = field(default_factory=list)
    tool_name: str = ""
    tool_args_template: dict[str, str] = field(default_factory=dict)
    need_memory: bool = False
    memory_query_template: str = ""
    need_research: bool = False
    reason: str = ""

    def to_plan(self, user_message: str) -> TurnPlan:
        """从规则和用户消息构建TurnPlan

        参数:
            user_message: 原始用户消息

        返回:
            TurnPlan: 规划结果
        """
        tool_args: dict[str, Any] = {}
        for key, template in self.tool_args_template.items():
            tool_args[key] = (
                template
                .replace("{message}", user_message)
                .replace("{message_short}", user_message[:100])
            )

        memory_query = (
            self.memory_query_template.replace(
                "{message}", user_message
            )
            if self.memory_query_template
            else ""
        )

        return TurnPlan(
            action=self.action,
            output_mode=self.output_mode,
            intent_tags=list(self.intent_tags),
            need_tool=self.need_tool,
            tool_candidates=list(self.tool_candidates),
            tool_name=self.tool_name,
            tool_args=tool_args,
            need_memory=self.need_memory,
            memory_query=memory_query,
            need_research=self.need_research,
            max_steps=_get_agent_max_steps(),
            reason=self.reason,
            user_message=user_message,
        )


class IntentRuleManager:
    """意图规则管理器

    管理意图规则列表，提供按优先级匹配的方法。
    支持运行时动态添加和移除规则。
    """

    def __init__(self) -> None:
        """初始化规则管理器"""
        self._rules: list[IntentRule] = []
        self._load_default_rules()

    def _load_default_rules(self) -> None:
        """加载默认意图规则"""
        self._rules = [
            IntentRule(
                name="silence",
                keywords=["ai关闭", "ai禁用", "关闭ai"],
                priority=10,
                action=TURN_ACTION_SILENCE,
                output_mode=OUTPUT_MODE_SILENCE,
                reason="用户已禁用AI",
            ),
            IntentRule(
                name="help",
                keywords=["帮助", "怎么用", "命令", "help", "用法"],
                priority=20,
                action=TURN_ACTION_REPLY,
                output_mode=OUTPUT_MODE_STRUCTURED_HELP,
                intent_tags=[INTENT_TAG_LOCAL],
                reason="求助场景",
            ),
            IntentRule(
                name="realtime",
                keywords=[
                    "今天", "现在", "最新", "实时", "新闻",
                    "天气", "股价", "汇率",
                ],
                priority=30,
                action=TURN_ACTION_REPLY,
                output_mode=OUTPUT_MODE_SOURCE_SUMMARY,
                intent_tags=[INTENT_TAG_REALTIME, INTENT_TAG_NETWORK],
                need_tool=True,
                tool_candidates=["web_search"],
                tool_name="web_search",
                tool_args_template={"query": "{message_short}"},
                need_research=True,
                reason="实时信息查询",
            ),
            IntentRule(
                name="draw",
                keywords=["画", "生成图", "绘制", "绘图", "画一张"],
                priority=40,
                action=TURN_ACTION_REPLY,
                output_mode=OUTPUT_MODE_CHAT_ANSWER,
                intent_tags=[INTENT_TAG_IMAGE],
                need_tool=True,
                tool_candidates=["image_generate"],
                tool_name="image_generate",
                tool_args_template={"prompt": "{message}"},
                reason="图片生成请求",
            ),
            IntentRule(
                name="memory",
                keywords=[
                    "还记得", "记不记得", "上次", "之前",
                    "历史", "回忆",
                ],
                priority=50,
                action=TURN_ACTION_REPLY,
                output_mode=OUTPUT_MODE_CHAT_ANSWER,
                intent_tags=[INTENT_TAG_MEMORY],
                need_memory=True,
                memory_query_template="{message}",
                reason="记忆召回请求",
            ),
            IntentRule(
                name="admin",
                keywords=[
                    "切换人格", "清空对话", "查看画像", "查看记忆",
                    "流萤人格", "流萤清空", "流萤画像", "流萤记忆",
                ],
                priority=60,
                action=TURN_ACTION_REPLY,
                output_mode=OUTPUT_MODE_CHAT_SHORT,
                intent_tags=[INTENT_TAG_ADMIN],
                reason="管理操作命令",
            ),
        ]

    def match(self, text: str) -> IntentRule | None:
        """按优先级匹配文本到意图规则

        参数:
            text: 输入文本（已转小写）

        返回:
            IntentRule | None: 匹配的最高优先级规则
        """
        for rule in sorted(self._rules, key=lambda r: r.priority):
            if any(kw in text for kw in rule.keywords):
                return rule
        return None

    def add_rule(self, rule: IntentRule) -> None:
        """添加规则

        参数:
            rule: 意图规则
        """
        self._rules.append(rule)

    def remove_rule(self, name: str) -> None:
        """移除规则

        参数:
            name: 规则名称
        """
        self._rules = [r for r in self._rules if r.name != name]

    def list_rules(self) -> list[IntentRule]:
        """列出所有规则

        返回:
            list[IntentRule]: 规则列表
        """
        return list(self._rules)
