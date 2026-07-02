"""
漂流瓶Web管理模块

提供Web审核界面与API，使用SQLAlchemy ORM模型
"""
import base64
from datetime import datetime, timedelta
import hashlib
from hmac import compare_digest
import os
from pathlib import Path
import secrets
from typing import Any

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import APIRouter, Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from nonebot import get_app, get_driver, get_plugin_config
from pydantic import BaseModel as PydanticModel
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.status import HTTP_302_FOUND
from starlette.templating import _TemplateResponse

from liuying.models.bottle import BottleComment, BottleImage, BottleRecord
from liuying.utils.bed_layout import BedLayout
from liuying.utils.enum import StorageType
from liuying.utils.log import logger

from .config import Config

app = get_app()

if not isinstance(app, FastAPI):
    msg = "本插件需要 FastAPI 驱动器才能正常运行"
    raise RuntimeError(msg)

driver = get_driver()
config: Config = get_plugin_config(Config)

gzip_level = config.gzip_level
app.add_middleware(
    SessionMiddleware, secret_key=secrets.token_hex(32)
)
app.add_middleware(
    GZipMiddleware,
    minimum_size=100,
    compresslevel=int(gzip_level),
)

account = config.bottle_account
password = config.bottle_password
password_sha256 = hashlib.sha256(
    password.encode("utf-8")
).hexdigest()
account_sha256 = hashlib.sha256(
    account.encode("utf-8")
).hexdigest()

plugin_dir = Path(__file__).parent
static_dir = plugin_dir / "templates" / "static"
app.mount(
    "/bottle/static",
    StaticFiles(directory=str(static_dir)),
    name="bottle-static",
)

login_static_dir = plugin_dir / "templates" / "login" / "static"
app.mount(
    "/bottle/login/static",
    StaticFiles(directory=str(login_static_dir)),
    name="bottle-login-static",
)

templates_dir = plugin_dir / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

router = APIRouter(prefix="/bottle", tags=["bottle"])


class BottleInfo(PydanticModel):
    ID: int
    Content: str
    UserID: str
    GroupID: str | None
    TimeInfo: str
    Status: int
    Images: list[str]


class AESCryptoData(PydanticModel):
    Data: str
    a: str


def login_required(request: Request):
    """登录校验依赖项"""
    if "user" not in request.session or (
        datetime.now()
        >= datetime.fromtimestamp(
            request.session.get(
                "expire_time", datetime.now().timestamp()
            )
        )
    ):
        raise HTTPException(
            status_code=HTTP_302_FOUND,
            detail="未登录或登录已过期，请访问/bottle/login进行登录",
            headers={"Location": "/bottle/login"},
        )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """登录页面"""
    return templates.TemplateResponse(
        request, "login/login.html"
    )


@router.post("/login")
async def login(
    username: str = Form(...),
    password: str = Form(...),
    request: Request = None,
):
    """处理登录请求"""
    if compare_digest(
        username, account_sha256
    ) and compare_digest(password, password_sha256):
        request.session["user"] = username
        current_time = datetime.now()
        request.session["expire_time"] = (
            current_time + timedelta(hours=config.expire_time)
        ).timestamp()
        return RedirectResponse(
            url="/bottle/check", status_code=HTTP_302_FOUND
        )

    return JSONResponse(
        status_code=401,
        content={"detail": "用户名或密码错误"},
    )


@router.get("/check", response_class=HTMLResponse)
async def read_item(
    request: Request, user: str = Depends(login_required)
) -> _TemplateResponse:
    """审核首页"""
    pending_count = await BottleRecord.get_pending_count()
    pending_comments = await BottleComment.filter(status=0).count()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "pending_count": pending_count,
            "pending_comments": pending_comments,
        },
    )


