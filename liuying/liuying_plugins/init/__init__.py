"""初始化模块"""

from pathlib import Path

import nonebot
from nonebot.adapters import Bot

from liuying.models._group import GroupConsole
from liuying.utils.log import logger
from liuying.utils.platform import PlatformUtils
from liuying.utils.platform.group import GroupListUtils

nonebot.load_plugins(str(Path(__file__).parent.resolve()))

driver = nonebot.get_driver()


@driver.on_bot_connect
async def _(bot: Bot) -> None:
    """将bot已存在的群组添加群认证

    参数:
        bot: Bot 实例
    """
    if PlatformUtils.get_platform(bot) != "qq":
        return

    logger.debug(f"更新Bot: {bot.self_id} 的群认证...")

    group_list, _ = await GroupListUtils.get_group_list(bot)
    db_group_list = await GroupConsole.filter().values_list("group_id", flat=True)

    create_list = []
    update_id = []

    for group in group_list:
        if group.group_id not in db_group_list:
            group.group_flag = 1
            create_list.append(group)
        else:
            update_id.append(group.group_id)

    if create_list:
        await GroupConsole.filter().bulk_create(create_list, 10)
    if update_id:
        await GroupConsole.filter(GroupConsole.group_id.in_(update_id)).update(
            group_flag=1
        )

    logger.debug(
        f"更新Bot: {bot.self_id} 的群认证完成，共创建 {len(create_list)} 条数据，"
        f"共修改 {len(update_id)} 条数据..."
    )
