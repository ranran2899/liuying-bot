"""QQ机器人配置管理业务逻辑"""

import asyncio
import json
from typing import Any

import nonebot
from nonebot.adapters.qq.config import BotInfo, Intents

from liuying.configs.config import Config
from liuying.models._bot.qq_bot_config import QQBotConfig
from liuying.models._user import UserLevel
from liuying.services.cache import Cache
from liuying.utils.log import logger

from ._intent import (
    DEFAULT_INTENT,
    INTENT_DESCRIPTIONS,
    VALID_INTENT_FIELDS,
)
from ._monitor import ReconnectMonitor

_DIRECT_FIELDS = frozenset(
    {"bot_name", "use_websocket", "is_sandbox", "status", "remark"}
)
"""直接配置字段"""

_adapter_instance: Any | None = None
"""QQ适配器单例"""


def _get_adapter() -> Any:
    """获取QQ适配器实例(延迟初始化)

    返回:
        Any: QQ适配器实例
    """
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = nonebot.get_adapter("QQ")
    return _adapter_instance


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


class QQBotConfigManager:
    """QQ机器人配置管理器"""

    MAX_CONFIGS_PER_USER = (
        Config.get_config("qq_bot_config", "MAX_BOT_COUNT") or 5
    )
    """每用户最大配置数量"""

    _cache: Cache[dict[str, Any]] = Cache(
        "QQ_BOT_CONFIG", result_type=dict
    )
    """配置缓存"""

    @staticmethod
    def _validate_credential(
        name: str, value: str, min_len: int = 10
    ) -> tuple[bool, str]:
        """验证凭据字段(Token/Secret)

        参数:
            name: 字段名称
            value: 字段值
            min_len: 最小长度要求

        返回:
            tuple[bool, str]: (是否有效, 错误信息)
        """
        if not value:
            return False, f"{name}不能为空"
        if len(value) < min_len:
            return False, f"{name}长度不足"
        return True, ""

    @classmethod
    def _validate_bot_id(cls, bot_id: str) -> tuple[bool, str]:
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
        if not 5 <= len(bot_id) <= 20:
            return False, "机器人ID长度必须在5-20位之间"
        return True, ""

    @classmethod
    def _validate_intent(
        cls, intent: dict[str, bool]
    ) -> tuple[bool, str]:
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

    @staticmethod
    def _build_bot_info(config: dict[str, Any]) -> BotInfo:
        """从配置字典构建BotInfo对象

        参数:
            config: 配置字典

        返回:
            BotInfo: QQ适配器BotInfo对象
        """
        return BotInfo(
            id=config["bot_id"],
            token=config["token"],
            secret=config["secret"],
            intent=Intents(**config.get("intent", {})),
            use_websocket=config.get("use_websocket", True),
        )

    @classmethod
    def _add_bot_to_config(cls, bot_info: BotInfo) -> bool:
        """将机器人配置添加到QQ适配器配置列表(不启动连接)

        用于启动阶段,由适配器startup自动遍历qq_bots启动连接

        参数:
            bot_info: BotInfo对象

        返回:
            bool: 是否添加成功
        """
        adapter = _get_adapter()
        existing_ids = {b.id for b in adapter.qq_config.qq_bots}
        if bot_info.id in existing_ids:
            return True
        adapter.qq_config.qq_bots.append(bot_info)
        logger.info(f"已将机器人 {bot_info.id} 添加到QQ适配器配置列表")
        return True

    @classmethod
    def _start_websocket(cls, bot_info: BotInfo) -> None:
        """启动机器人的WebSocket连接

        参数:
            bot_info: BotInfo对象
        """
        adapter = _get_adapter()
        task = asyncio.create_task(adapter.run_bot_websocket(bot_info))
        task.add_done_callback(adapter.tasks.discard)
        adapter.tasks.add(task)
        logger.info(f"已启动机器人 {bot_info.id} 的WebSocket连接")

    @classmethod
    def _disconnect_bot(cls, bot_id: str) -> None:
        """断开机器人连接并取消所有相关任务

        同时处理已连接和从未连接成功的机器人,取消其所有
        WebSocket转发任务以停止无限重试

        参数:
            bot_id: 机器人ID
        """
        adapter = _get_adapter()
        cancelled = 0
        for task in list(adapter.tasks):
            if task.done():
                continue
            try:
                coro = task.get_coro()
                if coro is None:
                    continue
                frame = coro.cr_frame
                if frame is None:
                    continue
                bot = frame.f_locals.get("bot")
                if bot is None:
                    continue
                if getattr(bot, "self_id", None) == bot_id:
                    task.cancel()
                    cancelled += 1
            except (AttributeError, RuntimeError):
                continue
        if cancelled:
            logger.info(f"已取消机器人 {bot_id} 的 {cancelled} 个连接任务")
        if bot_id in adapter.bots:
            adapter.bot_disconnect(adapter.bots[bot_id])
            logger.info(f"已断开机器人 {bot_id} 的连接")

    @classmethod
    def _sync_to_adapter(cls, bot_info: BotInfo) -> bool:
        """将机器人配置同步到QQ适配器并启动连接

        用于运行时动态添加或更新机器人配置。
        当配置发生变化时,会断开旧连接并使用新配置重连。

        参数:
            bot_info: BotInfo对象

        返回:
            bool: 是否同步成功
        """
        adapter = _get_adapter()
        for i, b in enumerate(adapter.qq_config.qq_bots):
            if b.id != bot_info.id:
                continue
            if b == bot_info:
                return True
            adapter.qq_config.qq_bots[i] = bot_info
            logger.info(f"已更新机器人 {bot_info.id} 的QQ适配器配置")
            cls._disconnect_bot(bot_info.id)
            if bot_info.use_websocket:
                cls._start_websocket(bot_info)
            return True

        adapter.qq_config.qq_bots.append(bot_info)
        logger.info(f"已将机器人 {bot_info.id} 添加到QQ适配器配置列表")
        if bot_info.use_websocket:
            cls._start_websocket(bot_info)
        return True

    @classmethod
    def _remove_from_adapter(cls, bot_id: str) -> bool:
        """从QQ适配器移除机器人配置

        参数:
            bot_id: 机器人ID

        返回:
            bool: 是否操作成功
        """
        adapter = _get_adapter()
        adapter.qq_config.qq_bots = [
            b for b in adapter.qq_config.qq_bots if b.id != bot_id
        ]
        cls._disconnect_bot(bot_id)
        return True

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
        validations = [
            cls._validate_bot_id(bot_id),
            cls._validate_credential("Token", token),
            cls._validate_credential("Secret", secret),
            cls._validate_intent(intent),
        ]
        for valid, msg in validations:
            if not valid:
                return False, msg

        count = await QQBotConfig.count_user_configs(user_id)
        if count >= cls.MAX_CONFIGS_PER_USER:
            return False, f"已达到最大配置数量限制({cls.MAX_CONFIGS_PER_USER}个)"

        if await QQBotConfig.check_bot_id_global_exists(bot_id):
            return False, f"机器人ID {bot_id} 已被其他用户添加,不可重复配置"

        try:
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

            cache_key = {"user_id": user_id, "bot_id": bot_id}
            await cls._cache.set(cache_key, _config_to_dict(config))

            if config.status:
                cls._sync_to_adapter(
                    cls._build_bot_info(_config_to_dict(config))
                )

            await UserLevel.set_bot_level(
                bot_id,
                user_id,
                Config.get_config("qq_bot_config", "BOT_LEVEL"),
            )

            logger.info(f"用户 {user_id} 添加QQ机器人配置: {bot_id}")
            return True, f"成功添加机器人配置: {bot_id}"
        except Exception as e:
            logger.error(f"添加配置失败: {e}", "QQBotConfig", e=e)
            return False, f"添加配置失败: {e!s}"

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
        cache_key = {"user_id": user_id, "bot_id": bot_id}
        return await cls._cache.get_or_load(
            cache_key,
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

        try:
            success = await QQBotConfig.update_config(
                user_id, bot_id, **update_data
            )
            if not success:
                return False, "更新配置失败"

            await cls._cache.delete({"user_id": user_id, "bot_id": bot_id})

            decrypted = await cls.get_config(user_id, bot_id)
            if decrypted:
                match decrypted.get("status", True):
                    case False:
                        cls._remove_from_adapter(bot_id)
                    case True:
                        cls._sync_to_adapter(
                            cls._build_bot_info(decrypted)
                        )

            logger.info(f"用户 {user_id} 更新配置: {bot_id}")
            return True, f"成功更新机器人配置: {bot_id}"
        except Exception as e:
            logger.error(f"更新配置失败: {e}", "QQBotConfig", e=e)
            return False, f"更新配置失败: {e!s}"

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

        try:
            cls._remove_from_adapter(bot_id)
            success = await QQBotConfig.delete_config(user_id, bot_id)
            if not success:
                return False, "删除配置失败"

            await cls._cache.delete({"user_id": user_id, "bot_id": bot_id})
            await UserLevel.delete_bot_level(bot_id, user_id)
            ReconnectMonitor.on_connected(bot_id)
            logger.info(f"用户 {user_id} 删除配置: {bot_id}")
            return True, f"成功删除机器人配置: {bot_id}"
        except Exception as e:
            logger.error(f"删除配置失败: {e}", "QQBotConfig", e=e)
            return False, f"删除配置失败: {e!s}"

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

        adapter = _get_adapter()
        existing_ids = {b.id for b in adapter.qq_config.qq_bots}
        success = fail = 0

        for config in configs:
            if config["bot_id"] in existing_ids:
                success += 1
                continue
            try:
                cls._add_bot_to_config(cls._build_bot_info(config))
                success += 1
            except Exception:
                fail += 1

        return success, fail

    @staticmethod
    def get_adapter_status() -> dict[str, Any]:
        """获取QQ适配器状态

        返回:
            dict[str, Any]: 适配器状态信息
        """
        adapter = _get_adapter()
        return {
            "connected_bots": [
                {"id": bot_id, "adapter": adapter.get_name()}
                for bot_id in adapter.bots
            ],
            "configured_bots": [
                {"id": b.id, "use_websocket": b.use_websocket}
                for b in adapter.qq_config.qq_bots
            ],
        }

    @staticmethod
    def get_online_bot_ids() -> set[str]:
        """获取当前在线的QQ机器人ID集合

        返回:
            set[str]: 在线机器人ID集合
        """
        adapter = _get_adapter()
        return set(adapter.bots.keys())
