"""服务器配置。

配置项由 liuying 的 ``Config``（``data/configs/plugins2config.yaml``）统一管理，
可用机器人指令「修改配置 mgga_server LOBBY_CAPACITY 40」在线调整；缺失时回落到
NoneBot ``.env`` 中的 ``GAME_*`` 项，最后回落字段默认值。
"""

from typing import Any

from nonebot import get_driver
from pydantic import BaseModel, Field

from liuying.configs.config import Config
from liuying.utils.log import logger

#: liuying 配置模块名（即插件包名）
MODULE = "mgga_server"


class GameConfig(BaseModel):
    """游戏服务器配置。"""

    game_ws_path: str = "/game"
    """WebSocket 接入路径。"""

    game_lobby_capacity: int = Field(default=30, ge=2, le=200)
    """单条线路最大同框人数，超过后自动开新线。"""

    game_lobby_max_lines: int = Field(default=20, ge=1, le=200)
    """单张大厅地图允许存在的最大线路数，防止客户端刷线路号撑爆内存。"""

    game_lobby_tick_rate: int = Field(default=10, ge=1, le=30)
    """大厅状态广播频率（Hz）。"""

    game_heartbeat_timeout: float = Field(default=30.0, gt=0)
    """心跳超时（秒）。"""

    game_token_ttl_days: int = Field(default=7, ge=1, le=365)
    """登录令牌有效期（天）。"""

    game_match_capacity: int = Field(default=5, ge=1, le=16)
    """单局对局最大人数。"""

    game_match_max_seconds: float = Field(default=3600.0, gt=0)
    """单局最长时长（秒），用于结算防作弊钳制与僵尸房间回收。"""

    game_max_packet_bytes: int = Field(default=8192, ge=256, le=1 << 20)
    """单个数据包最大字节数，超出直接断开。"""

    game_packet_rate: int = Field(default=60, ge=5, le=1000)
    """单连接每秒允许的最大包数，超出直接断开。"""

    def refresh(self) -> None:
        """就地重载配置，使运行中的模块无需重新绑定引用即可读到新值。"""
        for name, value in load_config().model_dump().items():
            setattr(self, name, value)


#: liuying 配置键 -> GameConfig 字段名
CONFIG_KEYS: dict[str, str] = {
    "WS_PATH": "game_ws_path",
    "LOBBY_CAPACITY": "game_lobby_capacity",
    "LOBBY_MAX_LINES": "game_lobby_max_lines",
    "LOBBY_TICK_RATE": "game_lobby_tick_rate",
    "HEARTBEAT_TIMEOUT": "game_heartbeat_timeout",
    "TOKEN_TTL_DAYS": "game_token_ttl_days",
    "MATCH_CAPACITY": "game_match_capacity",
    "MATCH_MAX_SECONDS": "game_match_max_seconds",
    "MAX_PACKET_BYTES": "game_max_packet_bytes",
    "PACKET_RATE": "game_packet_rate",
}


def load_config() -> GameConfig:
    """读取配置：liuying 配置优先，其次 ``.env``，最后字段默认值。

    返回:
        GameConfig: 组装好的配置对象。
    """
    values: dict[str, Any] = {}
    for key, field in CONFIG_KEYS.items():
        if (got := Config.get_config(MODULE, key, None)) is not None:
            values[field] = got

    env = get_driver().config.model_dump()
    for field in CONFIG_KEYS.values():
        if field not in values and env.get(field) is not None:
            values[field] = env[field]

    try:
        return GameConfig(**values)
    except ValueError as exc:
        # 用户可能在线改出越界值，此时退回默认配置而不是让整个服务起不来
        logger.error(f"[mgga_server] 配置校验失败，已回落默认配置：{exc}")
        return GameConfig()
