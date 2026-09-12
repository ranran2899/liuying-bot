"""排查 smart_tools 注册问题的临时脚本：加载所有插件后检查 ban 插件的元数据与注册结果"""

import sys

sys.argv = ["bot.py"]

import nonebot  # noqa: E402

from liuying.liuying_plugins.AI.tools.external import smart_tool_bridge  # noqa: E402
from liuying.liuying_plugins.AI.tools.registry import tool_registry  # noqa: E402

plugins = nonebot.get_loaded_plugins()
print(f"== 已加载插件数: {len(plugins)}")

for plugin in plugins:
    meta = plugin.metadata
    if not meta or not meta.extra:
        continue
    extra = meta.extra
    if isinstance(extra, dict) and "smart_tools" in extra:
        tools = extra["smart_tools"]
        print(f"插件 {plugin.name} 声明 smart_tools={len(tools)}")
        for t in tools:
            print(f"    tag={t!r}")
            if hasattr(t, "func"):
                print(f"    func={t.func}")
    elif hasattr(extra, "model_dump"):
        try:
            d = extra.model_dump()
            if "smart_tools" in d:
                print(f"插件 {plugin.name}(pydantic) smart_tools={len(d['smart_tools'])}")
        except Exception as e:
            print(f"插件 {plugin.name} extra dump 失败: {e}")

ban_plugins = [p for p in plugins if "ban" in (p.name or "")]
print(f"== 含 ban 的插件: {[p.name for p in ban_plugins]}")

count = smart_tool_bridge.register_all()
print(f"== register_all 注册数: {count}")
for name in ("ban_user", "unban_user", "query_bot_help"):
    t = tool_registry.get(name)
    print(f"    {name}: {'已注册' if t else '未注册'}")