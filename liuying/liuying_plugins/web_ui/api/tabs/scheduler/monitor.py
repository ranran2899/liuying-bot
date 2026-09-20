"""定时任务监控接口

对接 ``liuying.services.apscheduler`` 的任务仓库、指标收集器与告警配置：
- REST ``GET /scheduler/get_status``：单次拉取监控快照
- WS   ``/liuying/socket/scheduler_monitor``：服务端循环推送，
  ``sleep`` 查询参数可调推送间隔（秒），下限 1 秒
"""

import asyncio
import contextlib
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse
import orjson as json
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from liuying.services.apscheduler import (
    alert_manager,
    metrics_collector,
    task_manager,
)
from liuying.utils.log import logger

from ....base_model import Result
from ....utils import authentication

# REST router 独立成页，无外层 router 包裹，直接声明前缀；
# ws_router 注册进 WsApiRouter（prefix=/liuying/socket），同样无需前缀
router = APIRouter(prefix="/scheduler")
ws_router = APIRouter()

# WS 推送间隔下限（秒），防止客户端传极小值打满事件循环
_MIN_PUSH_INTERVAL = 1


def _fmt_time(value: datetime | None) -> str | None:
    """datetime 转 ISO 字符串，空值返回 None"""
    return value.isoformat() if value else None


def build_scheduler_payload() -> dict:
    """汇总调度器指标、全部任务运行信息与告警阈值

    任务数据取自管理器与调度器共享的 TaskEntry 仓库（单一数据源），
    执行指标按任务ID查只读指标表；不序列化 args/kwargs（可能含
    不可 JSON 化对象），监控面板无需展示函数参数。
    """
    tasks = []
    for entry in task_manager.get_all_tasks():
        metrics = metrics_collector.get_task_metrics(entry.id)
        tasks.append(
            {
                "id": entry.id,
                "name": entry.name,
                "trigger_type": entry.trigger_type.value,
                "status": entry.status.value,
                "group": entry.group,
                "priority": entry.priority,
                "max_instances": entry.max_instances,
                "run_count": entry.run_count,
                "save_to_db": entry.save_to_db,
                "next_run_time": _fmt_time(entry.next_run_time),
                "last_run_time": _fmt_time(entry.last_run_time),
                "total_executions": metrics.total_executions if metrics else 0,
                "success_rate": round(metrics.success_rate, 4) if metrics else 0,
                "avg_duration": round(metrics.avg_duration, 3) if metrics else 0,
                "consecutive_failures": (
                    metrics.consecutive_failures if metrics else 0
                ),
            }
        )

    tasks.sort(key=lambda item: (item["group"], item["trigger_type"], item["id"]))

    config = alert_manager.config
    return {
        "scheduler": metrics_collector.get_scheduler_metrics().to_dict(),
        "tasks": tasks,
        "alert_thresholds": {
            "failure_rate": config.failure_rate_threshold,
            "consecutive_failures": config.consecutive_failures_threshold,
            "min_total_executions": config.min_total_executions,
            "timeout_seconds": config.timeout_threshold_seconds,
            "long_running_seconds": config.long_running_threshold_seconds,
            "queue_backlog": config.queue_backlog_threshold,
            "cooldown_seconds": config.cooldown_seconds,
        },
    }


@router.get(
    "/get_status",
    dependencies=[authentication()],
    response_model=Result[dict],
    response_class=JSONResponse,
    description="单次获取定时任务监控快照（调度器指标/任务列表/告警阈值）",
)
async def _() -> Result[dict]:
    """单次拉取监控快照，与 WS ``/scheduler_monitor`` 推送内容同源"""
    try:
        return Result.ok(build_scheduler_payload())
    except Exception as e:
        return Result.fail(f"获取定时任务监控状态失败: {type(e).__name__}: {e}")


@ws_router.websocket("/scheduler_monitor")
async def scheduler_monitor_realtime(websocket: WebSocket, sleep: int = 3):
    """循环推送定时任务监控快照

    消息为 Result 信封的手工 dict（与 REST 响应同构），前端按
    ``msg.data`` 解包。快照构建失败时跳过本轮推送而非断开连接。

    参数:
        websocket: WS 连接
        sleep: 推送间隔（秒），下限 1 秒
    """
    await websocket.accept()
    logger.debug("ws scheduler_monitor is connect")
    with contextlib.suppress(
        WebSocketDisconnect, ConnectionClosedError, ConnectionClosedOK
    ):
        while websocket.client_state == WebSocketState.CONNECTED:
            try:
                payload = build_scheduler_payload()
            except Exception as e:
                logger.warning("scheduler_monitor 快照构建失败", command="WebUi", e=e)
                payload = None
            if payload is not None:
                # orjson 恒定 UTF-8 输出（无 ensure_ascii 参数），返回 bytes 需解码
                await websocket.send_text(
                    json.dumps(
                        {"suc": True, "code": 200, "info": "成功", "data": payload}
                    ).decode()
                )
            await asyncio.sleep(max(_MIN_PUSH_INTERVAL, sleep))
