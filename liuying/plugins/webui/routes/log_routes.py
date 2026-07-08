"""日志查看路由

提供日志文件列表与尾部内容读取。日志文件位于 LOG_PATH 目录。
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from liuying.configs.path_config import LOG_PATH

from ..config import get_config

__all__ = ["build_log_router"]

_LOG_ROOT = LOG_PATH.resolve()
"""日志根目录（解析后用于路径穿越校验）"""


def _is_safe_log_name(name: str) -> bool:
    """校验日志文件名安全且无路径穿越"""
    if not name or "/" in name or "\\" in name or ".." in name:
        return False
    if Path(name).name != name:
        return False
    return True


def build_log_router() -> APIRouter:
    """构建日志查看路由"""
    router = APIRouter(prefix="/logs", tags=["WebUI-日志查看"])

    @router.get("")
    async def list_logs() -> dict[str, Any]:
        """获取日志文件列表（按修改时间倒序）"""
        files: list[dict[str, Any]] = []
        if _LOG_ROOT.exists():
            for p in _LOG_ROOT.iterdir():
                if not p.is_file():
                    continue
                if p.suffix.lower() not in {".log", ".txt"}:
                    continue
                stat = p.stat()
                files.append(
                    {
                        "name": p.name,
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    }
                )
        files.sort(key=lambda x: x["modified"], reverse=True)
        return {"files": files, "count": len(files)}

    @router.get("/{name}")
    async def read_log(name: str, lines: int = 0) -> dict[str, Any]:
        """读取日志文件尾部内容

        参数:
            name: 日志文件名
            lines: 返回的尾部行数（0 表示使用配置默认值）
        """
        if not _is_safe_log_name(name):
            raise HTTPException(status_code=400, detail="非法日志文件名")
        target = (_LOG_ROOT / name).resolve()
        try:
            target.relative_to(_LOG_ROOT)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="日志文件不存在") from exc
        if not target.is_file():
            raise HTTPException(status_code=404, detail="日志文件不存在")

        max_lines = int(lines) if lines and lines > 0 else int(
            get_config("WEBUI_LOG_TAIL_LINES", 400)
        )
        max_lines = max(1, min(max_lines, 5000))
        with target.open(encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        tail = all_lines[-max_lines:]
        return {
            "name": name,
            "lines": [line.rstrip("\n") for line in tail],
            "total_lines": len(all_lines),
            "truncated": len(all_lines) > max_lines,
            "returned": len(tail),
        }

    return router
