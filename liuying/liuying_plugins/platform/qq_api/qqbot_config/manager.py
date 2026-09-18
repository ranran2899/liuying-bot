"""QQ机器人配置业务逻辑

依赖单向:
- adapter (适配器同步)
- monitor (重连监控,通过注册回调避免循环依赖)
- intent (意图字段)
- Config (项目配置访问)
数据访问统一由 model.QQBotConfig 提供
"""

import json

from liuying.configs.config import Config
from liuying.models._user import UserPermLevel
from liuying.utils.log import logger

from .adapter import QQAdapterManager, build_bot_info
from .intent import (
    DEFAULT_INTENT,
    INTENT_DESCRIPTIONS,
    VALID_INTENT_FIELDS,
)
from .model import QQBotConfig
from .monitor import ReconnectMonitor

_CONFIG_MODULE = "qqbot_config"
"""配置模块名"""

_SECRET_MIN_LEN = 10
"""AppSecret最小长度"""


class QQBotConfigManager:
    """QQ机器人配置业务管理器

    负责配置的增删改查业务逻辑(校验/适配器同步/权限联动),
    数据访问统一由 QQBotConfig 模型方法提供,
    通过 ReconnectMonitor 注册回调实现自动删除保护。
    写操作统一返回 (是否成功, 结果消息) 元组,
    供聊天指令与 WebUI 共用
    """

    @staticmethod
    def _validate_bot_id(bot_id: str) -> str | None:
        """验证机器人ID

        参数:
            bot_id: 机器人ID

        返回:
            str | None: 错误信息,验证通过返回None
        """
        if not bot_id:
            return "机器人ID不能为空"
        if not bot_id.isdigit():
            return "机器人ID必须为纯数字"
        return None

    @staticmethod
    def _validate_secret(secret: str) -> str | None:
        """验证AppSecret

        参数:
            secret: AppSecret

        返回:
            str | None: 错误信息,验证通过返回None
        """
        if not secret:
            return "Secret不能为空"
        if len(secret) < _SECRET_MIN_LEN:
            return "Secret长度不足"
        return None

    @classmethod
    def setup(cls) -> None:
        """初始化业务层与监控层的关联(启动钩子中调用)"""
        ReconnectMonitor.register_delete_callback(cls.delete_config)

    @classmethod
    def _sync_to_adapter(cls, bot: dict) -> None:
        """同步单个配置到适配器(允许失败,不影响配置存储)

        参数:
            bot: QQ_BOTS格式的单个机器人配置
        """
        try:
            QQAdapterManager.sync_to_adapter(build_bot_info(bot))
        except Exception as e:
            logger.error(f"同步到适配器失败: {e}", "QQBotConfig", e=e)

    @classmethod
    async def add_config(
        cls,
        user_id: str,
        bot_id: str,
        secret: str,
        use_websocket: bool = True,
    ) -> tuple[bool, str]:
        """添加QQ机器人配置

        参数:
            user_id: 用户ID
            bot_id: 机器人ID(AppID)
            secret: 机器人AppSecret
            use_websocket: 是否使用WebSocket

        返回:
            tuple[bool, str]: (是否成功, 结果消息)
        """
        if err := cls._validate_bot_id(bot_id):
            return False, err
        if err := cls._validate_secret(secret):
            return False, err

        max_configs = int(
            Config.get_config(_CONFIG_MODULE, "MAX_BOT_COUNT") or 5
        )
        bots = await QQBotConfig.get_user_bots(user_id)
        if len(bots) >= max_configs:
            return False, f"已达到最大配置数量限制({max_configs}个)"
        if await QQBotConfig.bot_id_exists(bot_id):
            return False, f"机器人ID {bot_id} 已被其他用户添加,不可重复配置"

        bots.append(
            {
                "id": bot_id,
                "secret": secret,
                "intent": DEFAULT_INTENT.copy(),
                "use_websocket": use_websocket,
            }
        )
        await QQBotConfig.save_user_bots(user_id, bots)

        cls._sync_to_adapter(bots[-1])

        bot_level = int(Config.get_config(_CONFIG_MODULE, "BOT_LEVEL") or 7)
        await UserPermLevel.set_bot_level(bot_id, user_id, bot_level)

        logger.info(f"用户 {user_id} 添加QQ机器人配置: {bot_id}")
        return True, f"成功添加机器人配置: {bot_id}"

    @classmethod
    async def update_config(
        cls,
        user_id: str,
        bot_id: str,
        *,
        secret: str | None = None,
        use_websocket: bool | None = None,
        intent: dict[str, bool] | None = None,
    ) -> tuple[bool, str]:
        """更新QQ机器人配置(仅更新传入的非None字段)

        参数:
            user_id: 用户ID
            bot_id: 机器人ID
            secret: 新AppSecret
            use_websocket: 是否使用WebSocket
            intent: 完整意图配置

        返回:
            tuple[bool, str]: (是否成功, 结果消息)
        """
        if secret is not None and (err := cls._validate_secret(secret)):
            return False, err
        if intent is not None:
            invalid = [k for k in intent if k not in VALID_INTENT_FIELDS]
            if invalid:
                return False, f"无效的意图字段: {', '.join(invalid)}"

        bots = await QQBotConfig.get_user_bots(user_id)
        bot = next((b for b in bots if b["id"] == bot_id), None)
        if bot is None:
            return False, f"机器人配置 {bot_id} 不存在"

        changed = False
        if secret is not None:
            bot["secret"] = secret
            changed = True
        if use_websocket is not None:
            bot["use_websocket"] = use_websocket
            changed = True
        if intent is not None:
            bot["intent"] = intent
            changed = True
        if not changed:
            return False, "没有需要更新的字段"

        await QQBotConfig.save_user_bots(user_id, bots)

        cls._sync_to_adapter(bot)

        logger.info(f"用户 {user_id} 更新配置: {bot_id}")
        return True, f"成功更新机器人配置: {bot_id}"

    @classmethod
    async def delete_config(cls, user_id: str, bot_id: str) -> tuple[bool, str]:
        """删除QQ机器人配置

        参数:
            user_id: 用户ID
            bot_id: 机器人ID

        返回:
            tuple[bool, str]: (是否成功, 结果消息)
        """
        bots = await QQBotConfig.get_user_bots(user_id)
        remaining = [b for b in bots if b["id"] != bot_id]
        if len(remaining) == len(bots):
            return False, f"机器人配置 {bot_id} 不存在"

        await QQBotConfig.save_user_bots(user_id, remaining)
        cls._remove_from_adapter(bot_id)
        await UserPermLevel.delete_bot_level(bot_id, user_id)
        ReconnectMonitor.on_connected(bot_id)
        logger.info(f"用户 {user_id} 删除配置: {bot_id}")
        return True, f"成功删除机器人配置: {bot_id}"

    @classmethod
    def _remove_from_adapter(cls, bot_id: str) -> None:
        """从适配器移除机器人(允许失败,仅记录日志)"""
        try:
            QQAdapterManager.remove_from_adapter(bot_id)
        except Exception as e:
            logger.warning(
                f"移除适配器中的机器人 {bot_id} 失败: {e}", "QQBotConfig"
            )

    @classmethod
    async def clear_all_configs(cls) -> tuple[bool, str]:
        """清空全部用户的QQ机器人配置(超级用户指令)

        移除适配器中所有机器人连接,清理权限数据后删除全部配置

        返回:
            tuple[bool, str]: (是否成功, 结果消息)
        """
        all_bots = await QQBotConfig.get_all_bots()
        if not all_bots:
            return False, "当前没有任何QQ机器人配置"

        for user_id, bot in all_bots:
            cls._remove_from_adapter(bot["id"])
            await UserPermLevel.delete_bot_level(bot["id"], user_id)
            ReconnectMonitor.on_connected(bot["id"])

        await QQBotConfig.delete_all()
        ReconnectMonitor.reset_failures()
        logger.warning(f"超级用户清空全部QQ机器人配置,共 {len(all_bots)} 个")
        return True, f"已清空全部QQ机器人配置,共删除 {len(all_bots)} 个"

    @staticmethod
    def get_default_intent() -> dict[str, bool]:
        """获取默认意图配置"""
        return DEFAULT_INTENT.copy()

    @staticmethod
    def get_intent_fields() -> dict[str, str]:
        """获取所有可用的意图字段及描述"""
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
            dict[str, bool] | None: 意图配置,配置不存在返回None
        """
        bot = await QQBotConfig.get_bot(user_id, bot_id)
        if bot is None:
            return None
        return dict(bot.get("intent", {}))

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
            tuple[bool, str]: (是否成功, 结果消息)
        """
        if field not in VALID_INTENT_FIELDS:
            available = ", ".join(VALID_INTENT_FIELDS)
            return False, f"无效的意图字段: {field}\n可用字段: {available}"

        bot = await QQBotConfig.get_bot(user_id, bot_id)
        if bot is None:
            return False, f"机器人配置 {bot_id} 不存在"

        intent = dict(bot.get("intent", {}))
        if intent.get(field) == value:
            return True, f"意图字段 {field} 已为{'启用' if value else '禁用'}"

        intent[field] = value
        return await cls.update_config(user_id, bot_id, intent=intent)

    @classmethod
    async def reset_intent(cls, user_id: str, bot_id: str) -> tuple[bool, str]:
        """重置意图配置为默认值

        参数:
            user_id: 用户ID
            bot_id: 机器人ID

        返回:
            tuple[bool, str]: (是否成功, 结果消息)
        """
        return await cls.update_config(
            user_id, bot_id, intent=cls.get_default_intent()
        )

    @classmethod
    async def export_to_env_format(cls, user_id: str) -> str | None:
        """导出用户配置为QQ_BOTS环境变量格式

        参数:
            user_id: 用户ID

        返回:
            str | None: JSON格式字符串,无配置时返回None
        """
        bots = await QQBotConfig.get_user_bots(user_id)
        if not bots:
            return None
        return json.dumps(bots, ensure_ascii=False, indent=2)

    @classmethod
    async def load_configs_to_adapter(cls) -> tuple[int, int]:
        """加载全部机器人配置到QQ适配器

        仅将配置添加到适配器的qq_bots列表,不主动启动WebSocket连接。
        适配器startup会遍历qq_bots自动启动连接,避免重复启动。
        add_bot_to_config 内部已做去重,无需重复检查。

        返回:
            tuple[int, int]: (成功数量, 失败数量)
        """
        all_bots = await QQBotConfig.get_all_bots()
        if not all_bots:
            return 0, 0

        success = fail = 0
        for _, bot in all_bots:
            try:
                QQAdapterManager.add_bot_to_config(build_bot_info(bot))
                success += 1
            except Exception:
                fail += 1

        return success, fail
