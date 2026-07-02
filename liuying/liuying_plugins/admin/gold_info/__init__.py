from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import Command, PluginExtraData
from liuying.utils.enum import PluginType
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.utils.user import UserCurr, UserGold

__plugin_meta__ = PluginMetadata(
    name="机器人管理经济",
    description="管理用户金币",
    usage="""
    管理用户金币
    指令:
        添加金币 [用户ID] [数量]
        减少金币 [用户ID] [数量]
        设置金币 [用户ID] [数量]
        免费铜币
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.1",
        admin_level=5,
        plugin_type=PluginType.SUPER_AND_ADMIN,
        commands=[
            Command(command="添加金币"),
            Command(command="减少金币"),
            Command(command="设置金币"),
            Command(command="免费铜币"),
        ],
        superuser_help="""
        超级管理员额外命令
        格式:
            添加金币 [用户ID] [数量]
            减少金币 [用户ID] [数量]
            设置金币 [用户ID] [数量]
        """,
    ).to_dict(),
)

add_gold_cmd = on_alconna(
    Alconna("添加金币", Args["user_id", str], Args["amount", int]),
    permission=SUPERUSER,
    priority=5000,
    block=True,
)

reduce_gold_cmd = on_alconna(
    Alconna("减少金币", Args["user_id", str], Args["amount", int]),
    permission=SUPERUSER,
    priority=5000,
    block=True,
)

set_gold_cmd = on_alconna(
    Alconna("设置金币", Args["user_id", str], Args["amount", int]),
    permission=SUPERUSER,
    priority=5000,
    block=True,
)

free_copper_cmd = on_alconna(
    Alconna("免费铜币"),
    priority=5000,
    block=True,
)


@add_gold_cmd.handle()
async def handle_add_gold(session: Uninfo, user_id: str, amount: int):
    """处理添加金币请求

    参数:
        session: 会话信息
        user_id: 目标用户ID
        amount: 要添加的金币数量
    """
    if amount <= 0:
        await MessageUtils.build_message("添加的金币数量必须大于0").finish(
            reply_to=True
        )

    logger.info(
        f"用户 {session.user.id} 请求为用户 {user_id} 添加金币 {amount}",
        "添加金币",
        session=session,
    )

    new_gold = await UserGold.add_user_gold(user_id, amount)
    await MessageUtils.build_message(
        f"成功为用户 {user_id} 添加 {amount} 金币，当前金币：{new_gold}"
    ).finish(reply_to=True)


@reduce_gold_cmd.handle()
async def handle_reduce_gold(session: Uninfo, user_id: str, amount: int):
    """处理减少金币请求

    参数:
        session: 会话信息
        user_id: 目标用户ID
        amount: 要减少的金币数量
    """
    if amount <= 0:
        await MessageUtils.build_message("减少的金币数量必须大于0").finish(
            reply_to=True
        )

    logger.info(
        f"用户 {session.user.id} 请求为用户 {user_id} 减少金币 {amount}",
        "减少金币",
        session=session,
    )

    success = await UserGold.reduce_user_gold(user_id, amount)
    if not success:
        await MessageUtils.build_message("金币不足或减少失败").finish(reply_to=True)

    current_gold = await UserGold.get_user_gold(user_id)
    await MessageUtils.build_message(
        f"成功为用户 {user_id} 减少 {amount} 金币，当前金币：{current_gold}"
    ).finish(reply_to=True)


@set_gold_cmd.handle()
async def handle_set_gold(session: Uninfo, user_id: str, amount: int):
    """处理设置金币请求

    参数:
        session: 会话信息
        user_id: 目标用户ID
        amount: 要设置的金币数量
    """
    if amount < 0:
        await MessageUtils.build_message("设置的金币数量不能为负数").finish(
            reply_to=True
        )

    logger.info(
        f"用户 {session.user.id} 请求为用户 {user_id} 设置金币 {amount}",
        "设置金币",
        session=session,
    )

    new_gold = await UserGold.set_user_gold(user_id, amount)
    await MessageUtils.build_message(
        f"成功为杂鱼 {user_id} 的金币设置为 {new_gold}"
    ).finish(reply_to=True)


@free_copper_cmd.handle()
async def handle_free_copper(session: Uninfo):
    """处理免费铜币请求"""
    user_id = session.user.id
    logger.info(
        f"用户 {user_id} 领取免费铜币",
        "免费铜币",
        session=session,
        command="免费铜币",
    )

    current_copper = await UserCurr.add_user_copper(
        user_id=user_id,
        amount=1000000,
        source="免费铜币",
    )
    await MessageUtils.build_message(
        f"成功为你发放 1000000 铜币，当前铜币：{current_copper}"
    ).finish(reply_to=True)