@router.get("/bottles/random", response_model=AESCryptoData)
async def get_random_bottle(
    request: Request, user: str = Depends(login_required)
) -> AESCryptoData:
    """随机获取一个待审核漂流瓶"""
    bottle = await BottleRecord.get_random_pending()
    if not bottle:
        raise HTTPException(
            status_code=404, detail="漂流瓶不存在"
        )

    images = await BottleImage.get_images_by_bottle_id(bottle.id)
    images_base64 = []
    for img in images:
        data = await BedLayout.get_bytes(
            img.filename, storage_type=StorageType.LOCAL
        )
        if data:
            images_base64.append(
                base64.b64encode(data).decode("utf-8")
            )

    bottle_data = BottleInfo(
        ID=bottle.id,
        Content=bottle.content or "",
        UserID=bottle.user_id,
        GroupID=bottle.group_id,
        TimeInfo=bottle.create_time.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        Status=bottle.status,
        Images=images_base64,
    ).json().encode("utf-8")

    iv = os.urandom(16)
    key = hashlib.sha256(base64.b64encode(iv)).digest()
    padder = padding.PKCS7(
        algorithms.AES.block_size
    ).padder()
    padded_data = padder.update(bottle_data) + padder.finalize()

    cipher = Cipher(
        algorithms.AES(key),
        modes.CBC(iv),
        backend=default_backend(),
    )
    encryptor = cipher.encryptor()
    encrypted_data = (
        encryptor.update(padded_data) + encryptor.finalize()
    )

    return AESCryptoData(
        Data=base64.b64encode(encrypted_data).decode("utf-8"),
        a=base64.b64encode(iv).decode("utf-8"),
    )


@router.post("/bottles/approve/{bottle_id}")
async def approve_bottle(
    bottle_id: int, user: str = Depends(login_required)
) -> dict[str, str]:
    """审核通过漂流瓶"""
    success = await BottleRecord.approve_bottle(bottle_id)
    if not success:
        raise HTTPException(
            status_code=404, detail="漂流瓶不存在"
        )
    return {"status": "approved"}


@router.post("/bottles/refuse/{bottle_id}")
async def refuse_bottle(
    bottle_id: int, user: str = Depends(login_required)
) -> dict[str, str]:
    """拒绝漂流瓶"""
    success = await BottleRecord.refuse_bottle(bottle_id)
    if not success:
        raise HTTPException(
            status_code=404, detail="漂流瓶不存在"
        )

    await BottleImage.soft_delete_by_bottle_id(bottle_id)
    return {"status": "refused"}


@router.get("/comments", response_class=HTMLResponse)
async def review_comments(
    request: Request, user: str = Depends(login_required)
) -> _TemplateResponse:
    """评论审核页面"""
    comment = await BottleComment.get_random_pending()
    pending_count = await BottleRecord.get_pending_count()
    pending_comments = await BottleComment.filter(status=0).count()
    return templates.TemplateResponse(
        request,
        "comments.html",
        {
            "comment": comment,
            "pending_count": pending_count,
            "pending_comments": pending_comments,
        },
    )


@router.get("/comments/random")
async def get_random_comment(
    user: str = Depends(login_required),
) -> dict[str, Any]:
    """随机获取一个待审核评论"""
    comment = await BottleComment.get_random_pending()
    if not comment:
        raise HTTPException(
            status_code=404, detail="No comments found"
        )
    return {
        "comment_id": comment.id,
        "bottle_id": comment.bottle_id,
        "content": comment.content,
        "status": comment.status,
        "uid": comment.user_id,
    }


@router.post("/comments/approve/{comment_id}")
async def approve_comment(
    comment_id: int, user: str = Depends(login_required)
) -> dict[str, str]:
    """审核通过评论"""
    success = await BottleComment.approve_comment(comment_id)
    if not success:
        raise HTTPException(
            status_code=404, detail="Comment not found"
        )
    return {"status": "approved"}


@router.post("/comments/refuse/{comment_id}")
async def refuse_comment(
    comment_id: int, user: str = Depends(login_required)
) -> dict[str, str]:
    """拒绝评论"""
    success = await BottleComment.refuse_comment(comment_id)
    if not success:
        raise HTTPException(
            status_code=404, detail="Comment not found"
        )
    return {"status": "refused"}


app.include_router(router)


@driver.on_startup
def _():
    """启动时加载Web模块"""
    logger.info("漂流瓶Web管理模块加载成功")
