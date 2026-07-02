"""配置查看与修改路由

提供AI插件配置项的脱敏查看与超级用户级修改。
"""

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from liuying.liuying_plugins.AI.config import get_config as get_ai_config
from liuying.liuying_plugins.AI.config import set_config as set_ai_config

from ..deps import require_superuser

__all__ = ["build_config_router"]

# 配置项分组定义（key -> (分组, 类型, help, 是否敏感))
_CONFIG_REGISTRY: list[dict[str, Any]] = [
    {
        "key": "ENABLE_AI",
        "group": "基础",
        "value_type": "bool",
        "help": "是否启用AI对话",
        "secret": False,
    },
    {
        "key": "DEFAULT_PERSONA",
        "group": "基础",
        "value_type": "str",
        "help": "默认人格名",
        "secret": False,
    },
    {
        "key": "MAX_RESPONSE_LENGTH",
        "group": "基础",
        "value_type": "int",
        "help": "最大响应长度",
        "secret": False,
    },
    {
        "key": "HISTORY_LEN",
        "group": "基础",
        "value_type": "int",
        "help": "历史对话窗口长度",
        "secret": False,
    },
    {
        "key": "AGENT_ENABLED",
        "group": "Agent",
        "value_type": "bool",
        "help": "是否启用Agent工具调用",
        "secret": False,
    },
    {
        "key": "AGENT_MAX_STEPS",
        "group": "Agent",
        "value_type": "int",
        "help": "Agent最大循环步数",
        "secret": False,
    },
    {
        "key": "MEMORY_ENABLED",
        "group": "记忆",
        "value_type": "bool",
        "help": "是否启用记忆系统",
        "secret": False,
    },
    {
        "key": "MEMORY_RECALL_TOP_K",
        "group": "记忆",
        "value_type": "int",
        "help": "记忆召回数量",
        "secret": False,
    },
    {
        "key": "MEMORY_DECAY_ENABLED",
        "group": "记忆",
        "value_type": "bool",
        "help": "是否启用记忆衰减",
        "secret": False,
    },
    {
        "key": "TTS_ENABLED",
        "group": "TTS",
        "value_type": "bool",
        "help": "是否启用TTS",
        "secret": False,
    },
    {
        "key": "TTS_AUTO_ENABLED",
        "group": "TTS",
        "value_type": "bool",
        "help": "是否自动TTS",
        "secret": False,
    },
    {
        "key": "SAFETY_FILTER_ENABLED",
        "group": "安全",
        "value_type": "bool",
        "help": "是否启用安全过滤",
        "secret": False,
    },
    {
        "key": "CONTENT_MODERATION_ENABLED",
        "group": "安全",
        "value_type": "bool",
        "help": "是否启用内容审核",
        "secret": False,
    },
    {
        "key": "HUMANIZE_TYPING_ENABLED",
        "group": "拟人化",
        "value_type": "bool",
        "help": "是否启用打字延迟拟人化",
        "secret": False,
    },
    {
        "key": "HUMANIZE_TYPING_CPS",
        "group": "拟人化",
        "value_type": "float",
        "help": "打字速度（字符/秒）",
        "secret": False,
    },
    {
        "key": "HUMANIZE_TYPO_PROBABILITY",
        "group": "拟人化",
        "value_type": "float",
        "help": "错别字注入概率",
        "secret": False,
    },
    {
        "key": "FRAGMENT_STYLE",
        "group": "拟人化",
        "value_type": "str",
        "help": "碎片化输出风格：off或prompt",
        "secret": False,
    },
    {
        "key": "FRAGMENT_MAX_CHARS",
        "group": "拟人化",
        "value_type": "int",
        "help": "碎片化输出单段最大字符数",
        "secret": False,
    },
    {
        "key": "PROACTIVE_ENABLED",
        "group": "主动行为",
        "value_type": "bool",
        "help": "是否启用主动行为",
        "secret": False,
    },
    {
        "key": "PROACTIVE_INTERVAL_MINUTES",
        "group": "主动行为",
        "value_type": "int",
        "help": "主动行为检查间隔（分钟）",
        "secret": False,
    },
    {
        "key": "GROUP_IDLE_MINUTES",
        "group": "主动行为",
        "value_type": "int",
        "help": "群空闲触发阈值（分钟）",
        "secret": False,
    },
    {
        "key": "STICKER_ENABLED",
        "group": "贴纸",
        "value_type": "bool",
        "help": "是否启用贴纸",
        "secret": False,
    },
    {
        "key": "STICKER_PROBABILITY",
        "group": "贴纸",
        "value_type": "float",
        "help": "贴纸触发概率",
        "secret": False,
    },
    {
        "key": "VISION_ENABLED",
        "group": "视觉",
        "value_type": "bool",
        "help": "是否启用图片/GIF/视频理解",
        "secret": False,
    },
    {
        "key": "CHAT_PROVIDER",
        "group": "LLM",
        "value_type": "str",
        "help": "对话模型供应商",
        "secret": True,
    },
    {
        "key": "CHAT_MODEL",
        "group": "LLM",
        "value_type": "str",
        "help": "对话模型名",
        "secret": True,
    },
    {
        "key": "THINKING_MODE_ENABLED",
        "group": "LLM",
        "value_type": "bool",
        "help": "是否开启深度思考请求",
        "secret": False,
    },
    {
        "key": "CONTEXT_COMPRESS_ENABLED",
        "group": "上下文",
        "value_type": "bool",
        "help": "是否启用上下文压缩",
        "secret": False,
    },
    {
        "key": "CONTEXT_MAX_TOKENS",
        "group": "上下文",
        "value_type": "int",
        "help": "上下文压缩token预算",
        "secret": False,
    },
    {
        "key": "GROUP_MUTE_AWARE",
        "group": "群聊",
        "value_type": "bool",
        "help": "是否启用群禁言感知",
        "secret": False,
    },
    {
        "key": "GROUP_QUIET_START",
        "group": "群聊",
        "value_type": "int",
        "help": "群深夜静默开始小时",
        "secret": False,
    },
    {
        "key": "GROUP_QUIET_END",
        "group": "群聊",
        "value_type": "int",
        "help": "群深夜静默结束小时",
        "secret": False,
    },
    {
        "key": "TOKEN_QUOTA_ENABLED",
        "group": "额度",
        "value_type": "bool",
        "help": "是否启用用户对话token额度限制",
        "secret": False,
    },
]
"""配置项注册表（脱敏展示用）"""


