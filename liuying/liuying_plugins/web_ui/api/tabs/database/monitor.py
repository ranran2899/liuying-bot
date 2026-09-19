"""数据库状态监控接口

对接 ``liuying.services.liuying_db.monitoring`` 的连接池监控与连接泄漏
检测，以及 ``sync_manager`` 主从同步状态：
- REST ``GET /database/get_monitor_status``：单次拉取快照
- WS   ``/liuying/socket/db_monitor``：服务端循环推送，``sleep`` 查询
  参数可调推送间隔（秒），下限 1 秒
"""

import asyncio
import contextlib

from fastapi import APIRouter
from fastapi.responses import JSONResponse
import orjson as json
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from liuying.configs.config import BotConfig
from liuying.services.cache import CacheRoot
from liuying.services.liuying_db import session_manager, sync_manager
from liuying.services.liuying_db.monitoring import leak_detector, pool_monitor
from liuying.utils.log import logger

from ....base_model import Result
from ....utils import authentication

# REST router 由 database/__init__.py 的 router（prefix=/database）include，
# 此处不能再声明前缀，否则路径叠加为 /database/database/*；
# ws_router 注册进 WsApiRouter（prefix=/liuying/socket），同样无需前缀
router = APIRouter()
ws_router = APIRouter()

# 下发给前端的采样历史条数上限
_HISTORY_LIMIT = 60

# WS 推送间隔下限（秒），防止客户端传极小值打满事件循环
_MIN_PUSH_INTERVAL = 1


def build_monitor_payload() -> dict:
    """汇总各数据库连接池实时指标、泄漏检测、近期告警与同步状态

    实时指标以 record=False 采集，不写入监控循环的采样历史，
    避免高频采样污染 30 秒间隔的标准采样序列。
    """
    databases = []
    for db_name in session_manager.engines:
        metrics = pool_monitor.collect_metrics(db_name, record=False)
        if metrics is None:
            continue
        history = pool_monitor.get_metrics_history(db_name)[-_HISTORY_LIMIT:]
        databases.append(
            {
                "name": db_name,
                "pool_size": metrics.pool_size,
                "checked_in": metrics.checked_in,
                "checked_out": metrics.checked_out,
                "overflow": metrics.overflow,
                "usage_rate": round(metrics.usage_rate, 4),
                "is_healthy": metrics.is_healthy,
                "tables_created": session_manager.db_tables_created.get(
                    db_name, False
                ),
                "history": [
                    {
                        "t": m.timestamp,
                        "u": round(m.usage_rate, 4),
                        "c": m.checked_out,
                    }
                    for m in history
                ],
            }
        )

    leak = leak_detector.get_stats()
    leak["sessions"] = [
        {"db_name": db, "session_id": sid, "age": round(age, 1), "trace": info}
        for db, sid, age, info in leak_detector.detect_leaks()
    ]
    alerts = [
        {
            "db_name": a.db_name,
            "level": a.level.value,
            "message": a.message,
            "usage_rate": round(a.usage_rate, 4),
            "timestamp": a.timestamp,
        }
        for a in pool_monitor.get_recent_alerts(20)
    ]
    return {
        "sql_type": BotConfig.get_sql_type(),
        "databases": databases,
        "leak": leak,
        "alerts": alerts,
        "sync": sync_manager.get_sync_status(),
        "thresholds": {
            "warning": pool_monitor.warning_threshold,
            "critical": pool_monitor.critical_threshold,
        },
    }


@router.get(
    "/get_monitor_status",
    dependencies=[authentication()],
    response_model=Result[dict],
    response_class=JSONResponse,
    description="单次获取数据库状态监控快照（连接池/泄漏检测/告警/主从同步）",
)
async def _() -> Result[dict]:
    """单次拉取监控快照，与 WS ``/db_monitor`` 推送内容同源"""
    try:
        return Result.ok(build_monitor_payload())
    except Exception as e:
        return Result.fail(f"获取数据库监控状态失败: {type(e).__name__}: {e}")


@router.get(
    "/get_cache_stats",
    dependencies=[authentication()],
    response_model=Result[dict],
    response_class=JSONResponse,
    description="获取缓存系统监控统计（模式/注册类型/命中率/延迟分位）",
)
async def _() -> Result[dict]:
    """透传 ``CacheRoot.stats``：启用状态、模式、全局与分类型指标"""
    try:
        return Result.ok(CacheRoot.stats)
    except Exception as e:
        return Result.fail(f"获取缓存统计失败: {type(e).__name__}: {e}")


@router.post(
    "/reset_cache_stats",
    dependencies=[authentication()],
    response_model=Result,
    response_class=JSONResponse,
    description="重置缓存监控统计数据（不影响缓存数据本身）",
)
async def _() -> Result:
    """清空缓存命中率与延迟统计计数器"""
    try:
        CacheRoot.monitor.reset()
        return Result.ok(info="缓存统计已重置")
    except Exception as e:
        return Result.fail(f"重置缓存统计失败: {type(e).__name__}: {e}")


@ws_router.websocket("/db_monitor")
async def db_monitor_realtime(websocket: WebSocket, sleep: int = 3):
    """循环推送数据库监控快照

    消息为 Result 信封的手工 dict（与 REST 响应同构），前端按
    ``msg.data`` 解包。快照构建失败时跳过本轮推送而非断开连接。

    参数:
        websocket: WS 连接
        sleep: 推送间隔（秒），下限 1 秒
    """
    await websocket.accept()
    logger.debug("ws db_monitor is connect")
    with contextlib.suppress(
        WebSocketDisconnect, ConnectionClosedError, ConnectionClosedOK
    ):
        while websocket.client_state == WebSocketState.CONNECTED:
            try:
                payload = build_monitor_payload()
            except Exception as e:
                logger.warning("db_monitor 快照构建失败", command="WebUi", e=e)
                payload = None
            if payload is not None:
                # orjson 恒定 UTF-8 输出（无 ensure_ascii 参数），返回 bytes 需解码
                await websocket.send_text(
                    json.dumps(
                        {"suc": True, "code": 200, "info": "成功", "data": payload}
                    ).decode()
                )
            await asyncio.sleep(max(_MIN_PUSH_INTERVAL, sleep))


@ws_router.websocket("/cache_monitor")
async def cache_monitor_realtime(websocket: WebSocket, sleep: int = 5):
    """循环推送缓存系统监控统计（CacheRoot.stats）

    消息结构与 REST ``/get_cache_stats`` 同构，前端按 ``msg.data`` 解包。
    快照构建失败时跳过本轮推送而非断开连接。

    参数:
        websocket: WS 连接
        sleep: 推送间隔（秒），下限 1 秒
    """
    await websocket.accept()
    logger.debug("ws cache_monitor is connect")
    with contextlib.suppress(
        WebSocketDisconnect, ConnectionClosedError, ConnectionClosedOK
    ):
        while websocket.client_state == WebSocketState.CONNECTED:
            try:
                payload = CacheRoot.stats
            except Exception as e:
                logger.warning("cache_monitor 快照构建失败", command="WebUi", e=e)
                payload = None
            if payload is not None:
                await websocket.send_text(
                    json.dumps(
                        {"suc": True, "code": 200, "info": "成功", "data": payload}
                    ).decode()
                )
            await asyncio.sleep(max(_MIN_PUSH_INTERVAL, sleep))
