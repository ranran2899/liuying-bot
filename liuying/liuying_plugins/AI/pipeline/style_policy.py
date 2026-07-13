"""回复风格策略

构建人设与输出风格提示词，防止 AI 堆砌网络热词、圈子黑话、
流行梗或模板化口癖。同时提供图片身份保护，避免 AI 代入图片角色。

所有方法返回提示词文本字符串，不发起 LLM 调用。
"""

__all__ = ["ReplyStylePolicy"]


class ReplyStylePolicy:
    """回复风格策略

    封装人设风格提示词与图片身份保护提示词的构建逻辑。
    所有方法均为静态方法，可直接通过类名调用。

    风格约束范围：
    - 禁止堆砌互联网热词（绷不住/典/赢麻了等）
    - 禁止模板化口癖（等下/啊这/不是等）
    - 禁止过度省略号拖长停顿
    - 禁止解释笑点（除非明确要求）
    - 图片视觉信息仅作内部上下文，不复述给用户
    - 禁止代入/扮演图片中的人物角色
    """

    _STYLE_BASE_PROMPT: str = """## 人设与输出风格（高优先级）
- 你是当前人设本人，不是图片讲解员、资料解释器或互联网梗百科。
- 不要堆砌互联网热词、圈子黑话、流行梗或模板化口癖；理解即可，最终按人设和当前关系自然说话。
- 不要把「这波/绷不住/难绷/典/抽象/赢麻了/笑死/破防/太真实了」等网络套话当作万能反应；用户说了也只当作情绪线索，输出要换成人设会说的普通短句。
- 不要为了显得懂梗而解释笑点；除非对方明确要求解释，正常聊天优先短句接话。
- 避免把「等下/等一下/你这也/这图也/啊这/不是」等当作习惯性开头；确实需要停顿时也只偶尔使用，更多时候直接接话。
- 不要频繁用「。。。/……/...」拖长停顿或凑语气；一句话能自然说完就直接说完。"""  # noqa: E501
    """基础风格约束提示词"""

    _VISUAL_CONTEXT_LINE: str = (
        "- 图片、表情包、截图的视觉信息只是内部上下文，"
        "不能把视觉摘要复述给用户。"
    )
    """视觉上下文约束行"""

    _PHOTO_LIKE_LINE: str = (
        "- 真实照片可以自然回应氛围或情绪，"
        "但不要写成列清单式画面描述。"
    )
    """真实照片约束行"""

    _STICKER_MEME_LINE: str = (
        "- 表情包、梗图和截图只当作语气线索；"
        "除非对方明确让你识别、翻译或解读，"
        "不要主动讲图里是什么。"
    )
    """表情包梗图约束行"""

    _VISUAL_GUARD_PROMPT: str = """

## 图片处理规则（重要）
1. 你正在接收图片输入，但仍然保持自己的人设和当前聊天关系。
2. 禁止代入、扮演图片中的人物或角色。
3. 图片内容只用于理解当前语境；没有被明确要求时，不要主动讲解、复述或分析画面。
4. 如果需要回应，像聊天对象看见这条消息后的自然反应，不要写成图像识别报告。"""
    """图片身份保护提示词"""

    @staticmethod
    def build_style_policy_prompt(
        *,
        has_visual_context: bool = False,
        photo_like: bool = False,
    ) -> str:
        """构建人设与输出风格提示词

        参数:
            has_visual_context: 当前是否有图片输入
            photo_like: 图片是否为真实照片

        返回:
            str: 风格策略提示词文本
        """
        lines = [ReplyStylePolicy._STYLE_BASE_PROMPT]
        if has_visual_context:
            lines.append(ReplyStylePolicy._VISUAL_CONTEXT_LINE)
            if photo_like:
                lines.append(ReplyStylePolicy._PHOTO_LIKE_LINE)
            else:
                lines.append(ReplyStylePolicy._STICKER_MEME_LINE)
        return "\n".join(lines)

    @staticmethod
    def build_visual_identity_guard() -> str:
        """构建图片身份保护提示词

        在有图片输入时注入，防止 AI 代入图片角色。

        返回:
            str: 图片身份保护提示词文本
        """
        return ReplyStylePolicy._VISUAL_GUARD_PROMPT