def _cast_value(value: Any, value_type: str) -> Any:
    """按类型转换配置值

    参数:
        value: 原始值
        value_type: 目标类型名

    返回:
        Any: 转换后的值

    异常:
        ValueError: 类型转换失败
    """
    if value is None:
        return None
    if value_type == "bool":
        if isinstance(value, bool):
            return value
        return str(value).lower() in ("true", "1", "yes", "on")
    if value_type == "int":
        return int(value)
    if value_type == "float":
        return float(value)
    return str(value)


def build_config_router() -> APIRouter:
    """构建配置管理路由

    Returns:
        APIRouter: 配置管理路由器
    """
    router = APIRouter(prefix="/config", tags=["AI-配置管理"])

    @router.get("")
    async def list_config() -> dict[str, Any]:
        """获取AI插件配置（脱敏）

        返回:
            dict: 配置项列表与分组
        """
        entries: list[dict[str, Any]] = []
        groups: set[str] = set()
        for item in _CONFIG_REGISTRY:
            key = item["key"]
            raw_value = get_ai_config(key, None)
            secret = item["secret"]
            display_value = "***" if (secret and raw_value) else raw_value
            entries.append(
                {
                    "key": key,
                    "value": display_value,
                    "value_type": item["value_type"],
                    "help_text": item["help"],
                    "secret": secret,
                    "group": item["group"],
                }
            )
            groups.add(item["group"])
        return {
            "entries": entries,
            "groups": sorted(groups),
        }

    @router.post("/value")
    async def update_value(
        body: dict = Body(default_factory=dict),
        _: None = Depends(require_superuser),
    ) -> dict[str, Any]:
        """修改单个配置项

        参数:
            body: 包含 key 和 value 的请求体

        返回:
            dict: 操作结果
        """
        key = str(body.get("key", "")).strip().upper()
        value = body.get("value")
        if not key:
            raise HTTPException(
                status_code=400, detail="key 不能为空"
            )
        entry = next(
            (e for e in _CONFIG_REGISTRY if e["key"] == key),
            None,
        )
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail=f"未知配置项: {key}",
            )
        try:
            normalized = _cast_value(value, entry["value_type"])
        except ValueError as e:
            raise HTTPException(
                status_code=400, detail=f"取值非法: {e}"
            ) from e
        set_ai_config(key, normalized, auto_save=True)
        return {
            "ok": True,
            "key": key,
            "new_value": "***" if entry["secret"] else normalized,
        }

    return router
