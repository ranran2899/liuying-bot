"""群组类内置工具

群成员列表 + 成员详情 + 成员模糊查找。

群组上下文（group_id）由会话 contextvar 提供，工具自行读取，
不作为 LLM 参数暴露。
"""

from liuying.utils.log import logger

from ...agent.runtime.session_context import get_current_group_id
from ...core.group import group_member_service
from ..decorators import register_tool


@register_tool(
    name="get_group_members",
    description=(
        "查询当前群组的成员列表（含昵称/角色），"
        "适用于需要了解群成员构成、@特定成员、"
        "或分析群组氛围时"
    ),
    parameters={
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "返回数量上限，默认50",
                "default": 50,
            },
        },
        "required": [],
    },
)
async def get_group_members(limit: int = 50) -> str:
    """查询当前群成员列表

    参数:
        limit: 返回数量上限，默认50

    返回:
        str: 群成员列表文本
    """
    group_id = get_current_group_id()
    if not group_id:
        return "当前不在群聊中，无法查询群成员"

    try:
        snapshot = await group_member_service.get_members(group_id)
        if snapshot.total == 0:
            return f"群 {group_id} 暂无成员信息"
        lines: list[str] = [f"群 {group_id} 成员总数: {snapshot.total}"]
        for m in snapshot.members[:limit]:
            role_tag = f"[{m.role}]" if m.role != "member" else ""
            lines.append(f"- {m.display_name()}({m.user_id}){role_tag}")
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"查询群成员失败: {e}", command="AI", e=e)
        return f"查询群成员失败: {type(e).__name__}"


@register_tool(
    name="get_group_member_info",
    description=(
        "查询单个群成员的详细信息（昵称/角色/入群时间），"
        "适用于需要了解特定成员、判断管理员身份时"
    ),
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "目标用户ID",
            },
        },
        "required": ["user_id"],
    },
)
async def get_group_member_info(user_id: str) -> str:
    """查询当前群中指定成员信息

    参数:
        user_id: 目标用户ID

    返回:
        str: 成员信息文本
    """
    group_id = get_current_group_id()
    if not group_id:
        return "当前不在群聊中，无法查询成员信息"

    try:
        member = await group_member_service.get_member(group_id, user_id)
        if not member:
            return f"未找到用户 {user_id} 在群 {group_id}"
        info = member.to_full()
        lines = [
            f"用户ID: {info['user_id']}",
            f"昵称: {info['user_name']}",
            f"自定义名称: {info['user_nickname']}",
            f"角色: {info['role']}",
            f"入群时间: {info.get('join_time', '')}",
        ]
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"查询群成员信息失败: {e}", command="AI", e=e)
        return f"查询群成员信息失败: {type(e).__name__}"


@register_tool(
    name="find_group_member",
    description=(
        "按名称关键词模糊查找当前群的成员，"
        "适用于用户提到某人但只知道名字时"
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "名称关键词",
            },
        },
        "required": ["name"],
    },
)
async def find_group_member(name: str) -> str:
    """按名称模糊查找当前群成员

    参数:
        name: 名称关键词

    返回:
        str: 匹配结果文本
    """
    group_id = get_current_group_id()
    if not group_id:
        return "当前不在群聊中，无法查找成员"

    try:
        members = await group_member_service.find_members_by_name(
            group_id, name, limit=10
        )
        if not members:
            return f"未找到匹配 '{name}' 的群成员"
        lines = [f"匹配 '{name}' 的群成员:"]
        for m in members:
            lines.append(
                f"- {m.display_name()}({m.user_id}) [{m.role}]"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"查找群成员失败: {e}", command="AI", e=e)
        return f"查找群成员失败: {type(e).__name__}"
