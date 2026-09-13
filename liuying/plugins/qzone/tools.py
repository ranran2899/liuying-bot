"""QZone Agent 工具函数

定义供 AI Agent 调用的 QZone 工具函数（发说说/拉取动态/点赞）。
通过 PluginExtraData.smart_tools 声明，由 AI 插件 SmartToolBridge 自动注册。
不直接导入 AI 插件的任何模块。
"""

from .service import qzone_service

__all__ = ["qzone_publish", "qzone_feeds", "qzone_like"]


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
