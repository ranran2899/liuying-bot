"""
塔罗牌插件
提供占卜、单张塔罗牌、每日塔罗、运势排行、图鉴收集等功能
"""
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Match, on_alconna
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import Command, PluginExtraData, RegisterConfig
from liuying.utils.log import logger

from .data_source import tarot_manager

__plugin_meta__ = PluginMetadata(
    name="塔罗牌",
    description="塔罗牌!魔法占卜",
    usage="""
    指令:
        占卜: 随机选取牌阵进行占卜
        塔罗牌: 得到单张塔罗牌回应
        每日塔罗: 每日一次运势占卜，记录运势分数
        运势排行: 查看今日运势排行榜
        塔罗图鉴: 查看已收集的塔罗牌图鉴
        塔罗牌详解 <牌名>: 查看指定塔罗牌的详细信息
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.2",
        menu_type="娱乐",
        commands=[
            Command(command="占卜", description="随机选取牌阵进行占卜"),
            Command(command="塔罗牌", description="得到单张塔罗牌回应"),
            Command(command="每日塔罗", description="每日一次运势占卜"),
            Command(command="运势排行", description="查看今日运势排行榜"),
            Command(command="塔罗图鉴", description="查看已收集的塔罗牌图鉴"),
            Command(command="塔罗牌详解", description="查看指定塔罗牌详细信息"),
        ],
        configs=[
            RegisterConfig(
                key="tarot_auto_update",
                value=False,
                help="是否自动更新塔罗牌资源",
                default_value=False,
                type=bool,
            ),
        ],
    ).to_dict(),
)

divine_matcher = on_alconna(
    Alconna("占卜", Args["arg?", str]),
    aliases={"/占卜"},
    priority=7,
    block=True,
)

tarot_matcher = on_alconna(
    Alconna("塔罗牌", Args["arg?", str]),
    aliases={"/塔罗牌"},
    priority=7,
    block=True,
)

daily_tarot_matcher = on_alconna(
    Alconna("每日塔罗"),
    aliases={"今日塔罗", "/每日塔罗"},
    priority=7,
    block=True,
)

fortune_rank_matcher = on_alconna(
    Alconna("运势排行"),
    aliases={"/运势排行"},
    priority=7,
    block=True,
)

tarot_collection_matcher = on_alconna(
    Alconna("塔罗图鉴"),
    aliases={"塔罗收集", "塔罗牌图鉴", "塔罗牌收集"},
    priority=7,
    block=True,
)

tarot_detail_matcher = on_alconna(
    Alconna("塔罗牌详解", Args["card_name", str]),
    priority=7,
    block=True,
)


def _check_help(arg: Match[str]) -> bool:
    """检查参数中是否包含帮助请求

    参数:
        arg: 命令参数匹配结果

    返回:
        bool: 是否请求帮助
    """
    return arg.available and "帮助" in arg.result


@divine_matcher.handle()
async def _(session: Uninfo, arg: Match[str]):
    """处理占卜命令"""
    if _check_help(arg):
        await divine_matcher.finish(__plugin_meta__.usage)
    await tarot_manager.divine(session)
    logger.info("塔罗牌占卜", "占卜", session=session)


@tarot_matcher.handle()
async def _(session: Uninfo, arg: Match[str]):
    """处理单张塔罗牌命令"""
    if _check_help(arg):
        await tarot_matcher.finish(__plugin_meta__.usage)
    logger.info("单张塔罗牌", "塔罗牌", session=session)
    await tarot_manager.onetime_divine(session)


@daily_tarot_matcher.handle()
async def _(session: Uninfo):
    """处理每日塔罗命令"""
    await tarot_manager.daily_divine(session)
    logger.info("每日塔罗", "每日塔罗", session=session)


@fortune_rank_matcher.handle()
async def _(session: Uninfo):
    """处理运势排行命令"""
    logger.info("运势排行", "运势排行", session=session)
    await tarot_manager.fortune_ranking(session)


@tarot_collection_matcher.handle()
async def _(session: Uninfo):
    """处理塔罗图鉴命令"""
    await tarot_manager.collection_view(session)
    logger.info("塔罗图鉴", "塔罗图鉴", session=session)


@tarot_detail_matcher.handle()
async def _(session: Uninfo, card_name: str):
    """处理塔罗牌详解命令"""
    await tarot_manager.card_detail(session, card_name)
    logger.info("塔罗牌详解", "塔罗牌详解", session=session)
