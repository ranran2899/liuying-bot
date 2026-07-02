"""知识库辅助提取函数

提供从插件 extra 字典中提取命令、AI工具、别名等信息的纯函数，
以及关键词构建与文本分词工具。所有函数均不依赖实例状态，
可被 PluginView 等类复用。
"""

import re
from typing import Any

_DEFAULT_KEYWORD_STOPWORDS: set[str] = {
    "的", "了", "是", "在", "我", "你", "他", "她", "它",
    "请", "帮", "能", "可以", "吗", "么", "啊", "呢", "吧",
    "一下", "帮我", "请问", "怎么", "如何", "什么", "为什么",
    "the", "a", "an", "is", "are", "to", "of",
}
"""关键词停用词集合（高频无意义词）"""


def _safe_str(value: Any, default: str = "") -> str:
    """安全转字符串

    参数:
        value: 原始值
        default: 默认值

    返回:
        str: 字符串
    """
    if value is None:
        return default
    try:
        return str(value)
    except Exception:
        return default


def _extract_commands(extra: dict[str, Any]) -> list[dict[str, Any]]:
    """从extra字典提取命令列表

    参数:
        extra: extra字典

    返回:
        list[dict]: 命令字典列表
    """
    raw = extra.get("commands") or []
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            cmd: dict[str, Any] = {
                "command": _safe_str(item.get("command", "")),
                "params": list(item.get("params") or []),
                "description": _safe_str(item.get("description", "")),
            }
            examples_raw = item.get("examples") or []
            examples: list[dict[str, str]] = []
            if isinstance(examples_raw, list):
                for ex in examples_raw:
                    if isinstance(ex, dict):
                        examples.append(
                            {
                                "exec": _safe_str(ex.get("exec", "")),
                                "description": _safe_str(
                                    ex.get("description", "")
                                ),
                            }
                        )
                    elif isinstance(ex, str):
                        examples.append({"exec": ex, "description": ""})
            cmd["examples"] = examples
            result.append(cmd)
    return result


def _extract_smart_tools(extra: dict[str, Any]) -> list[dict[str, Any]]:
    """从extra字典提取AI工具标签

    参数:
        extra: extra字典

    返回:
        list[dict]: 工具标签字典列表
    """
    raw = extra.get("smart_tools") or []
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            tool: dict[str, Any] = {
                "name": _safe_str(item.get("name", "")),
                "description": _safe_str(item.get("description", "")),
            }
            params = item.get("parameters")
            if isinstance(params, dict):
                tool["parameters"] = {
                    "type": _safe_str(params.get("type", "object")),
                    "required": list(params.get("required") or []),
                    "properties": dict(params.get("properties") or {}),
                }
            else:
                tool["parameters"] = None
            result.append(tool)
    return result


def _extract_aliases(extra: dict[str, Any]) -> list[str]:
    """从extra字典提取别名

    参数:
        extra: extra字典

    返回:
        list[str]: 别名列表
    """
    raw = extra.get("aliases") or []
    if isinstance(raw, list):
        return [_safe_str(a) for a in raw if a]
    if isinstance(raw, set):
        return [_safe_str(a) for a in raw if a]
    return []


def _build_keywords(
    display_name: str,
    description: str,
    commands: list[dict[str, Any]],
    aliases: list[str],
    menu_type: str,
) -> str:
    """构建检索关键词（空格分隔）

    参数:
        display_name: 显示名
        description: 描述
        commands: 命令列表
        aliases: 别名列表
        menu_type: 菜单类型

    返回:
        str: 关键词字符串（空格分隔）
    """
    parts: list[str] = []
    if display_name:
        parts.append(display_name)
    if menu_type:
        parts.append(menu_type)
    if aliases:
        parts.extend(aliases)

    for cmd in commands:
        cmd_text = cmd.get("command", "")
        if cmd_text:
            parts.append(cmd_text)
        for ex in cmd.get("examples", []):
            ex_text = ex.get("exec", "")
            if ex_text:
                parts.append(ex_text)

    if description:
        cleaned = re.sub(r"[^\w\u4e00-\u9fa5]+", " ", description)
        parts.extend(t for t in cleaned.split() if len(t) >= 2)

    seen: set[str] = set()
    unique: list[str] = []
    for p in parts:
        p = p.strip()
        if p and p not in seen:
            seen.add(p)
            unique.append(p)
    return " ".join(unique)[:1000]


def _tokenize(text: str) -> list[str]:
    """分词（简化的中英文混合分词）

    参数:
        text: 输入文本

    返回:
        list[str]: 分词后的token列表（去停用词、去重）
    """
    if not text:
        return []
    cleaned = re.sub(r"[^\w\u4e00-\u9fa5]+", " ", text)
    tokens: list[str] = []
    seen: set[str] = set()

    for raw in cleaned.split():
        token = raw.strip().lower()
        if not token or token in _DEFAULT_KEYWORD_STOPWORDS:
            continue
        if len(token) < 2 and not token.isascii():
            continue
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)

    for i in range(len(cleaned)):
        ch = cleaned[i]
        if "\u4e00" <= ch <= "\u9fa5":
            for length in (2, 3, 4):
                end = i + length
                if end > len(cleaned):
                    break
                piece = cleaned[i:end]
                if any(
                    not ("\u4e00" <= c <= "\u9fa5") for c in piece
                ):
                    continue
                token = piece.lower()
                if (
                    token in _DEFAULT_KEYWORD_STOPWORDS
                    or token in seen
                ):
                    continue
                seen.add(token)
                tokens.append(token)
    return tokens
