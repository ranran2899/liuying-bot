"""ACG作品与角色检索实现

群聊里的番剧、游戏角色、梗图出处这类问题，通用检索召回噪声大。
本技能按查询类型定向拼装检索关键词，提升召回精度。
"""

from typing import Any

from liuying.liuying_plugins.AI.tools import AgentTool

_MAX_RESULTS = 4
"""检索结果条数"""

_SNIPPET_LIMIT = 180
"""单条摘要截断长度"""

_KIND_KEYWORDS: dict[str, str] = {
    "anime": "动画 番剧 剧情 简介 播出",
    "character": "角色 出自 作品 声优 设定",
    "game": "游戏 角色 剧情 玩法",
    "manga": "漫画 剧情 简介 作者",
    "auto": "动画 游戏 角色 出自 作品",
}
"""查询类型到检索补充词的映射"""

_DEFAULT_KIND = "auto"
"""默认查询类型，无法判断时用综合关键词"""


def build_keyword(name: str, kind: str = _DEFAULT_KIND) -> str:
    """拼装定向检索关键词

    参数:
        name: 作品名或角色名
        kind: 查询类型 anime/character/game/manga/auto

    返回:
        str: 检索关键词
    """
    suffix = _KIND_KEYWORDS.get(
        kind, _KIND_KEYWORDS[_DEFAULT_KIND]
    )
    return f"{name.strip()} {suffix}"


async def resolve(
    name: str,
    kind: str = _DEFAULT_KIND,
    llm_helper: Any = None,
) -> str:
    """检索ACG作品或角色信息

    参数:
        name: 作品名或角色名
        kind: 查询类型
        llm_helper: LLM助手实例

    返回:
        str: 检索结果文本
    """
    if llm_helper is None:
        return "ACG检索不可用：未配置LLM助手"
    target = (name or "").strip()
    if not target:
        return "请提供作品名或角色名"

    keyword = build_keyword(target, kind)
    # 外部检索失败需降级为可读提示，避免中断 Agent 循环。
    try:
        results = await llm_helper.web_search(
            keyword, count=_MAX_RESULTS
        )
    except Exception as e:
        return f"ACG检索失败: {e}"

    if not results:
        return f"未检索到「{target}」的相关资料"

    lines = [f"「{target}」相关资料："]
    for item in results:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        snippet = (
            item.get("snippet") or item.get("content") or ""
        ).strip()
        if len(snippet) > _SNIPPET_LIMIT:
            snippet = f"{snippet[:_SNIPPET_LIMIT]}..."
        if title:
            lines.append(f"- {title}")
        if snippet:
            lines.append(f"  {snippet}")
    return "\n".join(lines)


def build_acg_tool(runtime: Any) -> AgentTool:
    """构建ACG检索工具

    参数:
        runtime: SkillRuntime 实例

    返回:
        AgentTool: ACG检索工具
    """
    llm_helper = getattr(runtime, "llm_helper", None)

    async def _handler(
        name: str, kind: str = _DEFAULT_KIND
    ) -> str:
        """ACG检索handler

        参数:
            name: 作品名或角色名
            kind: 查询类型

        返回:
            str: 检索结果
        """
        return await resolve(
            name=name, kind=kind, llm_helper=llm_helper
        )

    return AgentTool(
        name="resolve_acg",
        description=(
            "查询动画、漫画、游戏的作品或角色信息，"
            "包括角色出自哪部作品、剧情简介、声优。"
            "ACG 相关提问优先用本工具而非 web_search"
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "作品名或角色名",
                },
                "kind": {
                    "type": "string",
                    "enum": list(_KIND_KEYWORDS),
                    "description": (
                        "查询类型：anime动画 character角色 "
                        "game游戏 manga漫画 auto综合，默认auto"
                    ),
                },
            },
            "required": ["name"],
        },
        func=_handler,
    )
