"""视觉能力诊断实现

把 core/vision 的 VisionCapabilityRouter 暴露成 Agent 工具，
用于回答「你能看图吗」这类能力自述问题，以及在图片分析
反复失败时给出可读的原因定位。

本技能只做能力探测与路由自述，具体看图分析在 vision_analyze。
"""

import asyncio
from typing import Any

from liuying.liuying_plugins.AI.core.vision import vision_router
from liuying.liuying_plugins.AI.tools import AgentTool

_ROUTE_TIMEOUT = 20.0
"""能力探测超时（秒），探测可能触发一次真实的模型请求"""

_METHOD_LABELS = {
    "keyword": "模型名关键词匹配",
    "probe": "真实请求探测",
    "config": "配置显式声明",
}
"""探测方式的中文标签"""


def format_route(route: Any, summary: dict[str, Any]) -> str:
    """把路由结果与能力摘要格式化为可读文本

    参数:
        route: VisionRouteResult 实例
        summary: get_capability_summary 返回的摘要字典

    返回:
        str: 中文能力描述
    """
    if not route.success:
        reason = route.fallback_reason or "未找到支持视觉的模型"
        cached = summary.get("cached_probes", 0)
        return (
            f"当前不具备看图能力：{reason}。"
            f"（已探测{cached}个模型配置）"
        )

    lines = [
        f"具备看图能力，当前走 {route.provider}/{route.model}。"
    ]
    info = route.info
    if info is not None:
        method = _METHOD_LABELS.get(
            info.detection_method, info.detection_method
        )
        lines.append(
            f"判定方式：{method}，置信度{info.confidence:.0%}。"
        )
    if route.fallback_used:
        lines.append(
            f"注意：正在使用降级通道（{route.fallback_reason}），"
            "识别质量可能下降。"
        )
    if preferred := summary.get("preferred_model"):
        lines.append(f"首选视觉模型：{preferred}。")
    return "".join(lines)


async def check_capability(
    prefer_model: str = "",
) -> str:
    """探测并汇报当前视觉能力

    参数:
        prefer_model: 优先尝试的模型名，留空按默认顺序探测

    返回:
        str: 中文能力描述
    """
    # 探测会发起真实模型请求，属外部不确定依赖，超时与异常降级为文本。
    try:
        async with asyncio.timeout(_ROUTE_TIMEOUT):
            route = await vision_router.route_vision_request(
                prefer_model=(prefer_model or "").strip() or None
            )
    except TimeoutError:
        return "视觉能力探测超时，暂时无法确认是否能看图"
    except Exception as e:
        return f"视觉能力探测失败：{type(e).__name__}"

    summary = vision_router.get_capability_summary()
    return format_route(route, summary)


def build_caller_tools(runtime: Any) -> list[AgentTool]:
    """构建视觉能力诊断工具集

    参数:
        runtime: SkillRuntime 实例

    返回:
        list[AgentTool]: 工具列表
    """
    del runtime  # 本技能只依赖 vision_router 单例，无需注入服务

    async def _handler(prefer_model: str = "") -> str:
        """能力探测handler

        参数:
            prefer_model: 优先尝试的模型名

        返回:
            str: 能力描述
        """
        return await check_capability(prefer_model=prefer_model)

    return [
        AgentTool(
            name="vision_capability",
            description=(
                "查询自己当前是否能看图、走的是哪个视觉模型。"
                "用户问「你能看图吗」「你的眼睛好了吗」，"
                "或图片分析连续失败需要说明原因时用本工具。"
                "不要用它来分析具体图片"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "prefer_model": {
                        "type": "string",
                        "description": (
                            "优先探测的模型名；"
                            "一般留空按默认顺序探测"
                        ),
                    }
                },
                "required": [],
            },
            func=_handler,
        )
    ]
