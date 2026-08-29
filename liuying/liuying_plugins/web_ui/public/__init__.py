from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from liuying.configs.path_config import DATA_PATH
from liuying.utils.log import logger

WEBUI_PATH = DATA_PATH / "web_ui"
"""WebUI 静态资源目录"""

extra_version_dirs: list[Path] = []
"""外部插件注册的静态资源目录，纳入版本指纹计算"""

_webui_version: str = ""
"""前端资源版本指纹（进程内缓存），基于 assets 目录最新文件修改时间生成"""


def get_version() -> str:
    """获取前端资源版本指纹（启动后首次访问时计算并缓存）

    基于 assets 目录与外部插件静态资源目录所有文件的最新修改时间
    生成，前端文件更新后版本自动变化，无需手动维护版本号。

    返回:
        秒级时间戳字符串，目录缺失时返回 "0"
    """
    global _webui_version
    if not _webui_version:
        latest = 0.0
        # 保序去重，避免同一目录重复扫描
        dirs = dict.fromkeys([WEBUI_PATH / "assets", *extra_version_dirs])
        for d in dirs:
            if d.is_dir():
                for f in d.rglob("*"):
                    if f.is_file():
                        latest = max(latest, f.stat().st_mtime)
        _webui_version = str(int(latest))
    return _webui_version


router = APIRouter()


@router.get("/")
async def index():
    path = WEBUI_PATH / "index.html"
    if path.is_file():
        # 注入资源版本指纹，替换页面内所有 {{ver}} 占位符
        html = path.read_text(encoding="utf8").replace("{{ver}}", get_version())
        return Response(content=html, media_type="text/html")
    raise HTTPException(status_code=404, detail="index.html not found")


def _serve_root_file(filename: str):
    """构造根目录静态文件响应函数

    参数:
        filename: 文件名

    返回:
        响应函数
    """

    async def _file():
        path = WEBUI_PATH / filename
        if path.is_file():
            return FileResponse(path)
        # 文件不存在时返回 404
        raise HTTPException(status_code=404, detail=f"{filename} not found")

    return _file


# 挂载根目录下的静态文件（favicon.svg / favicon.ico）
router.add_api_route("/favicon.svg", _serve_root_file("favicon.svg"), methods=["GET"])
router.add_api_route("/favicon.ico", _serve_root_file("favicon.ico"), methods=["GET"])


async def init_public(app: FastAPI):
    try:
        WEBUI_PATH.mkdir(parents=True, exist_ok=True)
        folders = [x.name for x in WEBUI_PATH.iterdir() if x.is_dir()]
        app.include_router(router)
        for pathname in folders:
            logger.debug(f"挂载文件夹: {pathname}", command="WebUI")
            app.mount(
                f"/{pathname}",
                StaticFiles(
                    directory=WEBUI_PATH / pathname,
                    check_dir=True,
                ),
                name=f"public_{pathname}",
            )
    except Exception as e:
        logger.error("初始化 WebUI资源 失败", command="WebUI", e=e)
