"""回复风格与生成阶段提示词策略

集中管理对话生成链路的共享 LLM 指令文案：人设与输出风格、
工具使用原则、多话题防串扰、工具编排阶段指令、finish 收束
描述、回复阶段受约束生成指令与模式提示、证据块头部与
安全重试提示模板，防止同类文案多处漂移。

所有文本为模块级常量/纯函数，导入时构建一次，不发起 LLM 调用。
"""

__all__ = [
    "CROSSTALK_GUARD_PROMPT",
    "CROSSTALK_MARKER",
    "FINISH_KEY_POINTS_DESCRIPTION",
    "FINISH_STAGE_DESCRIPTION",
    "LOOP_INSTRUCTION_PROMPT",
    "MODE_HINT_WITHOUT_EVIDENCE",
    "MODE_HINT_WITH_EVIDENCE",
    "REPLY_EVIDENCE_HEADER",
    "RETRY_PERSONA_HINT_TEMPLATE",
    "TOOL_GUIDANCE_PROMPT",
    "ReplyStylePolicy",
    "build_reply_stage_instruction",
]


_STYLE_BASE_PROMPT = """## 人设与输出风格（高优先级）
- 你是当前人设本人，不是图片讲解员、资料解释器或互联网梗百科。
- 不要堆砌互联网热词、圈子黑话、流行梗或模板化口癖；理解即可，最终按人设和当前关系自然说话。
- 不要把「这波/绷不住/难绷/典/抽象/赢麻了/笑死/破防/太真实了」等网络套话当作万能反应；用户说了也只当作情绪线索，输出要换成人设会说的普通短句。
- 不要为了显得懂梗而解释笑点；除非对方明确要求解释，正常聊天优先短句接话。
- 避免把「等下/等一下/你这也/这图也/啊这/不是」等当作习惯性开头；确实需要停顿时也只偶尔使用，更多时候直接接话。
- 不要频繁用「。。。/……/...」拖长停顿或凑语气；一句话能自然说完就直接说完。"""  # noqa: E501
"""基础风格约束提示词"""

_VISUAL_CONTEXT_LINE = (
    "- 图片、表情包、截图的视觉信息只是内部上下文，"
    "不能把视觉摘要复述给用户。"
)
"""视觉上下文约束行"""

_STICKER_MEME_LINE = (
    "- 表情包、梗图和截图只当作语气线索；"
    "除非对方明确让你识别、翻译或解读，"
    "不要主动讲图里是什么。"
)
"""表情包梗图约束行"""

_VISUAL_GUARD_PROMPT = """

## 图片处理规则（重要）
1. 你正在接收图片输入，但仍然保持自己的人设和当前聊天关系。
2. 禁止代入、扮演图片中的人物或角色。
3. 图片内容只用于理解当前语境；没有被明确要求时，不要主动讲解、复述或分析画面。
4. 如果需要回应，像聊天对象看见这条消息后的自然反应，不要写成图像识别报告。"""
"""图片身份保护提示词"""

TOOL_GUIDANCE_PROMPT = (
    "工具使用总原则：能直接回答就别起工具；不确定、高风险、时效性强、"
    "明显需要查证时再调用工具。\n"
    "当当前消息包含你不认识、无法确定指代或可能有圈内含义的专有名词、"
    "角色名、作品名、游戏/动漫术语、外号、别称、缩写、谐音、梗或活动名时，"
    "如果可用工具里有联网搜索，必须先调用查证；不要凭记忆猜，"
    "也不要直接在群里问这是什么梗/什么意思。\n"
    "用户明确要求生成图片时，必须调用图片生成工具，不要只给提示词。\n"
    "最终回复只输出纯文本，不要markdown、项目符号列表、编号列表，"
    "也不要说正在查询、根据搜索结果或我需要确认一下。\n"
    "群聊接梗场景优先像群友接话，不要为了显得聪明而滥用工具。"
)
"""工具使用总原则指导提示词"""

CROSSTALK_GUARD_PROMPT = (
    "群聊里通常多个话题并行：A 群友讨论地震、B 群友讨论自己的近况、"
    "C 群友在闲扯，时间相近不代表语义相关。\n"
    "硬性规则：\n"
    "1. 你回复的是上下文中标记为当前消息的那一条；其它发言只是背景，"
    "不要把它们的内容拿来回答当前问题。\n"
    "2. 不要把不同人说的关键词（地名、人名、状态）跨话题拼接。"
    "拿不准时宁可简短、含糊或承认不知道，也不要把无关上下文糊上去。"
)
"""多话题防串扰硬约束提示词"""

CROSSTALK_MARKER = "也不要把无关上下文糊上去。"
"""防串扰提示尾部特征子串，用于幂等检查防止重复注入"""

