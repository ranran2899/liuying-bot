"""环境感知（Peer Awareness）

识别群内其他 bot 并在它们发言时静默，避免 bot 互相对话。
同时收集其他 NoneBot 插件清单，注入系统提示避免 AI 将
其他插件功能说成自己的能力。支持配置其他 bot 的 ID 列表。
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import re

from liuying.utils.log import logger

from ..config import get_config

_CJK_BOT_NAME_HINTS: tuple[str, ...] = (
    "机器人",
    "助手",
    "小助手",
    "管家",
)
"""CJK多字提示词（子串匹配）

单字提示词（如「酱」）已移除：会把「番茄酱」等普通用户
昵称误判为 bot，触发 30 秒群静默。
"""

_ASCII_HINT_RE: re.Pattern[str] = re.compile(
    r"(?:^|[^a-z])(?:bot|chan|kun)(?:[^a-z]|$)",
    re.IGNORECASE,
)
"""ASCII提示词（bot/chan/kun）词边界正则

需作为独立词出现才命中（首尾或两侧为非字母），
避免子串误伤普通昵称（如 Chandler 含 chan、
kunlun 含 kun）。IGNORECASE 下 [^a-z] 同时排除
大小写字母，即完整词边界语义。
"""

_BOT_MESSAGE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\[AI\]"),
    re.compile(r"^AI[:：]"),
    re.compile(r"^Bot[:：]"),
    re.compile(r"^<bot>"),
    re.compile(r"命令执行结果[:：]"),
    re.compile(r"^查询结果[:：]"),
)
"""其他bot消息特征正则模式"""

_SILENCE_AFTER_PEER_SECONDS = 30.0
"""检测到其他bot发言后的静默秒数"""

_MAX_KNOWN_PEERS = 50
"""最多记录的其他bot数量"""


@dataclass(slots=True)
class PeerBotInfo:
    """其他bot信息

    Attributes:
        user_id: bot用户ID
        group_id: 所在群组ID
        name: bot名称（如已知）
        last_spoke: 最后发言时间
        speak_count: 发言次数
    """

    user_id: str
    group_id: str
    name: str = ""
    last_spoke: datetime = field(
        default_factory=datetime.now
    )
    speak_count: int = 1


class PeerAwareness:
    """环境感知管理器

    识别其他bot并控制静默，收集其他插件能力清单。
    """

    def __init__(self) -> None:
        """初始化环境感知管理器"""
        self._known_peers: dict[str, PeerBotInfo] = {}
        """已知其他bot（key=user_id|group_id）"""
        self._silence_until: dict[str, datetime] = {}
        """群组静默截止时间（key=group_id）"""
        self._parsed_ids: tuple[str, frozenset[str]] = (
            "",
            frozenset(),
        )
        """配置的peer ID缓存（原始串与解析集合）"""

    def is_peer_bot(
        self,
        user_id: str,
        text: str,
        group_id: str,
        nickname: str = "",
    ) -> bool:
        """判断消息是否来自其他bot

        优先检查配置的 peer_bot_ids，其次使用启发式判断。

        参数:
            user_id: 用户ID
            text: 消息文本
            group_id: 群组ID
            nickname: 用户昵称（可选）

        返回:
            bool: 是否为其他bot
        """
        configured = str(get_config("PEER_BOT_IDS", "") or "")
        if configured:
            raw, peer_ids = self._parsed_ids
            if raw != configured:
                peer_ids = frozenset(
                    uid.strip()
                    for uid in configured.split(",")
                    if uid.strip()
                )
                self._parsed_ids = (configured, peer_ids)
            if user_id in peer_ids:
                self._record_peer(user_id, group_id, nickname)
                return True
        if self._heuristic_is_bot(text, nickname):
            self._record_peer(user_id, group_id, nickname)
            return True
        return False

    def should_silence(
        self, group_id: str
    ) -> bool:
        """检查当前群组是否应保持静默

        参数:
            group_id: 群组ID

        返回:
            bool: 是否应静默
        """
        silence_time = self._silence_until.get(group_id)
        if silence_time and silence_time > datetime.now():
            return True
        if silence_time and silence_time <= datetime.now():
            self._silence_until.pop(group_id, None)
        return False

    def trigger_silence(
        self, group_id: str
    ) -> None:
        """触发群组静默（检测到其他bot发言后）

        参数:
            group_id: 群组ID
        """
        self._silence_until[group_id] = datetime.now() + timedelta(
            seconds=_SILENCE_AFTER_PEER_SECONDS
        )
        logger.debug(
            f"检测到其他bot发言，触发静默: group={group_id}",
            command="AI",
        )

    def get_known_peers(
        self, group_id: str | None = None
    ) -> list[PeerBotInfo]:
        """获取已知的其他bot列表

        参数:
            group_id: 群组ID，None时返回全部

        返回:
            list[PeerBotInfo]: 已知bot列表
        """
        if group_id is None:
            return list(self._known_peers.values())
        return [
            info
            for info in self._known_peers.values()
            if info.group_id == group_id
        ]

    def build_peer_awareness_prompt(self) -> str:
        """构建环境感知提示词（注入系统提示）

        提示AI不要将其他插件/其他bot的功能说成自己的能力。

        返回:
            str: 提示词文本
        """
        lines: list[str] = [
            "\n[环境感知]",
            "本机器人由多个独立插件组成，你只是其中的AI对话插件。",
            "其他插件（如签到/抽签/天气）是独立功能，",
            "不要将这些功能说成你自己的能力。",
            "当用户询问这些功能时，引导用户使用对应命令。",
        ]
        peer_count = len(self._known_peers)
        if peer_count > 0:
            lines.append(
                f"群内检测到 {peer_count} 个其他bot，"
                "避免与其他bot互相对话。"
            )
        return "\n".join(lines)

    @staticmethod
    def _heuristic_is_bot(
        text: str, nickname: str
    ) -> bool:
        """启发式判断是否为bot消息

        昵称匹配分两类：
        - CJK多字提示词（机器人/助手/管家）按子串匹配；
        - ASCII提示词（bot/chan/kun）按词边界匹配，
          避免误伤 Chandler（chan 子串）、kunlun（kun 子串）
          等普通昵称；单字「酱」已移除，避免误伤「番茄酱」。

        参数:
            text: 消息文本
            nickname: 用户昵称

        返回:
            bool: 是否疑似bot
        """
        if not text:
            return False
        for pattern in _BOT_MESSAGE_PATTERNS:
            if pattern.search(text):
                return True
        if nickname:
            for hint in _CJK_BOT_NAME_HINTS:
                if hint in nickname:
                    return True
            if _ASCII_HINT_RE.search(nickname):
                return True
        return False

    def _record_peer(
        self,
        user_id: str,
        group_id: str,
        name: str,
    ) -> None:
        """记录其他bot信息

        参数:
            user_id: bot用户ID
            group_id: 所在群组ID
            name: bot名称
        """
        key = f"{user_id}|{group_id}"
        existing = self._known_peers.get(key)
        if existing:
            existing.last_spoke = datetime.now()
            existing.speak_count += 1
            if name and not existing.name:
                existing.name = name
        else:
            if len(self._known_peers) >= _MAX_KNOWN_PEERS:
                oldest_key = min(
                    self._known_peers,
                    key=lambda k: self._known_peers[
                        k
                    ].last_spoke,
                )
                self._known_peers.pop(oldest_key, None)
            self._known_peers[key] = PeerBotInfo(
                user_id=user_id,
                group_id=group_id,
                name=name,
            )


peer_awareness = PeerAwareness()
"""环境感知管理器单例"""
