"""Qzone服务

QQ空间协议基础封装：g_tk签名哈希、cookie管理、
发说说（含配图）、拉取动态列表、点赞、评论。
实现完整参考 nonebot_plugin_personification 的 Qzone 用法。
"""

import base64
from dataclasses import dataclass
import html
import json
import re
import time
from typing import Any

import httpx

from liuying.utils.log import logger

__all__ = ["QzoneService", "qzone_service"]


_PUBLISH_URL = (
    "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/"
    "cgi-bin/emotion_cgi_publish_v6"
)
"""发说说CGI"""


_FEEDLIST_URL = (
    "https://user.qzone.qq.com/proxy/domain/taotao.qq.com/"
    "cgi-bin/emotion_cgi_msglist_v6"
)
"""拉取动态列表CGI"""


_LIKE_URL = (
    "https://user.qzone.qq.com/proxy/domain/w.qzone.qq.com/"
    "cgi-bin/likes/internal_dolike_app"
)
"""点赞CGI"""


_COMMENT_URL = (
    "https://user.qzone.qq.com/proxy/domain/taotao.qq.com/"
    "cgi-bin/emotion_cgi_re_feeds"
)
"""评论CGI"""


_UPLOAD_IMAGE_URL = "https://up.qzone.qq.com/cgi-bin/upload/cgi_upload_image"
"""上传配图CGI"""


_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)
"""PC端UA"""


_IMAGE_B64_RE = re.compile(r"\[IMAGE_B64\]([A-Za-z0-9+/=\r\n]+)\[/IMAGE_B64\]")
"""说说内容中的base64图片标记正则"""


def _get_g_tk(p_skey: str) -> int:
    """计算g_tk签名哈希

    Args:
        p_skey: p_skey值

    Returns:
        int: g_tk哈希值
    """
    hash_val = 5381
    for char in p_skey or "":
        hash_val += (hash_val << 5) + ord(char)
    return hash_val & 0x7FFFFFFF


def _parse_qzone_jsonp(text: str) -> dict[str, Any]:
    """解析Qzone JSONP响应

    先尝试直接解析JSON，失败则正则提取首个 {...} 块再解析。

    Args:
        text: 原始响应文本

    Returns:
        dict: 解析后的字典，失败返回空字典
    """
    raw = str(text or "").strip()
    try:
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(0))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _payload_success(
    payload: dict[str, Any],
    raw_text: str = "",
) -> tuple[bool, str]:
    """检查Qzone返回是否成功

    Args:
        payload: 解析后的字典
        raw_text: 原始响应文本（用于识别HTML登录页）

    Returns:
        tuple[bool, str]: (是否成功, 消息)
    """
    if not payload:
        raw_lower = str(raw_text or "").strip().lower()
        if raw_lower.startswith("<html") or raw_lower.startswith("<!doctype"):
            return False, "Qzone 返回了登录页面或验证码，请刷新 Cookie"
        return False, "Qzone 返回无法解析"

    for key in ("code", "ret", "subcode"):
        if key in payload:
            try:
                code = int(payload.get(key) or 0)
            except Exception:
                code = 0
            if code != 0:
                msg = str(
                    payload.get("message") or payload.get("msg") or payload
                )[:180]
                return False, msg
    return True, "ok"


def _is_qzone_success_text(text: str) -> bool:
    """通过原始响应文本判断Qzone操作是否成功

    QQ空间部分CGI返回的JSON字段不固定，直接字符串匹配
    "code":0 / "ret":0 / "subcode":0 作为兜底成功判断。

    Args:
        text: 原始响应文本

    Returns:
        bool: 是否包含成功标志
    """
    raw = str(text or "").strip()
    success_marks = (
        '"code":0',
        '"code": 0',
        '"ret":0',
        '"ret": 0',
        '"subcode":0',
        '"subcode": 0',
    )
    return any(mark in raw for mark in success_marks)


