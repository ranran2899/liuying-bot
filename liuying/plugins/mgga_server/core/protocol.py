"""通信协议定义。

传输层为 WebSocket 文本帧，载荷为单行 JSON::

    {"t": "<包类型>", "seq": <可选的请求序号>, "d": {<数据>}}

服务端对「请求包」的应答会原样带回 ``seq``，客户端据此把回包对上请求；
服务端主动推送的广播包不带 ``seq``。错误统一用 ``error`` 包返回::

    {"t": "error", "seq": 12, "d": {"code": "AUTH_FAILED", "msg": "密码错误",
                                    "on": "auth.login"}}
"""

import json
import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

PROTOCOL_VERSION = 1

#: 包类型名最大长度，避免客户端用超长字符串刷日志
MAX_TYPE_LEN = 48


class Code(StrEnum):
    """错误码。客户端按 code 做分支，msg 仅用于展示。"""

    BAD_PACKET = "BAD_PACKET"
    UNKNOWN_TYPE = "UNKNOWN_TYPE"
    NOT_AUTHED = "NOT_AUTHED"
    AUTH_FAILED = "AUTH_FAILED"
    NAME_TAKEN = "NAME_TAKEN"
    BAD_FIELD = "BAD_FIELD"
    ALREADY_ONLINE = "ALREADY_ONLINE"
    BANNED = "BANNED"
    NO_LOBBY = "NO_LOBBY"
    LINE_FULL = "LINE_FULL"
    NOT_IN_LOBBY = "NOT_IN_LOBBY"
    NO_MATCH = "NO_MATCH"
    MATCH_FULL = "MATCH_FULL"
    NOT_LEADER = "NOT_LEADER"
    RATE_LIMIT = "RATE_LIMIT"
    TOO_LARGE = "TOO_LARGE"
    INTERNAL = "INTERNAL"


class ProtocolError(Exception):
    """业务/协议错误，被派发器捕获后转成 ``error`` 包返回给客户端。"""

    __slots__ = ("code", "msg")

    def __init__(self, code: Code, msg: str) -> None:
        super().__init__(msg)
        self.code = code
        self.msg = msg


@dataclass(slots=True)
class Packet:
    """一个协议包。"""

    type: str
    data: dict[str, Any] = field(default_factory=dict)
    seq: int | None = None

    # ------------------------------------------------------------ 编解码
    @staticmethod
    def decode(raw: str | bytes) -> "Packet":
        """把 WebSocket 帧解析为 Packet。

        参数:
            raw: 原始文本或字节。

        返回:
            Packet: 解析结果。

        抛出:
            ProtocolError: 格式非法。
        """
        try:
            obj = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise ProtocolError(Code.BAD_PACKET, f"非法 JSON: {exc}") from exc

        match obj:
            case {"t": str() as ptype, **rest} if ptype:
                pass
            case dict():
                raise ProtocolError(Code.BAD_PACKET, "缺少字段 t")
            case _:
                raise ProtocolError(Code.BAD_PACKET, "包必须是 JSON 对象")

        if len(ptype) > MAX_TYPE_LEN:
            raise ProtocolError(Code.BAD_PACKET, "字段 t 过长")

        match rest.get("d"):
            case None:
                data: dict[str, Any] = {}
            case dict() as got:
                data = got
            case _:
                raise ProtocolError(Code.BAD_PACKET, "字段 d 必须是对象")

        match rest.get("seq"):
            case None:
                seq: int | None = None
            case bool():
                raise ProtocolError(Code.BAD_PACKET, "字段 seq 必须是整数")
            case int() as got:
                seq = got
            case _:
                raise ProtocolError(Code.BAD_PACKET, "字段 seq 必须是整数")

        return Packet(type=ptype, data=data, seq=seq)

    def encode(self) -> str:
        """序列化为单行 JSON 文本。

        返回:
            str: JSON 文本。
        """
        obj: dict[str, Any] = {"t": self.type, "d": self.data}
        if self.seq is not None:
            obj["seq"] = self.seq
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

    # ------------------------------------------------------------ 取值助手
    def str_of(self, key: str, *, max_len: int = 64, required: bool = True) -> str:
        """取字符串字段。

        参数:
            key: 字段名。
            max_len: 长度上限。
            required: 是否必填，非必填且缺失时返回空串。

        返回:
            str: 去除首尾空白后的值。

        抛出:
            ProtocolError: 类型或长度不合法。
        """
        match self.data.get(key):
            case None if not required:
                return ""
            case str() as value:
                pass
            case _:
                raise ProtocolError(Code.BAD_FIELD, f"字段 {key} 必须是字符串")

        value = value.strip()
        if required and not value:
            raise ProtocolError(Code.BAD_FIELD, f"字段 {key} 不能为空")
        if len(value) > max_len:
            raise ProtocolError(Code.BAD_FIELD, f"字段 {key} 过长（上限 {max_len}）")
        return value

    def int_of(self, key: str, default: int | None = None) -> int:
        """取整数字段。

        参数:
            key: 字段名。
            default: 缺失时的默认值。

        返回:
            int: 字段值。

        抛出:
            ProtocolError: 类型不合法。
        """
        match self.data.get(key, default):
            case bool() | None:
                raise ProtocolError(Code.BAD_FIELD, f"字段 {key} 必须是整数")
            case int() as value:
                return value
            case _:
                raise ProtocolError(Code.BAD_FIELD, f"字段 {key} 必须是整数")

    def float_of(self, key: str, default: float | None = None) -> float:
        """取浮点字段。

        参数:
            key: 字段名。
            default: 缺失时的默认值。

        返回:
            float: 字段值。

        抛出:
            ProtocolError: 类型不合法或为 NaN/无穷。
        """
        match self.data.get(key, default):
            case bool() | None:
                raise ProtocolError(Code.BAD_FIELD, f"字段 {key} 必须是数字")
            case int() | float() as value:
                result = float(value)
            case _:
                raise ProtocolError(Code.BAD_FIELD, f"字段 {key} 必须是数字")

        # NaN / inf 会污染后续的坐标钳制与统计，直接拒绝
        if not math.isfinite(result):
            raise ProtocolError(Code.BAD_FIELD, f"字段 {key} 不是有效数字")
        return result

    def bool_of(self, key: str, default: bool = False) -> bool:
        """取布尔字段。

        参数:
            key: 字段名。
            default: 缺失时的默认值。

        返回:
            bool: 字段值。
        """
        match self.data.get(key, default):
            case bool() as value:
                return value
            case _:
                raise ProtocolError(Code.BAD_FIELD, f"字段 {key} 必须是布尔值")
