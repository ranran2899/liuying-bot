"""QQ机器人配置业务逻辑

依赖单向:
- _adapter (适配器同步)
- _monitor (重连监控,通过注册回调避免循环依赖)
- _intent (意图字段)
- Config (项目配置访问)
"""

import json
from typing import Any

from liuying.configs.config import Config
from liuying.models._bot.qq_bot_config import QQBotConfig
from liuying.models._user import UserLevel
from liuying.services.cache import Cache
from liuying.utils.log import logger

from ._adapter import QQAdapterManager, build_bot_info
from ._intent import (
    DEFAULT_INTENT,
    INTENT_DESCRIPTIONS,
    VALID_INTENT_FIELDS,
)
from ._monitor import ReconnectMonitor

_CONFIG_MODULE = "qq_bot_config"
"""配置模块名"""

_DIRECT_FIELDS = frozenset(
    {"bot_name", "use_websocket", "is_sandbox", "status", "remark"}
)
"""直接配置字段(无需特殊处理的字段)"""


def _config_to_dict(c: QQBotConfig) -> dict[str, Any]:
    """将QQBotConfig模型转换为字典

    参数:
        c: QQBotConfig模型实例

    返回:
        dict[str, Any]: 转换后的字典
    """
    return {
        "id": c.id,
        "user_id": c.user_id,
        "bot_id": c.bot_id,
        "bot_name": c.bot_name,
        "token": c.token,
        "secret": c.secret,
        "intent": json.loads(c.intent),
        "use_websocket": c.use_websocket,
        "is_sandbox": c.is_sandbox,
        "status": c.status,
        "create_time": c.create_time.isoformat() if c.create_time else None,
        "update_time": c.update_time.isoformat() if c.update_time else None,
        "remark": c.remark,
    }


def _build_cache_key(user_id: str, bot_id: str) -> dict[str, str]:
    """构造缓存键

    参数:
        user_id: 用户ID
        bot_id: 机器人ID

    返回:
        dict[str, str]: 缓存键字典
    """
    return {"user_id": user_id, "bot_id": bot_id}


