"""JSON解析工具

提供LLM响应JSON提取与修复能力，支持四重兜底解析。
作为 core 层公共工具，供 agent 与 core 子包共用，避免 core 反向依赖 agent。
"""

import json
import re
from typing import Any


def _repair_unquoted_json_values(text: str) -> str:
    """修复JSON中未加引号的字符串值

    LLM有时会输出 `"key": friendly` 这类未加引号的枚举值，
    导致标准 json.loads 解析失败。本函数在保持 true/false/null
    及数字不变的前提下，为纯标识符值补上加引号。

    参数:
        text: 待修复的JSON文本

    返回:
        str: 修复后的文本
    """

    def _quote_value(match: re.Match) -> str:
        """单条键值修复回调"""
        key = match.group(1)
        value = match.group(2)
        lowered = value.lower()
        if lowered in ("true", "false", "null"):
            return match.group(0)
        if re.fullmatch(
            r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", value
        ):
            return match.group(0)
        return f'"{key}": "{value}"'

    # 匹配 "key": identifier 且后跟逗号/}/]
    pattern = r'"([^"]+)"\s*:\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(?=[,}\]])'
    return re.sub(pattern, _quote_value, text)


def extract_json_payload(raw: str) -> dict[str, Any] | None:
    """从LLM响应文本中提取JSON对象（四重兜底）

    解析顺序：
    1. 直接 json.loads
    2. 去除 markdown fence 后再解析
    3. 修复未加引号的枚举值后再解析
    4. 正则提取首个 {...} 块再解析

    参数:
        raw: LLM响应原始文本

    返回:
        dict[str, Any] | None: 解析出的字典，失败返回None
    """
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text).rstrip("`").strip()
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            pass
    repaired = _repair_unquoted_json_values(text)
    try:
        parsed = json.loads(repaired)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except Exception:
        # 即使正则提取的块解析失败，也尝试修复一次
        repaired_block = _repair_unquoted_json_values(
            match.group(0)
        )
        try:
            parsed = json.loads(repaired_block)
        except Exception:
            return None
    return parsed if isinstance(parsed, dict) else None
