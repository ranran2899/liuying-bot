from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from liuying.configs.path_config import DATA_PATH
from liuying.utils.log import logger

WEBUI_PATH = DATA_PATH / "web_ui"
"""WebUI 静态资源目录"""

router = APIRouter()


@router.get("/")
async def index():
    return FileResponse(WEBUI_PATH / "index.html")


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
