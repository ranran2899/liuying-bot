from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path
import stat
import sys
import time
from typing import ClassVar

import httpx
from nonebot_plugin_uninfo import Uninfo
from PIL import Image as PILImage
import pypinyin

from liuying.configs.config import Config
from liuying.utils.log import logger
from liuying.utils.time_utils import TimeUtils

from .limiters import CountLimiter, FreqLimiter, UserBlockLimiter  # noqa: F401


@dataclass
class EntityIDs:
    """实体ID数据类，包含用户ID、群组ID和频道ID"""
    user_id: str
    """用户id"""
    group_id: str | None
    """群组id"""
    channel_id: str | None
    """频道id"""


class ResourceDirManager:
    """临时文件管理器，用于管理和清理临时文件目录"""

    temp_path: ClassVar[set[Path]] = set()

    @classmethod
    def __tree_append(cls, path: Path, deep: int = 1, current: int = 0):
        """递归添加文件夹到临时路径集合

        参数:
            path: 要添加的路径
            deep: 递归深度，-1为无限深度
            current: 当前递归层级
        """
        if current >= deep and deep != -1:
            return
        path = path.resolve()
        for f in os.listdir(path):
            file = (path / f).resolve()
            if file.is_dir() and file not in cls.temp_path:
                cls.temp_path.add(file)
                logger.debug(f"添加临时文件夹: {file}")
                cls.__tree_append(file, deep, current + 1)

    @classmethod
    def add_temp_dir(cls, path: str | Path, tree: bool = False, deep: int = 1):
        """添加临时清理文件夹

        参数:
            path: 文件夹路径
            tree: 是否递归添加文件夹
            deep: 深度, -1 为无限深度
        """
        if isinstance(path, str):
            path = Path(path)
        if path not in cls.temp_path:
            cls.temp_path.add(path)
            logger.debug(f"添加临时文件夹: {path}")
        if tree:
            cls.__tree_append(path, deep)


def cn2py(word: str) -> str:
    """将字符串转化为拼音

    参数:
        word: 要转换的文本

    返回:
        str: 转换后的拼音字符串
    """
    return "".join("".join(i) for i in pypinyin.pinyin(word, style=pypinyin.NORMAL))


async def get_user_avatar(uid: int | str) -> bytes | None:
    """快捷获取用户头像

    参数:
        uid: 用户id

    返回:
        bytes | None: 用户头像数据，获取失败返回None
    """
    url = f"http://q1.qlogo.cn/g?b=qq&nk={uid}&s=160"
    async with httpx.AsyncClient() as client:
        for _ in range(3):
            try:
                return (await client.get(url)).content
            except Exception:
                logger.error("获取用户头像错误", "Util", target=uid)
    return None


async def get_group_avatar(gid: int | str) -> bytes | None:
    """快捷获取群头像

    参数:
        gid: 群号

    返回:
        bytes | None: 群头像数据，获取失败返回None
    """
    url = f"http://p.qlogo.cn/gh/{gid}/{gid}/640/"
    async with httpx.AsyncClient() as client:
        for _ in range(3):
            try:
                return (await client.get(url)).content
            except Exception:
                logger.error("获取群头像错误", "Util", target=gid)
    return None


def change_pixiv_image_links(
    url: str, size: str | None = None, nginx_url: str | None = None
) -> str:
    """根据配置改变图片大小和反代链接

    参数:
        url: 图片原图链接
        size: 模式
        nginx_url: 反代

    返回:
        str: 处理后的url
    """
    if size == "master":
        img_sp = url.rsplit(".", maxsplit=1)
        url = img_sp[0].replace("original", "master") + f"_master1200.{img_sp[1]}"
    if not nginx_url:
        nginx_url = Config.get_config("pixiv", "PIXIV_NGINX_URL")
    if nginx_url:
        url = (
            url.replace("i.pximg.net", nginx_url)
            .replace("i.pixiv.cat", nginx_url)
            .replace("i.pixiv.re", nginx_url)
            .replace("_webp", "")
        )
    return url


def change_img_md5(path_file: str | Path) -> bool:
    """改变图片MD5值

    参数:
        path_file: 图片路径

    返回:
        bool: 是否修改成功
    """
    try:
        with open(path_file, "a") as f:
            f.write(str(int(time.time() * 1000)))
        return True
    except Exception as e:
        logger.warning(f"改变图片MD5错误 Path：{path_file}", e=e)
        return False


def is_valid_date(date_text: str, separator: str = "-") -> bool:
    """检查日期是否合法

    参数:
        date_text: 日期字符串
        separator: 分隔符，默认为"-"

    返回:
        bool: 日期是否合法
    """
    return TimeUtils.is_valid_date(date_text, separator)


def get_entity_ids(session: Uninfo) -> EntityIDs:
    """获取用户id，群组id，频道id

    参数:
        session: Uninfo会话对象

    返回:
        EntityIDs: 包含用户id，群组id，频道id的数据类
    """
    user_id = session.user.id
    match session.group:
        case None:
            return EntityIDs(user_id=user_id, group_id=None, channel_id=None)
        case group if group.parent:
            return EntityIDs(
                user_id=user_id, group_id=group.parent.id, channel_id=group.id
            )
        case group:
            return EntityIDs(user_id=user_id, group_id=group.id, channel_id=None)


def is_number(text: str) -> bool:
    """检查文本是否为数字

    参数:
        text: 要检查的文本

    返回:
        bool: 是否为数字
    """
    try:
        float(text)
        return True
    except ValueError:
        return False


_BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp",
    ".mp3", ".wav", ".flac", ".ogg", ".m4a",
    ".mp4", ".avi", ".mov", ".wmv", ".flv",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".exe", ".dll", ".so", ".dylib",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".sqlite", ".db",
})


def is_binary_file(file_path: str | Path) -> bool:
    """检查文件是否为二进制文件

    参数:
        file_path: 文件路径

    返回:
        bool: 是否为二进制文件
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)
    return file_path.suffix.lower() in _BINARY_EXTENSIONS


def win_on_rm_error(func, path, exc_info):
    """Windows下删除只读文件时的错误处理函数

    参数:
        func: 调用的函数
        path: 文件路径
        exc_info: 异常信息
    """
    os.chmod(path, stat.S_IWRITE)
    func(path)


def format_image_url(image_url: str) -> str:
    """格式化图片URL，确保在不同系统下正确显示

    参数:
        image_url: 原始图片路径

    返回:
        str: 格式化后的URL
    """
    if not image_url or not os.path.exists(image_url):
        return image_url
    prefix = "file:///" if sys.platform.startswith("win") else "file://"
    return f"{prefix}{image_url.replace(chr(92), '/')}"


def get_image_size(img_bytes: bytes) -> tuple[str, str]:
    """获取图片尺寸

    参数:
        img_bytes: 图片字节数据

    返回:
        tuple[str, str]: 宽度和高度
    """
    with PILImage.open(BytesIO(img_bytes)) as image:
        width, height = image.size
    return str(width), str(height)
