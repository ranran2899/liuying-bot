"""群组类内置工具

群成员列表 + 成员详情 + 成员模糊查找。
"""

import nonebot

from ....core.group import group_member_service
from ...runtime.constants import (
    EVIDENCE_KIND_CONTEXT,
    INTENT_TAG_LOCAL,
    LATENCY_CLASS_FAST,
)
from ..decorators import register_tool


@register_tool(
    name="get_group_members",
    description=(
        "查询指定群组的成员列表（含昵称/角色），"
        "适用于需要了解群成员构成、@特定成员、"
        "或分析群组氛围时"
    ),
    parameters={
        "type": "object",
        "properties": {
            "group_id": {
                "type": "string",
                "description": "群组ID",
            },
            "limit": {
                "type": "integer",
                "description": "返回数量上限，默认50",
                "default": 50,
            },
        },
        "required": ["group_id"],
    },
    intent_tags=[INTENT_TAG_LOCAL],
    latency_class=LATENCY_CLASS_FAST,
    evidence_kind=EVIDENCE_KIND_CONTEXT,
    metadata={"requires_bot": True},
)
async def get_group_members(
    group_id: str, limit: int = 50
) -> str:
    """查询群成员列表

    参数:
        group_id: 群组ID
        limit: 返回数量上限，默认50

    返回:
        str: 群成员列表文本
    """
    try:
        bot = nonebot.get_bot()
    except Exception:
        bot = None

    try:
        snapshot = await group_member_service.get_members(
            group_id, bot=bot
        )
        if snapshot.total == 0:
            return f"群 {group_id} 暂无成员信息"
        lines: list[str] = [
            f"群 {group_id} 成员总数: {snapshot.total}"
            f"（来源: {snapshot.source}）"
        ]
        for m in snapshot.members[:limit]:
            name = m.nickname or m.username or m.user_id
            role_tag = (
                f"[{m.role}]" if m.role != "member" else ""
            )
            lines.append(f"- {name}({m.user_id}){role_tag}")
        return "\n".join(lines)
    except Exception as e:
        return f"查询群成员失败: {e}"


@register_tool(
    name="get_group_member_info",
    description=(
        "查询单个群成员的详细信息（昵称/角色/入群时间），"
        "适用于需要了解特定成员、判断管理员身份时"
    ),
    parameters={
        "type": "object",
        "properties": {
            "group_id": {
                "type": "string",
                "description": "群组ID",
            },
            "user_id": {
                "type": "string",
                "description": "用户ID",
            },
        },
        "required": ["group_id", "user_id"],
    },
    intent_tags=[INTENT_TAG_LOCAL],
    latency_class=LATENCY_CLASS_FAST,
    evidence_kind=EVIDENCE_KIND_CONTEXT,
    metadata={"requires_bot": True},
)
async def get_group_member_info(
    group_id: str, user_id: str
) -> str:
    """查询单个群成员信息

    参数:
        group_id: 群组ID
        user_id: 用户ID

    返回:
        str: 成员信息文本
    """
    try:
        bot = nonebot.get_bot()
    except Exception:
        bot = None

    try:
        member = (
            await group_member_service.get_member(
                group_id, user_id, bot=bot
            )
        )
        if not member:
            return f"未找到用户 {user_id} 在群 {group_id}"
        info = member.to_full()
        lines = [
            f"用户ID: {info['user_id']}",
            f"昵称: {info['nickname']}",
            f"用户名: {info.get('username', '')}",
            f"角色: {info['role']}",
            f"入群时间: {info.get('join_time', '')}",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"查询群成员信息失败: {e}"


@register_tool(
    name="find_group_member",
    description=(
        "按名称关键词模糊查找群成员，"
        "适用于用户提到某人但只知道名字时"
    ),
    parameters={
        "type": "object",
        "properties": {
            "group_id": {
                "type": "string",
                "description": "群组ID",
            },
            "name": {
                "type": "string",
                "description": "名称关键词",
            },
        },
        "required": ["group_id", "name"],
    },
    intent_tags=[INTENT_TAG_LOCAL],
    latency_class=LATENCY_CLASS_FAST,
    evidence_kind=EVIDENCE_KIND_CONTEXT,
    metadata={"requires_bot": True},
)
async def find_group_member(group_id: str, name: str) -> str:
    """按名称模糊查找群成员

    参数:
        group_id: 群组ID
        name: 名称关键词

    返回:
        str: 匹配结果文本
    """
    try:
        bot = nonebot.get_bot()
    except Exception:
        bot = None

    try:
        members = (
            await group_member_service.find_members_by_name(
                group_id, name, bot=bot, limit=10
            )
        )
        if not members:
            return f"未找到匹配 '{name}' 的群成员"
        lines = [f"匹配 '{name}' 的群成员:"]
        for m in members:
            name_str = m.nickname or m.username or m.user_id
            lines.append(
                f"- {name_str}({m.user_id}) "
                f"[{m.role}]"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"查找群成员失败: {e}"
