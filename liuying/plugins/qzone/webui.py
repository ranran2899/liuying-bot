"""QZone WebUI 路由

独立的 FastAPI APIRouter，提供 QZone 状态查询、cookie 配置、动态拉取。
挂载到 NoneBot driver 的 server_app，路径前缀 /qzone。
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from nonebot import get_driver

from liuying.utils.log import logger

from .service import qzone_service

__all__ = ["build_qzone_router", "register_qzone_webui"]


def _get_superusers() -> set[str]:
    """获取超级用户集合

    返回:
        set[str]: 超级用户ID集合
    """
    driver = get_driver()
    return set(
        getattr(driver.config, "superusers", set()) or set()
    )


def _require_superuser(user_id: str = "") -> None:
    """写操作鉴权依赖

    校验请求方是否为超级用户，未授权时抛出 403。
    通过 FastAPI Depends 挂载到所有写操作路由。

    参数:
        user_id: 请求方用户ID（query参数）

    异常:
        HTTPException: 非超级用户时抛出 403
    """
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="缺少 user_id 参数",
        )
    if str(user_id) not in _get_superusers():
        raise HTTPException(
            status_code=403,
            detail="需要超级用户权限",
        )


def build_qzone_router() -> APIRouter:
    """构建QZone WebUI路由

    返回:
        APIRouter: FastAPI路由器
    """
    router = APIRouter(prefix="/qzone", tags=["QZone管理"])

    @router.get("/status")
    async def qzone_status() -> dict[str, Any]:
        """获取QZone服务状态"""
        try:
            cookie = qzone_service._cookie
            return {
                "enabled": qzone_service.enabled,
                "uin": cookie.uin or "",
                "updated_at": (
                    datetime.fromtimestamp(
                        cookie.updated_at
                    ).isoformat()
                    if cookie.updated_at
                    else ""
                ),
                "has_p_skey": bool(cookie.p_skey),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.post("/cookie")
    async def qzone_cookie_set(
        p_skey: str,
        uin: str,
        skey: str = "",
        p_uin: str = "",
        pt4_token: str = "",
        _: None = Depends(_require_superuser),
    ) -> dict[str, Any]:
        """设置QZone cookie

        参数:
            p_skey: p_skey值
            uin: QQ号
            skey: skey值
            p_uin: p_uin值
            pt4_token: pt4_token值

        返回:
            dict: 操作结果
        """
        try:
            if not p_skey or not uin:
                raise HTTPException(
                    status_code=400,
                    detail="p_skey与uin不能为空",
                )
            qzone_service.update_cookie(
                p_skey=p_skey,
                uin=uin,
                skey=skey,
                p_uin=p_uin,
                pt4_token=pt4_token,
            )
            return {
                "ok": True,
                "enabled": qzone_service.enabled,
                "uin": uin,
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.delete("/cookie")
    async def qzone_cookie_clear(
        _: None = Depends(_require_superuser),
    ) -> dict[str, Any]:
        """清除QZone cookie

        返回:
            dict: 操作结果
        """
        try:
            qzone_service.clear_cookie()
            return {"ok": True, "enabled": False}
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    @router.get("/feeds")
    async def qzone_feeds(count: int = 10) -> dict[str, Any]:
        """拉取QZone动态列表

        参数:
            count: 拉取数量

        返回:
            dict: 动态列表
        """
        try:
            if not qzone_service.enabled:
                raise HTTPException(
                    status_code=400,
                    detail="QZone未启用或cookie未配置",
                )
            feeds = await qzone_service.fetch_feeds(
                count=min(max(count, 1), 20)
            )
            return {
                "count": len(feeds),
                "feeds": feeds,
                "timestamp": datetime.now().isoformat(),
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=str(e)
            ) from e

    return router


def register_qzone_webui() -> None:
    """挂载QZone WebUI路由到NoneBot driver"""
    try:
        driver = get_driver()
        server_app = getattr(driver, "server_app", None)
        if server_app is None:
            logger.warning(
                "当前驱动不支持server_app，QZone WebUI未挂载",
                command="QZone",
            )
            return
        router = build_qzone_router()
        server_app.include_router(router)
        logger.info(
            "QZone WebUI路由已挂载到 /qzone/*",
            command="QZone",
        )
    except Exception as e:
        logger.warning(
            f"挂载QZone WebUI路由失败: {e}",
            command="QZone",
            e=e,
        )