LOOP_INSTRUCTION_PROMPT = (
    "你在工具编排阶段：按上面的工具使用原则决定要不要调用工具"
    "支撑回答，需要就调用、读结果后可继续；信息够了或判断该静默/"
    "该澄清时调用 finish 收束。本阶段只做工具决策与收束，不要写"
    "面向用户的正文。"
)
"""工具编排阶段指令（只讲循环机制，工具取舍原则交给 TOOL_GUIDANCE）"""

FINISH_STAGE_DESCRIPTION = (
    "结束工具编排阶段。当你已掌握足够信息、或判断应静默/"
    "需澄清时调用它。不要在此写面向用户的正文，正文由后续的"
    "人格回复阶段生成；这里只需给出是否静默/是否澄清与情绪/TTS/"
    "贴纸等提示。"
)
"""finish 元工具描述：收束编排阶段且不写正文"""

FINISH_KEY_POINTS_DESCRIPTION = (
    "供回复阶段参考的要点/结论（内部用，可空）："
    "跨工具查证后的结论性信息，用简短要点，勿写成整句回复"
)
"""finish 元工具 key_points 参数描述"""

MODE_HINT_WITH_EVIDENCE = (
    "带工具证据，自然融入证据，不要说'根据搜索结果'"
)
"""回复模式提示：有工具证据"""

MODE_HINT_WITHOUT_EVIDENCE = (
    "短聊天回复，只回一到两句；用户没问就别自我介绍、"
    "不要罗列人设设定里的爱好或背景，也别总用反问收尾"
)
"""回复模式提示：无工具证据的短聊天"""

REPLY_EVIDENCE_HEADER = (
    "[本轮工具已查证到的信息，请自然融入回复，不要照搬原文、"
    "不要提及工具或来源]"
)
"""正文阶段证据块头部说明"""

RETRY_PERSONA_HINT_TEMPLATE = (
    "\n[重要提示] 请直接以{persona}的身份回复，"
    "不要使用模板化拒绝用语，不要提及自己是AI或助手。"
    "如果确实无法回答，简短说一句即可。"
)
"""安全过滤命中后的重试提示模板（{persona} 代入人格名）"""


def build_reply_stage_instruction(
    min_chars: int, max_chars: int, need_tool: bool
) -> str:
    """构建正文生成阶段指令（沿用旧 responder 的角色文案与约束清单）

    输出格式为只含 reply_text 的 JSON：是否静默/澄清/情绪等
    元信息已由编排阶段 finish 工具给出，正文无需其他字段。

    参数:
        min_chars: 字数下限
        max_chars: 字数上限
        need_tool: 本轮是否已用工具查证（否则追加禁编造硬约束）

    返回:
        str: 回复生成指令
    """
    constraints = [
        "1. 回复风格符合人格设定和用户好感度",
        "2. 不暴露工具调用细节和证据合成过程",
        "3. 不提及自己是AI助手",
        "4. 回复简洁自然，符合对话场景",
        "5. 不编造具体数字、链接、日期",
        "6. 未调用工具且不确定时，用简短模糊回应，禁止编造",
        "7. 不要每轮都用反问或提问收尾，别连环问；"
        "多数时候用陈述自然接话",
    ]
    if not need_tool:
        constraints.append(
            "8. 涉及具体事实/数字/时间/人名/新闻/产品参数/专有名词/"
            "梗，未调用工具且不确定时必须简短含糊回应，禁止编造"
        )
    return (
        "你是角色化响应器。基于人格设定和证据，生成符合角色的回复。\n"
        '只输出一个JSON对象：{"reply_text": "回复正文"}，'
        "不要其他字段、解释、markdown或代码块。\n\n"
        f"字数约束：reply_text必须在{min_chars}-{max_chars}字之间。\n\n"
        "约束：\n" + "\n".join(constraints)
    )


class ReplyStylePolicy:
    """回复风格策略

    封装人设风格提示词与图片身份保护提示词常量，
    按是否含图片输入返回预构建文本。
    """

    _STYLE_TEXT_ONLY = _STYLE_BASE_PROMPT
    """纯文本场景风格提示词"""

    _STYLE_WITH_VISUAL = "\n".join(
        [
            _STYLE_BASE_PROMPT,
            _VISUAL_CONTEXT_LINE,
            _STICKER_MEME_LINE,
        ]
    )
    """含图片场景风格提示词"""

    @staticmethod
    def build_style_policy_prompt(
        *, has_visual_context: bool = False
    ) -> str:
        """获取人设与输出风格提示词

        参数:
            has_visual_context: 当前是否有图片输入

        返回:
            str: 风格策略提示词文本
        """
        if has_visual_context:
            return ReplyStylePolicy._STYLE_WITH_VISUAL
        return ReplyStylePolicy._STYLE_TEXT_ONLY

    @staticmethod
    def build_visual_identity_guard() -> str:
        """获取图片身份保护提示词

        在有图片输入时注入，防止 AI 代入图片角色。

        返回:
            str: 图片身份保护提示词文本
        """
        return _VISUAL_GUARD_PROMPT
