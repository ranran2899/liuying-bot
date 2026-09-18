"""QQ机器人配置管理API

复用 qqbot_config 插件的 QQBotConfigManager 业务逻辑,
提供机器人配置的查询/新增/修改/删除接口,操作实时同步到QQ适配器
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from liuying.liuying_plugins.platform.qq_api.qqbot_config.adapter import (
    QQAdapterManager,
)
from liuying.liuying_plugins.platform.qq_api.qqbot_config.manager import (
    QQBotConfigManager,
)
from liuying.liuying_plugins.platform.qq_api.qqbot_config.model import (
    QQBotConfig,
)
from liuying.utils.log import logger

from ....base_model import Result
from ....utils import authentication
from .model import AddBot, DeleteBot, UpdateBot

router = APIRouter(prefix="/qqbot")


def _get_online_ids() -> set[str]:
    """获取在线机器人ID集合(适配器未加载时降级为空集)"""
    try:
        return QQAdapterManager.get_online_bot_ids()
    except Exception as e:
        logger.warning(f"获取QQ适配器在线状态失败: {e}", "WebUI")
        return set()


@router.get(
    "/list",
    dependencies=[authentication()],
    response_model=Result,
    response_class=JSONResponse,
    description="获取全部QQ机器人配置",
)
async def get_bot_list() -> Result:
    online_ids = _get_online_ids()
    data = [
        {
            "user_id": user_id,
            "bot_id": bot["id"],
            "secret_masked": f"{bot['secret'][:4]}****",
            "use_websocket": bot.get("use_websocket", True),
            "intent": bot.get("intent", {}),
            "online": bot["id"] in online_ids,
        }
        for user_id, bot in await QQBotConfig.get_all_bots()
    ]
    return Result.ok(data)


@router.get(
    "/intents",
    dependencies=[authentication()],
    response_model=Result,
    response_class=JSONResponse,
    description="获取可用意图字段及默认配置",
)
async def get_intents() -> Result:
    return Result.ok(
        {
            "fields": [
                {"field": field, "description": desc}
                for field, desc in QQBotConfigManager.get_intent_fields().items()
            ],
            "default": QQBotConfigManager.get_default_intent(),
        }
    )


@router.get(
    "/status",
    dependencies=[authentication()],
    response_model=Result,
    response_class=JSONResponse,
    description="获取QQ适配器连接状态",
)
async def get_status() -> Result:
    online_ids = _get_online_ids()
    configured = await QQBotConfig.get_all_bots()
    return Result.ok(
        {
            "online_count": len(online_ids),
            "configured_count": len(configured),
            "online_ids": sorted(online_ids),
        }
    )


@router.post(
    "/add",
    dependencies=[authentication()],
    response_model=Result,
    response_class=JSONResponse,
    description="添加QQ机器人配置",
)
async def add_bot(param: AddBot) -> Result:
    suc, msg = await QQBotConfigManager.add_config(
        user_id=param.user_id,
        bot_id=param.bot_id.strip(),
        secret=param.secret.strip(),
        use_websocket=param.use_websocket,
    )
    return Result.ok(msg) if suc else Result.fail(msg)


@router.post(
    "/update",
    dependencies=[authentication()],
    response_model=Result,
    response_class=JSONResponse,
    description="更新QQ机器人配置",
)
async def update_bot(param: UpdateBot) -> Result:
    suc, msg = await QQBotConfigManager.update_config(
        param.user_id,
        param.bot_id.strip(),
        secret=param.secret.strip() if param.secret else None,
        use_websocket=param.use_websocket,
        intent=param.intent,
    )
    return Result.ok(msg) if suc else Result.fail(msg)


@router.post(
    "/delete",
    dependencies=[authentication()],
    response_model=Result,
    response_class=JSONResponse,
    description="删除QQ机器人配置",
)
async def delete_bot(param: DeleteBot) -> Result:
    suc, msg = await QQBotConfigManager.delete_config(
        param.user_id, param.bot_id.strip()
    )
    return Result.ok(msg) if suc else Result.fail(msg)