class QQBotConfigManager:
    """QQ机器人配置业务管理器

    负责配置的增删改查业务逻辑,通过 QQAdapterManager 与适配器交互,
    通过 ReconnectMonitor 注册回调实现自动删除保护
    """

    _cache: Cache[dict[str, Any]] = Cache(
        "QQ_BOT_CONFIG", result_type=dict
    )
    """配置缓存"""

    @staticmethod
    def _validate_credential(name: str, value: str) -> tuple[bool, str]:
        """验证凭据字段(Token/Secret)

        参数:
            name: 字段名称
            value: 字段值

        返回:
            tuple[bool, str]: (是否有效, 错误信息)
        """
        min_len = int(
            Config.get_config(_CONFIG_MODULE, "CREDENTIAL_MIN_LEN") or 10
        )
        if not value:
            return False, f"{name}不能为空"
        if len(value) < min_len:
            return False, f"{name}长度不足"
        return True, ""

    @staticmethod
    def _validate_bot_id(bot_id: str) -> tuple[bool, str]:
        """验证机器人ID

        参数:
            bot_id: 机器人ID

        返回:
            tuple[bool, str]: (是否有效, 错误信息)
        """
        if not bot_id:
            return False, "机器人ID不能为空"
        if not bot_id.isdigit():
            return False, "机器人ID必须为纯数字"
        min_len = int(
            Config.get_config(_CONFIG_MODULE, "BOT_ID_MIN_LEN") or 5
        )
        max_len = int(
            Config.get_config(_CONFIG_MODULE, "BOT_ID_MAX_LEN") or 20
        )
        if not min_len <= len(bot_id) <= max_len:
            return False, f"机器人ID长度必须在{min_len}-{max_len}位之间"
        return True, ""

    @staticmethod
    def _validate_intent(intent: dict[str, bool]) -> tuple[bool, str]:
        """验证意图配置

        参数:
            intent: 意图配置字典

        返回:
            tuple[bool, str]: (是否有效, 错误信息)
        """
        for key, val in intent.items():
            if key not in VALID_INTENT_FIELDS:
                return False, f"无效的意图字段: {key}"
            if not isinstance(val, bool):
                return False, f"意图字段 {key} 必须为布尔值"
        return True, ""

    @classmethod
    async def add_config(
        cls,
        user_id: str,
        bot_id: str,
        token: str,
        secret: str,
        intent: dict[str, bool],
        bot_name: str | None = None,
        use_websocket: bool = True,
        is_sandbox: bool = False,
        remark: str | None = None,
    ) -> tuple[bool, str]:
        """添加QQ机器人配置

        参数:
            user_id: 用户ID
            bot_id: 机器人ID
            token: 机器人Token
            secret: 机器人Secret
            intent: 意图配置
            bot_name: 机器人名称
            use_websocket: 是否使用WebSocket
            is_sandbox: 是否为沙箱环境
            remark: 备注信息

        返回:
            tuple[bool, str]: (是否成功, 消息)
        """
        for valid, msg in [
            cls._validate_bot_id(bot_id),
            cls._validate_credential("Token", token),
            cls._validate_credential("Secret", secret),
            cls._validate_intent(intent),
        ]:
            if not valid:
                return False, msg

        max_configs = int(
            Config.get_config(_CONFIG_MODULE, "MAX_BOT_COUNT") or 5
        )
        count = await QQBotConfig.count_user_configs(user_id)
        if count >= max_configs:
            return False, f"已达到最大配置数量限制({max_configs}个)"

        if await QQBotConfig.check_bot_id_global_exists(bot_id):
            return False, f"机器人ID {bot_id} 已被其他用户添加,不可重复配置"

        config = await QQBotConfig.create_config(
            user_id=user_id,
            bot_id=bot_id,
            bot_name=bot_name,
            token=token,
            secret=secret,
            intent=json.dumps(intent, ensure_ascii=False),
            use_websocket=use_websocket,
            is_sandbox=is_sandbox,
            remark=remark,
        )

        config_dict = _config_to_dict(config)
        await cls._cache.set(_build_cache_key(user_id, bot_id), config_dict)

        if config.status:
            try:
                QQAdapterManager.sync_to_adapter(
                    build_bot_info(config_dict)
                )
            except Exception as e:
                logger.error(
                    f"同步到适配器失败: {e}", "QQBotConfig", e=e
                )

        bot_level = int(
            Config.get_config(_CONFIG_MODULE, "BOT_LEVEL") or 7
        )
        await UserLevel.set_bot_level(bot_id, user_id, bot_level)

        logger.info(f"用户 {user_id} 添加QQ机器人配置: {bot_id}")
        return True, f"成功添加机器人配置: {bot_id}"

    @classmethod
    async def get_config(
        cls, user_id: str, bot_id: str
    ) -> dict[str, Any] | None:
        """获取单个QQ机器人配置

        参数:
            user_id: 用户ID
            bot_id: 机器人ID

        返回:
            dict[str, Any] | None: 配置字典, 不存在返回None
        """
        return await cls._cache.get_or_load(
            _build_cache_key(user_id, bot_id),
            loader=lambda: cls._load_config(user_id, bot_id),
        )

    @classmethod
    async def _load_config(
        cls, user_id: str, bot_id: str
    ) -> dict[str, Any] | None:
        """从数据库加载配置(供缓存加载器调用)

        参数:
            user_id: 用户ID
            bot_id: 机器人ID

        返回:
            dict[str, Any] | None: 配置字典, 不存在返回None
        """
        config = await QQBotConfig.get_config_by_bot_id(user_id, bot_id)
        return _config_to_dict(config) if config else None

    @classmethod
    async def get_user_configs(
        cls, user_id: str
    ) -> list[dict[str, Any]]:
        """获取用户的所有QQ机器人配置

        参数:
            user_id: 用户ID

        返回:
            list[dict[str, Any]]: 配置字典列表
        """
        configs = await QQBotConfig.get_user_configs(user_id)
        return [_config_to_dict(c) for c in configs]

    @classmethod
    async def get_all_active_configs(cls) -> list[dict[str, Any]]:
        """获取所有启用的QQ机器人配置

        返回:
            list[dict[str, Any]]: 启用状态的配置字典列表
        """
        configs = await QQBotConfig.filter(status=True).all()
        return [_config_to_dict(c) for c in configs]

    @classmethod
    async def update_config(
        cls, user_id: str, bot_id: str, **kwargs: Any
    ) -> tuple[bool, str]:
        """更新QQ机器人配置

        参数:
            user_id: 用户ID
            bot_id: 机器人ID
            **kwargs: 要更新的字段

        返回:
            tuple[bool, str]: (是否成功, 消息)
        """
        if not await QQBotConfig.check_bot_id_exists(user_id, bot_id):
            return False, f"机器人配置 {bot_id} 不存在"

        update_data: dict[str, Any] = {}

        for field in ("token", "secret"):
            if field in kwargs:
                valid, msg = cls._validate_credential(
                    field.capitalize(), kwargs[field]
                )
                if not valid:
                    return False, msg
                update_data[field] = kwargs[field]

        if "intent" in kwargs:
            valid, msg = cls._validate_intent(kwargs["intent"])
            if not valid:
                return False, msg
            update_data["intent"] = json.dumps(
                kwargs["intent"], ensure_ascii=False
            )

        for field in _DIRECT_FIELDS:
            if field in kwargs:
                update_data[field] = kwargs[field]

        if not update_data:
            return False, "没有需要更新的字段"

        success = await QQBotConfig.update_config(
            user_id, bot_id, **update_data
        )
        if not success:
            return False, "更新配置失败"

        cache_key = _build_cache_key(user_id, bot_id)
        await cls._cache.delete(cache_key)

        config = await cls.get_config(user_id, bot_id)
        if config:
            try:
                if config.get("status", True):
                    QQAdapterManager.sync_to_adapter(
                        build_bot_info(config)
                    )
                else:
                    QQAdapterManager.remove_from_adapter(bot_id)
            except Exception as e:
                logger.error(
                    f"同步适配器状态失败: {e}", "QQBotConfig", e=e
                )

        logger.info(f"用户 {user_id} 更新配置: {bot_id}")
        return True, f"成功更新机器人配置: {bot_id}"

    @classmethod
    async def delete_config(
        cls, user_id: str, bot_id: str
    ) -> tuple[bool, str]:
        """删除QQ机器人配置

        参数:
            user_id: 用户ID
            bot_id: 机器人ID

        返回:
            tuple[bool, str]: (是否成功, 消息)
        """
        if not await QQBotConfig.check_bot_id_exists(user_id, bot_id):
            return False, f"机器人配置 {bot_id} 不存在"

        QQAdapterManager.remove_from_adapter(bot_id)
        success = await QQBotConfig.delete_config(user_id, bot_id)
        if not success:
            return False, "删除配置失败"

        await cls._cache.delete(_build_cache_key(user_id, bot_id))
        await UserLevel.delete_bot_level(bot_id, user_id)
        ReconnectMonitor.on_connected(bot_id)
        logger.info(f"用户 {user_id} 删除配置: {bot_id}")
        return True, f"成功删除机器人配置: {bot_id}"

    @staticmethod
    def get_default_intent() -> dict[str, bool]:
        """获取默认意图配置

        返回:
            dict[str, bool]: 默认意图配置字典
        """
        return DEFAULT_INTENT.copy()

    @staticmethod
    def get_intent_fields() -> dict[str, str]:
        """获取所有可用的意图字段及描述

        返回:
            dict[str, str]: 字段名到描述的映射
        """
        return INTENT_DESCRIPTIONS.copy()

    @classmethod
    async def get_intent(
        cls, user_id: str, bot_id: str
    ) -> dict[str, bool] | None:
        """获取机器人的意图配置

        参数:
            user_id: 用户ID
            bot_id: 机器人ID

        返回:
            dict[str, bool] | None: 意图配置, 不存在返回None
        """
        config = await cls.get_config(user_id, bot_id)
        if config is None:
            return None
        return config.get("intent", cls.get_default_intent())

    @classmethod
    async def update_intent(
        cls, user_id: str, bot_id: str, field: str, value: bool
    ) -> tuple[bool, str]:
        """更新单个意图字段

        参数:
            user_id: 用户ID
            bot_id: 机器人ID
            field: 意图字段名
            value: 字段值

        返回:
            tuple[bool, str]: (是否成功, 消息)
        """
        if field not in VALID_INTENT_FIELDS:
            available = ", ".join(VALID_INTENT_FIELDS)
            return False, f"无效的意图字段: {field}\n可用字段: {available}"

        config = await cls.get_config(user_id, bot_id)
        if config is None:
            return False, f"机器人配置 {bot_id} 不存在"

        intent = config.get("intent", cls.get_default_intent())
        if intent.get(field) == value:
            return True, f"意图字段 {field} 已为{'启用' if value else '禁用'}"

        intent[field] = value
        return await cls.update_config(user_id, bot_id, intent=intent)

    @classmethod
    async def reset_intent(
        cls, user_id: str, bot_id: str
    ) -> tuple[bool, str]:
        """重置意图配置为默认值

        参数:
            user_id: 用户ID
            bot_id: 机器人ID

        返回:
            tuple[bool, str]: (是否成功, 消息)
        """
        return await cls.update_config(
            user_id, bot_id, intent=cls.get_default_intent()
        )

    @classmethod
    async def export_to_env_format(
        cls, user_id: str
    ) -> str | None:
        """导出用户配置为环境变量格式

        参数:
            user_id: 用户ID

        返回:
            str | None: JSON格式字符串, 无配置时返回None
        """
        configs = await cls.get_user_configs(user_id)
        if not configs:
            return None
        return json.dumps(
            [
                {
                    "id": c["bot_id"],
                    "token": c["token"],
                    "secret": c["secret"],
                    "intent": c["intent"],
                    "use_websocket": c["use_websocket"],
                }
                for c in configs
            ],
            ensure_ascii=False,
            indent=2,
        )

    @classmethod
    async def load_configs_to_adapter(cls) -> tuple[int, int]:
        """加载所有启用配置到QQ适配器

        仅将配置添加到适配器的qq_bots列表,不主动启动WebSocket连接。
        适配器startup会遍历qq_bots自动启动连接,避免重复启动。

        返回:
            tuple[int, int]: (成功数量, 失败数量)
        """
        configs = await cls.get_all_active_configs()
        if not configs:
            return 0, 0

        adapter = QQAdapterManager._get_adapter()
        existing_ids = {b.id for b in adapter.qq_config.qq_bots}
        success = fail = 0

        for config in configs:
            if config["bot_id"] in existing_ids:
                success += 1
                continue
            try:
                QQAdapterManager.add_bot_to_config(
                    build_bot_info(config)
                )
                success += 1
            except Exception:
                fail += 1

        return success, fail


# 注册自动删除回调,消除循环依赖
ReconnectMonitor.register_delete_callback(QQBotConfigManager.delete_config)