def _clean_qzone_text(value: Any) -> str:
    """清理QQ空间文本

    去除HTML标签、转义字符并压缩空白。

    Args:
        value: 原始文本或文本列表

    Returns:
        str: 清理后的文本
    """
    if isinstance(value, list):
        raw = "".join(
            str(item.get("text", "") if isinstance(item, dict) else item)
            for item in value
        )
    else:
        raw = str(value or "")
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.IGNORECASE)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


@dataclass(slots=True)
class QzoneCookie:
    """Qzone cookie存储

    Attributes:
        raw_cookie: 原始完整cookie字符串
        p_skey: p_skey值
        uin: 纯数字QQ号
        skey: skey值
        updated_at: 更新时间戳
    """

    raw_cookie: str = ""
    p_skey: str = ""
    uin: str = ""
    skey: str = ""
    updated_at: float = 0.0


class QzoneService:
    """Qzone服务

    封装QQ空间协议，提供发说说/拉取动态/点赞/评论。
    """

    def __init__(self) -> None:
        """初始化Qzone服务"""
        self._cookie = QzoneCookie()
        self._enabled = False
        self._client: httpx.AsyncClient | None = None

    @property
    def enabled(self) -> bool:
        """是否启用"""
        return self._enabled and bool(self._cookie.p_skey)

    @property
    def cookie_uin(self) -> str:
        """当前cookie的QQ号"""
        return self._cookie.uin

    @property
    def cookie_updated_at(self) -> float:
        """当前cookie的更新时间戳"""
        return self._cookie.updated_at

    def _format_cookie(self) -> str:
        """构建发送请求用的Cookie字符串

        QQ空间接口要求 cookie 中至少包含 uin=o{qq}; p_skey=xxx。

        Returns:
            str: 格式化后的cookie字符串
        """
        if self._cookie.p_skey and self._cookie.uin:
            formatted = (
                f"uin=o{self._cookie.uin}; p_skey={self._cookie.p_skey};"
            )
            if self._cookie.skey:
                formatted += f" skey={self._cookie.skey};"
            return formatted
        return self._cookie.raw_cookie

    def update_cookie(
        self,
        *,
        cookie: str = "",
        p_skey: str = "",
        uin: str = "",
        skey: str = "",
    ) -> None:
        """更新cookie

        支持传入完整 cookie 字符串，或单独传入 p_skey/uin/skey。
        若提供完整 cookie，会自动从中提取关键字段。

        Args:
            cookie: 完整cookie字符串
            p_skey: p_skey值
            uin: QQ号（允许带o前缀）
            skey: skey值
        """
        if cookie:
            self._cookie.raw_cookie = cookie
            pskey_match = re.search(r"p_skey=([^; ]+)", cookie)
            if pskey_match:
                self._cookie.p_skey = pskey_match.group(1)
            uin_match = re.search(r"uin=[oO0]*(\d+)", cookie)
            if uin_match:
                self._cookie.uin = uin_match.group(1)
            skey_match = re.search(r"skey=([^; ]+)", cookie)
            if skey_match:
                self._cookie.skey = skey_match.group(1)

        if p_skey:
            self._cookie.p_skey = p_skey
        if uin:
            self._cookie.uin = str(uin).lstrip("oO")
        if skey:
            self._cookie.skey = skey

        self._cookie.updated_at = time.time()
        self._enabled = bool(self._cookie.p_skey)
        logger.info(
            f"Qzone cookie已更新，uin={self._cookie.uin}",
            command="QZone",
        )

    def clear_cookie(self) -> None:
        """清除全部cookie字段并禁用服务"""
        self._cookie = QzoneCookie()
        self._enabled = False
        logger.info("QZone cookie已清除", command="QZone")

    def _get_g_tk(self) -> int:
        """获取当前g_tk

        Returns:
            int: g_tk哈希值
        """
        return _get_g_tk(self._cookie.p_skey)

    def _build_headers(self, referer_uin: str = "") -> dict[str, str]:
        """构建请求头

        Args:
            referer_uin: Referer中的QQ号（默认使用当前cookie的QQ号）

        Returns:
            dict: 请求头字典
        """
        uin = referer_uin or self._cookie.uin
        return {
            "User-Agent": _UA,
            "Referer": f"https://user.qzone.qq.com/{uin}",
            "Origin": "https://user.qzone.qq.com",
            "Cookie": self._format_cookie(),
        }

    async def _get_client(self) -> httpx.AsyncClient:
        """获取HTTP客户端

        Returns:
            httpx.AsyncClient: 客户端实例
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15.0)
        return self._client

    def _extract_image_b64_markers(
        self, text: str
    ) -> tuple[str, list[str]]:
        """提取说说内容中的base64图片标记

        Args:
            text: 原始说说内容

        Returns:
            tuple[str, list[str]]: (清理后的文本, base64图片载荷列表)
        """
        payloads: list[str] = []

        def _replace(match: re.Match[str]) -> str:
            payload = re.sub(r"\s+", "", match.group(1) or "")
            if payload:
                payloads.append(payload)
            return ""

        cleaned = _IMAGE_B64_RE.sub(_replace, str(text or "")).strip()
        return cleaned, payloads

    def _decode_image_b64(self, payload: str) -> bytes:
        """解码base64图片

        Args:
            payload: base64字符串（可能包含 data:image 前缀）

        Returns:
            bytes: 解码后的图片字节

        Raises:
            ValueError: base64无效
        """
        text = str(payload or "").strip()
        if "," in text and text.lower().startswith("data:image/"):
            text = text.split(",", 1)[1]
        text = re.sub(r"\s+", "", text)
        return base64.b64decode(text, validate=True)

    async def _upload_image(self, image_b64: str) -> str:
        """上传QQ空间配图并返回richval

        完整参考 nonebot_plugin_personification 的图片上传逻辑。

        Args:
            image_b64: base64编码的图片

        Returns:
            str: 上传成功返回 richval/picbo，失败返回空字符串
        """
        try:
            image_bytes = self._decode_image_b64(image_b64)
        except Exception as e:
            logger.warning(
                f"QZone配图base64无效: {e}", command="QZone", e=e
            )
            return ""
        if not image_bytes:
            return ""

        g_tk = self._get_g_tk()
        formatted_cookie = f"uin=o{self._cookie.uin}; p_skey={self._cookie.p_skey};"
        if self._cookie.skey:
            formatted_cookie += f" skey={self._cookie.skey};"

        url = f"{_UPLOAD_IMAGE_URL}?g_tk={g_tk}"
        data = {
            "uin": self._cookie.uin,
            "p_uin": self._cookie.uin,
            "skey": "",
            "zzpanelkey": "",
            "uploadtype": "1",
            "albumtype": "7",
            "exttype": "0",
            "refer": "shuoshuo",
            "output_type": "json",
            "charset": "utf-8",
            "output_charset": "utf-8",
            "upload_hd": "1",
            "hd_quality": "90",
        }
        headers = {
            "Cookie": formatted_cookie,
            "User-Agent": _UA,
            "Referer": f"https://user.qzone.qq.com/{self._cookie.uin}",
            "Origin": "https://user.qzone.qq.com",
        }
        files = {"filename": ("qzone.png", image_bytes, "image/png")}

        try:
            client = await self._get_client()
            resp = await client.post(
                url, data=data, files=files, headers=headers, timeout=20.0
            )
        except Exception as e:
            logger.warning(
                f"QZone配图上传失败: {e}", command="QZone", e=e
            )
            return ""
        if resp.status_code != 200:
            logger.warning(
                f"QZone配图上传失败，状态码：{resp.status_code}",
                command="QZone",
            )
            return ""

        payload = _parse_qzone_jsonp(resp.text)
        if not payload:
            logger.warning(
                "QZone配图上传返回无法解析", command="QZone"
            )
            return ""
        code = int(
            payload.get("ret", payload.get("code", 0)) or 0
        )
        if code not in {0, 1}:
            logger.warning(
                f"QZone配图上传返回异常：{str(payload)[:180]}",
                command="QZone",
            )
            return ""

        for key in ("richval", "picbo", "pic_bo", "lloc", "sloc"):
            value = str(payload.get(key, "") or "").strip()
            if value:
                return value
        data_obj = payload.get("data")
        if isinstance(data_obj, dict):
            for key in ("richval", "picbo", "pic_bo", "lloc", "sloc"):
                value = str(data_obj.get(key, "") or "").strip()
                if value:
                    return value
        logger.warning(
            "QZone配图上传未返回 richval/picbo", command="QZone"
        )
        return ""

    async def publish_shuo(
        self,
        content: str,
        *,
        visible: int = 0,
    ) -> tuple[bool, str]:
        """发说说

        完整参考 nonebot_plugin_personification 的发说说逻辑，
        支持 [IMAGE_B64]...[/IMAGE_B64] 标记自动上传配图。

        Args:
            content: 说说内容（可包含base64图片标记）
            visible: 可见性（0=公开 1=好友 2=私密）

        Returns:
            tuple[bool, str]: (是否成功, 消息)
        """
        if not self.enabled:
            return False, "Qzone未启用或cookie未配置"

        content_without_image, image_payloads = self._extract_image_b64_markers(
            content
        )
        cleaned_content = re.sub(
            r"\[图片(?:·[^\]]+)?\]|\[表情\]|\[动画表情\]",
            "",
            content_without_image,
        ).strip()
        if not cleaned_content and not image_payloads:
            return False, "说说内容不能为空（已过滤图片和表情）"

        richval = ""
        if image_payloads:
            richval = await self._upload_image(image_payloads[0])

        g_tk = self._get_g_tk()
        url = f"{_PUBLISH_URL}?g_tk={g_tk}"
        data = {
            "syn_tweet_version": 1,
            "paramstr": 1,
            "pic_template": "1" if richval else "",
            "richtype": "1" if richval else "",
            "richval": richval,
            "special_url": "",
            "subrichtype": "1" if richval else "",
            "con": cleaned_content,
            "feed_tpl_id": "w_v6",
            "ugc_right": visible,
            "who": 1,
            "modifyflag": 0,
            "hostuin": self._cookie.uin,
            "format": "json",
            "qzreferrer": (
                f"https://user.qzone.qq.com/{self._cookie.uin}"
            ),
        }
        headers = self._build_headers()
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        try:
            client = await self._get_client()
            resp = await client.post(url, data=data, headers=headers)
            if resp.status_code != 200:
                return False, f"请求失败，状态码：{resp.status_code}"

            text = resp.text
            if '"code":0' in text or '"code": 0' in text:
                return True, "发布成功"

            text_lower = text.strip().lower()
            if text_lower.startswith("<html") or text_lower.startswith(
                "<!doctype"
            ):
                return (
                    False,
                    "Qzone 返回了登录页面或验证码，请尝试重新获取空间 Cookie",
                )

            msg_match = re.search(r'"message":"([^"]+)"', text)
            err_msg = msg_match.group(1) if msg_match else text[:100]
            return False, f"发布失败，返回：{err_msg}"
        except Exception as e:
            logger.warning(
                f"发说说失败: {e}",
                command="QZone",
                e=e,
            )
            return False, f"请求失败: {e}"

    async def fetch_feeds(
        self,
        count: int = 10,
    ) -> list[dict[str, Any]]:
        """拉取动态列表

        Args:
            count: 拉取数量

        Returns:
            list[dict]: 动态列表
        """
        if not self.enabled:
            return []

        params = {
            "uin": self._cookie.uin,
            "ftype": "0",
            "sort": "0",
            "pos": "0",
            "num": str(max(1, min(40, int(count or 10)))),
            "replynum": "0",
            "g_tk": str(self._get_g_tk()),
            "callback": "_Callback",
            "code_version": "1",
            "format": "jsonp",
            "need_private_comment": "1",
        }
        headers = self._build_headers()

        try:
            client = await self._get_client()
            resp = await client.get(
                _FEEDLIST_URL,
                params=params,
                headers=headers,
            )
            if resp.status_code != 200:
                logger.warning(
                    f"拉取动态失败，状态码：{resp.status_code}",
                    command="QZone",
                )
                return []
            payload = _parse_qzone_jsonp(resp.text)
            ok, msg = _payload_success(payload, resp.text)
            if not ok:
                logger.warning(
                    f"拉取动态失败：{msg}",
                    command="QZone",
                )
                return []
            return payload.get("msglist", []) or []
        except Exception as e:
            logger.warning(
                f"拉取动态失败: {e}",
                command="QZone",
                e=e,
            )
            return []

    async def like_feed(
        self,
        feed_id: str,
        owner_uin: str,
    ) -> bool:
        """点赞动态

        Args:
            feed_id: 动态ID
            owner_uin: 动态所有者QQ

        Returns:
            bool: 是否成功
        """
        if not self.enabled:
            return False

        unikey = f"http://user.qzone.qq.com/{owner_uin}/mood/{feed_id}"
        data = {
            "qzreferrer": f"https://user.qzone.qq.com/{owner_uin}",
            "opuin": self._cookie.uin,
            "unikey": unikey,
            "curkey": unikey,
            "from": "1",
            "appid": "311",
            "typeid": "0",
            "abstime": str(int(time.time())),
            "fid": feed_id,
            "active": "0",
            "fupdate": "1",
            "format": "json",
        }
        headers = self._build_headers(referer_uin=owner_uin)
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        try:
            client = await self._get_client()
            resp = await client.post(
                _LIKE_URL,
                params={"g_tk": str(self._get_g_tk())},
                data=data,
                headers=headers,
            )
            if resp.status_code != 200:
                return False
            payload = _parse_qzone_jsonp(resp.text)
            ok, _ = _payload_success(payload, resp.text)
            return ok
        except Exception as e:
            logger.warning(
                f"点赞失败: {e}",
                command="QZone",
                e=e,
            )
            return False

    async def comment_feed(
        self,
        feed_id: str,
        owner_uin: str,
        content: str,
    ) -> tuple[bool, str]:
        """评论动态

        Args:
            feed_id: 动态ID
            owner_uin: 动态所有者QQ
            content: 评论内容

        Returns:
            tuple[bool, str]: (是否成功, 消息)
        """
        if not self.enabled:
            return False, "Qzone未启用或cookie未配置"
        if not content.strip():
            return False, "评论内容不能为空"

        topic_id = f"{owner_uin}_{feed_id}__1"
        data = {
            "uin": self._cookie.uin,
            "hostUin": owner_uin,
            "topicId": topic_id,
            "content": _clean_qzone_text(content)[:80],
            "private": "0",
            "paramstr": "1",
            "format": "json",
            "feedsType": "100",
            "plat": "qzone",
            "source": "ic",
            "ref": "feeds",
            "platformid": "52",
            "richtype": "",
            "richval": "",
            "inCharset": "utf-8",
            "outCharset": "utf-8",
            "qzreferrer": (
                f"https://user.qzone.qq.com/{owner_uin}"
            ),
        }
        headers = self._build_headers(referer_uin=owner_uin)
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        try:
            client = await self._get_client()
            resp = await client.post(
                _COMMENT_URL,
                params={"g_tk": str(self._get_g_tk())},
                data=data,
                headers=headers,
            )
            if resp.status_code != 200:
                return False, f"评论失败，状态码：{resp.status_code}"
            text = resp.text
            payload = _parse_qzone_jsonp(text)
            ok, msg = _payload_success(payload, text)
            if ok or _is_qzone_success_text(text):
                return True, "评论成功"
            return False, f"评论失败：{msg}"
        except Exception as e:
            logger.warning(
                f"评论失败: {e}",
                command="QZone",
                e=e,
            )
            return False, f"请求失败: {e}"

    async def close(self) -> None:
        """关闭客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


qzone_service = QzoneService()
"""Qzone服务单例"""
