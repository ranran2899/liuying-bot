import contextlib
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import re

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from nonebot.adapters import Bot
from nonebot.adapters.qq import Bot as QQBot
from nonebot.utils import run_sync
import psutil
import ujson as json

from liuying.configs.config import BotConfig, Config
from liuying.configs.path_config import DATA_PATH
from liuying.utils.log import logger
from liuying.utils.platform import PlatformUtils
from liuying.utils.platform.avatar_utils import AvatarUtils

from .base_model import SystemFolderSize, SystemStatus, User

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/login")

token_file = DATA_PATH / "web_ui" / "token.json"
token_file.parent.mkdir(parents=True, exist_ok=True)
token_data: dict = {"token": []}
if token_file.exists():
    with contextlib.suppress(json.JSONDecodeError):
        with open(token_file, encoding="utf8") as f:
            token_data = json.load(f)


def validate_path(path_str: str | None) -> tuple[Path | None, str | None]:
    """验证路径是否安全

    参数:
        path_str: 用户输入的路径

    返回:
        tuple[Path | None, str | None]: (验证后的路径, 错误信息)
    """
    try:
        if not path_str:
            return Path().resolve(), None

        # 1. 移除任何可能的路径遍历尝试
        path_str = re.sub(r"[\\/]\.\.[\\/]", "", path_str)

        # 2. 规范化路径并转换为绝对路径
        path = Path(path_str).resolve()

        # 3. 获取项目根目录
        root_dir = Path().resolve()

        # 4. 验证路径是否在项目根目录内
        try:
            if not path.is_relative_to(root_dir):
                return None, "访问路径超出允许范围"
        except ValueError:
            return None, "无效的路径格式"

        # 5. 验证路径是否包含任何危险字符
        if any(c in str(path) for c in ["..", "~", "*", "?", ">", "<", "|", '"']):
            return None, "路径包含非法字符"

        # 6. 验证路径长度是否合理
        return (None, "路径长度超出限制") if len(str(path)) > 4096 else (path, None)
    except Exception as e:
        return None, f"路径验证失败: {e!s}"


def get_user(uname: str) -> User | None:
    """获取账号密码

    参数:
        uname: uname

    返回:
        Optional[User]: 用户信息
    """
    username = Config.get_config("web-ui", "username")
    password = Config.get_config("web-ui", "password")
    if username and password and uname == username:
        # YAML 可能将纯数字密码解析为 int，User 模型要求 str，此处显式转换
        return User(username=str(username), password=str(password))


def create_token(user: User, expires_delta: timedelta | None = None):
    """创建token

    参数:
        user: 用户信息
        expires_delta: 过期时间.
    """
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=15))
    return jwt.encode(
        claims={"sub": user.username, "exp": expire},
        key=Config.get_config("web-ui", "secret"),
        algorithm=ALGORITHM,
    )


def authentication():
    """权限验证

    异常:
        JWTError: JWTError
        HTTPException: HTTPException
    """

    # if token not in token_data["token"]:
    def inner(token: str = Depends(oauth2_scheme)):
        try:
            payload = jwt.decode(
                token, Config.get_config("web-ui", "secret"), algorithms=[ALGORITHM]
            )
            username, _ = payload.get("sub"), payload.get("exp")
            user = get_user(username)  # type: ignore
            if user is None:
                raise JWTError
        except JWTError:
            raise HTTPException(
                status_code=400, detail="登录验证失败或已失效, 踢出房间!"
            )

    return Depends(inner)


def _get_dir_size(dir_path: Path) -> float:
    """获取文件夹大小

    参数:
        dir_path: 文件夹路径
    """
    return sum(
        sum(os.path.getsize(os.path.join(root, name)) for name in files)
        for root, dirs, files in os.walk(dir_path)
    )


@run_sync
def get_system_status() -> SystemStatus:
    """获取系统信息等"""
    cpu = psutil.cpu_percent()
    memory = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent
    return SystemStatus(
        cpu=cpu,
        memory=memory,
        disk=disk,
        check_time=datetime.now().replace(microsecond=0),
    )


@run_sync
def get_system_disk(
    full_path: str | None,
) -> list[SystemFolderSize]:
    """获取资源文件大小等"""
    base_path = Path(full_path) if full_path else Path()
    other_size = 0
    data_list = []
    for file in os.listdir(base_path):
        f = base_path / file
        if f.is_dir():
            size = _get_dir_size(f) / 1024 / 1024
            data_list.append(
                SystemFolderSize(name=file, size=size, full_path=str(f), is_dir=True)
            )
        else:
            other_size += f.stat().st_size / 1024 / 1024
    if other_size:
        data_list.append(
            SystemFolderSize(
                name="other_file", size=other_size, full_path=full_path, is_dir=False
            )
        )
    return data_list


async def get_bot_login_info(
    bot: Bot, default_id: str | None = None
) -> tuple[str, str]:
    """获取机器人登录信息（昵称与头像URL）

    优先判断是否为 QQ 官方机器人：若是则使用 QQ 官方
    /users/@me 接口返回的信息（昵称与头像），否则回退至
    OneBot 的 get_login_info 与 QQ 头像拼接逻辑。

    参数:
        bot: NoneBot Bot 实例
        default_id: 无法获取时的默认ID

    返回:
        tuple[str, str]: (昵称, 头像URL)
    """
    bot_id = bot.self_id or default_id or ""
    if isinstance(bot, QQBot):
        return await _get_qq_official_info(bot, bot_id)
    return await _get_onebot_info(bot, bot_id)


async def _get_qq_official_info(bot: QQBot, default_id: str) -> tuple[str, str]:
    """获取 QQ 官方机器人信息

    优先复用 bot 已连接的自身信息（self_info，连接就绪后由 ReadyEvent
    写入），缺失时回退调用适配器内置的 /users/@me 接口（bot.me()）。
    头像 URL 由官方签名可直接访问。

    参数:
        bot: QQ 官方 Bot 实例
        default_id: 无法获取时的默认ID

    返回:
        tuple[str, str]: (昵称, 头像URL)
    """
    try:
        user = bot.self_info
    except RuntimeError:
        user = None
    if user is None:
        try:
            user = await bot.me()
        except Exception as e:
            logger.warning("获取QQ官方机器人信息失败", command="WebUi", e=e)
            return default_id, ""
    return user.username or default_id, user.avatar or ""


async def _get_onebot_info(bot: Bot, default_id: str) -> tuple[str, str]:
    """获取 OneBot 机器人信息

    参数:
        bot: NoneBot Bot 实例
        default_id: 无法获取时的默认ID

    返回:
        tuple[str, str]: (昵称, 头像URL)
    """
    platform = PlatformUtils.get_platform(bot) or ""
    nickname = default_id
    ava_url = ""
    if platform == "qq" and hasattr(bot, "get_login_info"):
        try:
            login_info = await bot.get_login_info()
            nickname = login_info.get("nickname") or default_id
        except Exception as e:
            logger.warning("调用接口get_login_info失败", command="WebUi", e=e)
    try:
        ava_url = (
            AvatarUtils.get_user_avatar_url(
                default_id, "qq", BotConfig.get_qbot_uid(default_id)
            )
            or ""
        )
    except Exception as e:
        logger.warning("获取bot头像失败", command="WebUi", e=e)
    return nickname, ava_url
