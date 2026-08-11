"""服务器配置。

作为 liuying-bot 插件运行时，配置项由 liuying 的 `Config`（`data/configs/plugins2config.yaml`）
统一管理，可用机器人指令「修改配置 mgga_server LOBBY_CAPACITY 40」在线调整；
若脱离 liuying 单独运行，则回落到 NoneBot `.env` 中的 `GAME_*` 项。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

#: liuying 配置模块名（即插件包名）
MODULE = "mgga_server"


class GameConfig(BaseModel):
    """游戏服务器配置。"""

    game_ws_path: str = "/game"
    """WebSocket 接入路径。"""

    game_lobby_capacity: int = Field(default=30, ge=2, le=200)
    """单条线路最大同框人数，超过后自动开新线。"""

    game_lobby_tick_rate: int = Field(default=10, ge=1, le=30)
    """大厅状态广播频率（Hz）。"""

    game_heartbeat_timeout: float = Field(default=30.0, gt=0)
    """心跳超时（秒）。"""

    game_db_path: str = "data/mgga_server/accounts.db"
    """账号数据库路径（相对机器人工作目录）。"""

    game_token_ttl: int = Field(default=7 * 24 * 3600, gt=0)
    """登录令牌有效期（秒）。"""

    game_match_capacity: int = Field(default=5, ge=1, le=16)
    """单局对局最大人数。"""


#: liuying 配置键 -> GameConfig 字段名
CONFIG_KEYS: dict[str, str] = {
    "WS_PATH": "game_ws_path",
    "LOBBY_CAPACITY": "game_lobby_capacity",
    "LOBBY_TICK_RATE": "game_lobby_tick_rate",
    "HEARTBEAT_TIMEOUT": "game_heartbeat_timeout",
    "DB_PATH": "game_db_path",
    "TOKEN_TTL": "game_token_ttl",
    "MATCH_CAPACITY": "game_match_capacity",
}


def load_config() -> GameConfig:
    """优先读 liuying 配置，缺失时回落 .env，再回落默认值。"""
    values: dict[str, Any] = {}

    try:  # liuying-bot 环境
        from liuying.configs.config import Config  # type: ignore

        for key, field in CONFIG_KEYS.items():
            got = Config.get_config(MODULE, key, None)
            if got is not None:
                values[field] = got
    except Exception:  # pragma: no cover - 脱离 liuying 单独运行
        pass

    try:  # .env 中的 GAME_* 兜底
        from nonebot import get_driver

        env = get_driver().config.model_dump()
        for field in CONFIG_KEYS.values():
            if field not in values and env.get(field) is not None:
                values[field] = env[field]
    except Exception:  # pragma: no cover
        pass

    return GameConfig(**values)
