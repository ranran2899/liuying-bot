"""QZone Agent 工具注册

通过流萤AI插件公开API register_external_tool 注册 QZone 工具，
供 AI Agent 调用发说说/拉取动态/点赞。

依赖：流萤AI插件（liuying_plugins.AI）必须先加载完成。
本插件优先级=3，晚于AI插件（priority=2），确保 tool_registry 就绪。
"""

from liuying.liuying_plugins.AI import register_external_tool
from liuying.liuying_plugins.AI.agent.runtime.constants import (
    INTENT_TAG_ADMIN,
    INTENT_TAG_NETWORK,
    INTENT_TAG_REALTIME,
    LATENCY_CLASS_NETWORK,
)

from .service import qzone_service


@register_external_tool(
    name="qzone_publish",
    description=(
        "发布QQ空间说说（需管理员预先配置QZone cookie），"
        "适用于自己主动发表心情/动态/想法时"
    ),
    parameters={
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "说说正文内容",
            },
            "visible": {
                "type": "integer",
                "description": "可见性：0=公开 1=好友 2=私密",
                "default": 0,
            },
        },
        "required": ["content"],
    },
    intent_tags=[INTENT_TAG_ADMIN, INTENT_TAG_NETWORK],
    latency_class=LATENCY_CLASS_NETWORK,
    requires_network=True,
    metadata={
        "requires_admin": True,
        "output_kind": "qzone_publish_result",
    },
)
async def qzone_publish(content: str, visible: int = 0) -> str:
    """发布QQ空间说说

    参数:
        content: 说说内容
        visible: 可见性（0=公开 1=好友 2=私密）

    返回:
        str: 操作结果文本
    """
    if not qzone_service.enabled:
        return "QZone未启用或cookie未配置，无法发布"
    ok, msg = await qzone_service.publish_shuo(
        content, visible=visible
    )
    return f"发布{'成功' if ok else '失败'}: {msg}"


@register_external_tool(
    name="qzone_feeds",
    description=(
        "拉取QQ空间好友动态列表，"
        "返回结果中每条动态都会标明 feed_id 和 owner_uin，"
        "供 qzone_like 等工具使用"
    ),
    parameters={
        "type": "object",
        "properties": {
            "count": {
                "type": "integer",
                "description": "拉取数量，默认10，最大20",
                "default": 10,
            },
        },
    },
    intent_tags=[INTENT_TAG_NETWORK, INTENT_TAG_REALTIME],
    latency_class=LATENCY_CLASS_NETWORK,
    requires_network=True,
    metadata={
        "requires_admin": True,
        "output_kind": "qzone_feeds",
    },
)
async def qzone_feeds(count: int = 10) -> str:
    """拉取QQ空间动态列表

    参数:
        count: 拉取数量，默认10，最大20

    返回:
        str: 动态摘要文本
    """
    if not qzone_service.enabled:
        return "QZone未启用或cookie未配置"
    feeds = await qzone_service.fetch_feeds(
        count=min(max(count, 1), 20)
    )
    if not feeds:
        return "未拉取到动态"

    lines: list[str] = []
    for i, feed in enumerate(feeds, 1):
        feed_id = (
            feed.get("tid")
            or feed.get("feed_id")
            or feed.get("id")
            or feed.get("cellid")
            or ""
        )
        owner_uin = (
            feed.get("uin")
            or feed.get("hostuin")
            or feed.get("host_uin")
            or feed.get("owner_uin")
            or ""
        )
        nickname = (
            feed.get("nickname")
            or feed.get("name")
            or feed.get("nick")
            or owner_uin
        )
        content = (
            feed.get("content")
            or feed.get("con")
            or feed.get("summary")
            or ""
        )[:80]
        create_time = (
            feed.get("createTime")
            or feed.get("created_time")
            or feed.get("abstime")
            or ""
        )
        lines.append(
            f"{i}. [feed_id={feed_id} owner_uin={owner_uin}] "
            f"{nickname}: {content} ({create_time})"
        )
    return "\n".join(lines)


@register_external_tool(
    name="qzone_like",
    description=(
        "对指定QQ空间动态点赞，"
        "feed_id 和 owner_uin 必须从 qzone_feeds 返回结果中对应字段提取，"
        "适用于自己表达对好友动态的支持时"
    ),
    parameters={
        "type": "object",
        "properties": {
            "feed_id": {
                "type": "string",
                "description": "动态ID，从 qzone_feeds 结果中的 feed_id 字段获取",
            },
            "owner_uin": {
                "type": "string",
                "description": (
                    "动态所有者QQ号，"
                    "从 qzone_feeds 结果中的 owner_uin 字段获取"
                ),
            },
        },
        "required": ["feed_id", "owner_uin"],
    },
    intent_tags=[INTENT_TAG_NETWORK, INTENT_TAG_ADMIN],
    latency_class=LATENCY_CLASS_NETWORK,
    requires_network=True,
    metadata={
        "requires_admin": True,
        "output_kind": "qzone_like_result",
    },
)
async def qzone_like(feed_id: str, owner_uin: str) -> str:
    """点赞QQ空间动态

    参数:
        feed_id: 动态ID
        owner_uin: 动态所有者QQ号

    返回:
        str: 操作结果文本
    """
    if not qzone_service.enabled:
        return "QZone未启用或cookie未配置"
    ok = await qzone_service.like_feed(feed_id, owner_uin)
    return f"点赞{'成功' if ok else '失败'}: feed={feed_id}"
