"""定时任务管理路由

提供定时任务列表查询与暂停/恢复/立即执行/移除操作。
"""

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from liuying.utils.apscheduler.manager import task_manager

from ..deps import require_auth

__all__ = ["build_task_router"]


def build_task_router() -> APIRouter:
    """构建定时任务管理路由

    Returns:
        APIRouter: 定时任务管理路由器
    """
    router = APIRouter(prefix="/tasks", tags=["本体-定时任务"])

    @router.get("")
    async def list_tasks(group: str = "") -> dict[str, Any]:
        """获取全部定时任务列表

        参数:
            group: 分组过滤（可选）

        返回:
            dict: 任务列表与分组统计
        """
        try:
            tasks = task_manager.get_all_tasks()
            if group:
                tasks = [t for t in tasks if t.group == group]
            groups = {}
            for t in task_manager.get_all_tasks():
                groups[t.group] = groups.get(t.group, 0) + 1
            return {
                "tasks": [t.to_dict() for t in tasks],
                "count": len(tasks),
                "groups": groups,
                "started": getattr(task_manager, "_started", False),
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.post("/pause")
    async def pause_task(
        body: dict = Body(default_factory=dict),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """暂停指定定时任务

        请求体:
            task_id: 任务ID
        """
        task_id = str(body.get("task_id", "")).strip()
        if not task_id:
            raise HTTPException(
                status_code=400, detail="task_id 不能为空"
            )
        try:
            ok = await task_manager.pause_task(task_id)
            return {"ok": ok, "task_id": task_id, "action": "pause"}
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.post("/resume")
    async def resume_task(
        body: dict = Body(default_factory=dict),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """恢复指定定时任务

        请求体:
            task_id: 任务ID
        """
        task_id = str(body.get("task_id", "")).strip()
        if not task_id:
            raise HTTPException(
                status_code=400, detail="task_id 不能为空"
            )
        try:
            ok = await task_manager.resume_task(task_id)
            return {"ok": ok, "task_id": task_id, "action": "resume"}
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.post("/run")
    async def run_task(
        body: dict = Body(default_factory=dict),
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """立即执行指定定时任务

        请求体:
            task_id: 任务ID
        """
        task_id = str(body.get("task_id", "")).strip()
        if not task_id:
            raise HTTPException(
                status_code=400, detail="task_id 不能为空"
            )
        try:
            ok = task_manager.run_task_now(task_id)
            return {
                "ok": ok,
                "task_id": task_id,
                "action": "run_now",
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.delete("")
    async def remove_task(
        task_id: str,
        _: None = Depends(require_auth),
    ) -> dict[str, Any]:
        """移除指定定时任务

        参数:
            task_id: 任务ID
        """
        if not task_id:
            raise HTTPException(
                status_code=400, detail="task_id 不能为空"
            )
        try:
            ok = await task_manager.remove_task(task_id)
            return {"ok": ok, "task_id": task_id, "action": "remove"}
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.get("/{task_id}")
    async def task_detail(task_id: str) -> dict[str, Any]:
        """获取单个定时任务详情"""
        try:
            task = task_manager.get_task(task_id)
            if not task:
                raise HTTPException(
                    status_code=404, detail=f"未找到任务: {task_id}"
                )
            return task.to_dict()
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    return router
