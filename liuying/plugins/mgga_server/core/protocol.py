"""通信协议定义。

传输层为 WebSocket 文本帧，载荷为单行 JSON：

    {"t": "<包类型>", "seq": <可选的请求序号>, "d": {<数据>}}

服务端对「请求包」的应答会原样带回 `seq`，客户端据此把回包对上请求；
服务端主动推送的广播包不带 `seq`。错误统一用 `error` 包返回：

    {"t": "error", "seq": 12, "d": {"code": "AUTH_FAILED", "msg": "密码错误", "on": "auth.login"}}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

PROTOCOL_VERSION = 1


class Code:
    """错误码常量。客户端按 code 做分支，msg 仅用于展示。"""

    BAD_PACKET = "BAD_PACKET"
    UNKNOWN_TYPE = "UNKNOWN_TYPE"
    NOT_AUTHED = "NOT_AUTHED"
    AUTH_FAILED = "AUTH_FAILED"
    NAME_TAKEN = "NAME_TAKEN"
    BAD_FIELD = "BAD_FIELD"
    ALREADY_ONLINE = "ALREADY_ONLINE"
    NO_LOBBY = "NO_LOBBY"
    LINE_FULL = "LINE_FULL"
    NOT_IN_LOBBY = "NOT_IN_LOBBY"
    NO_MATCH = "NO_MATCH"
    MATCH_FULL = "MATCH_FULL"
    NOT_LEADER = "NOT_LEADER"
    RATE_LIMIT = "RATE_LIMIT"
    INTERNAL = "INTERNAL"


@dataclass(slots=True)
class Packet:
    """一个协议包。"""

    type: str
    data: dict[str, Any] = field(default_factory=dict)
    seq: int | None = None

    # ------------------------------------------------------------ 编解码
    @staticmethod
    def decode(raw: str | bytes) -> "Packet":
        """把 WebSocket 文本帧解析为 Packet；格式非法时抛 ProtocolError。"""
        try:
            obj = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise ProtocolError(Code.BAD_PACKET, f"非法 JSON: {exc}") from exc
        if not isinstance(obj, dict):
            raise ProtocolError(Code.BAD_PACKET, "包必须是 JSON 对象")
        ptype = obj.get("t")
        if not isinstance(ptype, str) or not ptype:
            raise ProtocolError(Code.BAD_PACKET, "缺少字段 t")
        data = obj.get("d") or {}
        if not isinstance(data, dict):
            raise ProtocolError(Code.BAD_PACKET, "字段 d 必须是对象")
        seq = obj.get("seq")
        if seq is not None and not isinstance(seq, int):
            raise ProtocolError(Code.BAD_PACKET, "字段 seq 必须是整数")
        return Packet(type=ptype, data=data, seq=seq)

    def encode(self) -> str:
        obj: dict[str, Any] = {"t": self.type, "d": self.data}
        if self.seq is not None:
            obj["seq"] = self.seq
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

    # ------------------------------------------------------------ 取值助手
    def str_of(self, key: str, *, max_len: int = 64, required: bool = True) -> str:
        value = self.data.get(key)
        if value is None and not required:
            return ""
        if not isinstance(value, str):
            raise ProtocolError(Code.BAD_FIELD, f"字段 {key} 必须是字符串")
        value = value.strip()
        if required and not value:
            raise ProtocolError(Code.BAD_FIELD, f"字段 {key} 不能为空")
        if len(value) > max_len:
            raise ProtocolError(Code.BAD_FIELD, f"字段 {key} 过长（上限 {max_len}）")
        return value

    def int_of(self, key: str, default: int | None = None) -> int:
        value = self.data.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ProtocolError(Code.BAD_FIELD, f"字段 {key} 必须是整数")
        return value

    def float_of(self, key: str, default: float | None = None) -> float:
        value = self.data.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ProtocolError(Code.BAD_FIELD, f"字段 {key} 必须是数字")
        return float(value)


class ProtocolError(Exception):
    """业务/协议错误。被派发器捕获后转成 `error` 包返回给客户端。"""

    def __init__(self, code: str, msg: str) -> None:
        super().__init__(msg)
        self.code = code
        self.msg = msg
