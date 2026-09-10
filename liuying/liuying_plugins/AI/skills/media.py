"""技能层媒体获取工具

视觉类技能包（vision_analyze / vision_caller / web_search）都需要
把 URL 拉成字节并判定 MIME，逻辑集中在此处避免各自重复实现。
"""

import asyncio
import socket
from typing import Any
from urllib.parse import urlparse

from liuying.utils.http import AsyncHttpx

__all__ = [
    "MAX_IMAGE_BYTES",
    "MAX_PARALLEL_FETCH",
    "detect_mime",
    "fetch_image",
    "fetch_images",
    "is_gif",
]


MAX_IMAGE_BYTES = 8 * 1024 * 1024
"""单张图片体积上限（字节），超限直接拒绝以保护视觉模型配额"""

MAX_PARALLEL_FETCH = 4
"""批量拉取图片的并发上限"""

_FETCH_TIMEOUT = 20.0
"""单张图片下载超时（秒）"""

_PRIVATE_URL_HOSTS = ("localhost", "metadata.google.internal")
"""一律拒绝的主机名（环回与云元数据服务）"""

_MAGIC_MIMES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"BM", "image/bmp"),
)
"""魔数到MIME的映射，按字节前缀匹配"""

_WEBP_RIFF = b"RIFF"
"""WebP 容器头，需配合偏移8处的 WEBP 标记判定"""


def is_gif(data: bytes) -> bool:
    """判断字节流是否为GIF

    参数:
        data: 图片二进制数据

    返回:
        bool: 是否为GIF
    """
    return data[:6] in (b"GIF87a", b"GIF89a")


def detect_mime(data: bytes) -> str:
    """按魔数识别图片MIME

    不信任URL扩展名，QQ图床等场景URL常无扩展名或与实际格式不符。

    参数:
        data: 图片二进制数据

    返回:
        str: MIME类型，无法识别时回退 image/jpeg
    """
    for magic, mime in _MAGIC_MIMES:
        if data.startswith(magic):
            return mime
    if data[:4] == _WEBP_RIFF and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _is_private_ip(ip: str) -> bool:
    """判断IP是否属于内网/环回/链路本地网段

    参数:
        ip: IP地址字符串（IPv4或IPv6）

    返回:
        bool: 是否为内网地址
    """
    if ip.startswith(("127.", "10.", "192.168.", "169.254.")):
        return True
    if ip.startswith(("::1", "fe80:")):
        return True
    if ip.startswith("172."):
        parts = ip.split(".")
        if len(parts) > 1 and parts[1].isdigit():
            return 16 <= int(parts[1]) <= 31
    return False


def _is_private_address(host: str) -> bool:
    """检查主机是否解析到内网/环回/链路本地地址

    DNS 解析在 URL 校验阶段完成；防 DNS rebinding 的完整方案
    需在连接层固定已校验 IP，此处仅做基础防护。

    参数:
        host: URL主机名或IP

    返回:
        bool: 是否为内网地址
    """
    if host.lower() in _PRIVATE_URL_HOSTS:
        return True
    try:
        addr_info = socket.getaddrinfo(host, None)
    except (OSError, UnicodeError):
        # 解析失败按内网处理，拒绝请求
        return True
    for info in addr_info:
        if _is_private_ip(info[4][0]):
            return True
    return False


async def fetch_image(url: str) -> tuple[bytes, str, str]:
    """下载单张图片

    仅允许 http/https 且目标主机不得解析到内网地址（SSRF 基础防护）。

    参数:
        url: 图片URL

    返回:
        tuple[bytes, str, str]: (数据, MIME, 错误信息)，
            成功时错误信息为空串，失败时数据为空
    """
    url = (url or "").strip()
    if not url:
        return b"", "", "图片URL为空"

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return b"", "", "仅支持http/https图片链接"
    # SSRF 基础防护：私网/环回/链路本地地址拒绝拉取
    if _is_private_address(parsed.hostname):
        return b"", "", "禁止访问内网地址"

    # 外部图床属不可控依赖，超时/连接失败/状态码异常均降级为错误文本，
    # 由上层工具转成可读提示，避免拖垮整个Agent回合。
    try:
        data = await asyncio.wait_for(
            AsyncHttpx.get_content(url), timeout=_FETCH_TIMEOUT
        )
    except TimeoutError:
        return b"", "", "图片下载超时"
    except Exception as e:
        return b"", "", f"图片下载失败: {type(e).__name__}"

    if not data:
        return b"", "", "图片内容为空"
    if len(data) > MAX_IMAGE_BYTES:
        limit_mb = MAX_IMAGE_BYTES // (1024 * 1024)
        return b"", "", f"图片超过{limit_mb}MB上限"
    return data, detect_mime(data), ""


async def fetch_images(
    urls: list[str], limit: int = MAX_PARALLEL_FETCH
) -> list[tuple[str, bytes, str, str]]:
    """并发下载多张图片

    并发上限内一次拉完，把 N 次串行网络往返压成 1 轮。

    参数:
        urls: 图片URL列表
        limit: 最多处理的图片数

    返回:
        list[tuple[str, bytes, str, str]]: (URL, 数据, MIME, 错误) 列表
    """
    picked = [u for u in urls if (u or "").strip()][:limit]
    if not picked:
        return []
    results: list[Any] = await asyncio.gather(
        *(fetch_image(url) for url in picked)
    )
    return [
        (url, data, mime, error)
        for url, (data, mime, error) in zip(
            picked, results, strict=True
        )
    ]
