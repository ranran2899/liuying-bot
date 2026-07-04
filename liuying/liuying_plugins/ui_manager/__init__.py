"""UI管理插件，提供主题切换、商店和管理功能。

支持统一的中文指令体系：
    切换主题 [插件主题名称] [主题名称] - 切换个人主题
    我的主题 - 查看个人主题
    主题商店 - 浏览可购买主题
    购买主题 [插件主题名称] [主题名称] - 购买主题
"""

from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import (
    Alconna,
    AlconnaMatch,
    Args,
    Match,
    Subcommand,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo

from liuying.configs.utils import PluginExtraData, RegisterConfig
from liuying.services.log import logger
from liuying.services.renderer import renderer_service as render_service
from liuying.utils.enum import PluginType
from liuying.utils.message import MessageUtils

from .ui_manager import theme_service

__all__ = ["__plugin_meta__"]

__plugin_meta__ = PluginMetadata(
    name="UI管理",
    description="管理UI主题和渲染服务的相关配置，支持个人主题选择与主题商店",
    usage="""
    指令：
        ui reload / 重载主题: 重新加载当前主题的配置和资源。
        ui page-themes [功能] / 页面主题 [功能]: 查看指定功能可用的页面主题。
        ui grant [用户ID] [功能] [主题名]: 为用户授予指定功能的主题。
        ui revoke [用户ID] [功能] [主题名]: 撤销用户的指定功能主题。
        我的主题: 查看个人拥有的主题和当前选择。
        切换主题 [功能] [主题名]: 切换个人指定功能的主题。
        主题商店: 浏览可购买的主题列表。
        购买主题 [功能] [主题名]: 购买指定功能的主题。

    支持中文和英文功能名/主题名：
        切换主题 签到 粉色  (中文)
        切换主题 sign pink  (英文)
    """.strip(),
    extra=PluginExtraData(
        author="liuying",
        version="0.5",
        plugin_type=PluginType.SUPERUSER,
        configs=[
            RegisterConfig(
                module="UI",
                key="CACHE",
                value=True,
                help="是否为渲染服务生成的图片启用文件缓存",
                default_value=True,
                type=bool,
            ),
            RegisterConfig(
                module="UI",
                key="DEBUG_MODE",
                value=False,
                help="是否在日志中输出渲染组件的完整HTML源码，用于调试",
                default_value=False,
                type=bool,
            ),
        ],
    ).to_dict(),
)


# --- 匹配器定义 ---

ui_matcher = on_alconna(
    Alconna(
        "ui",
        Subcommand("reload", help_text="重载当前主题"),
        Subcommand(
            "page-themes",
            Args["feature?", str],
            help_text="查看页面级主题",
        ),
        Subcommand(
            "grant",
            Args["user_id?", str]["target_feature?", str]["theme_name?", str],
            help_text="为用户授予主题",
        ),
        Subcommand(
            "revoke",
            Args["user_id?", str]["target_feature?", str]["theme_name?", str],
            help_text="撤销用户主题",
        ),
    ),
    aliases={"主题管理"},
    rule=to_me(),
    permission=SUPERUSER,
    priority=1,
    block=True,
)

user_theme_matcher = on_alconna(
    Alconna("我的主题"),
    aliases={"mytheme"},
    priority=1,
    block=True,
)

switch_theme_matcher = on_alconna(
    Alconna("切换主题", Args["feature", str]["theme_name", str]),
    aliases={"使用主题"},
    priority=1,
    block=True,
)

theme_shop_matcher = on_alconna(
    Alconna("主题商店"),
    aliases={"themes shop", "主题商城"},
    priority=1,
    block=True,
)

buy_theme_matcher = on_alconna(
    Alconna("购买主题", Args["feature", str]["theme_name", str]),
    priority=1,
    block=True,
)

ui_matcher.shortcut("重载主题", command="ui reload")
ui_matcher.shortcut("页面主题", command="ui page-themes", arguments=["{%0}"])


# --- 命令处理器 ---

@ui_matcher.assign("reload")
async def handle_reload(session: Uninfo):
    """处理重载主题命令。"""
    theme_service.clear_cache()
    theme_name = await render_service.reload_theme()
    logger.info(
        f"UI主题已重载为: {theme_name}", "UI管理器", session=session
    )
    await MessageUtils.build_message(
        f"UI主题已成功重载为 '{theme_name}'！"
    ).send(reply_to=True)


@ui_matcher.assign("page-themes")
async def handle_page_themes(
    session: Uninfo,
    feature: Match[str] = AlconnaMatch("feature"),
):
    """处理查看页面级主题命令。"""
    await theme_service.handle_page_themes(session, feature)


@ui_matcher.assign("grant")
async def handle_grant(
    session: Uninfo,
    user_id: Match[str] = AlconnaMatch("user_id"),
    target_feature: Match[str] = AlconnaMatch("target_feature"),
    theme_name: Match[str] = AlconnaMatch("theme_name"),
):
    """处理为用户授予主题命令。"""
    await theme_service.handle_grant(
        session, user_id, target_feature, theme_name
    )


@ui_matcher.assign("revoke")
async def handle_revoke(
    session: Uninfo,
    user_id: Match[str] = AlconnaMatch("user_id"),
    target_feature: Match[str] = AlconnaMatch("target_feature"),
    theme_name: Match[str] = AlconnaMatch("theme_name"),
):
    """处理撤销用户主题命令。"""
    await theme_service.handle_revoke(
        session, user_id, target_feature, theme_name
    )


@user_theme_matcher.handle()
async def handle_my_theme(session: Uninfo):
    """处理查看个人主题命令。"""
    await theme_service.handle_my_theme(session)


@switch_theme_matcher.handle()
async def handle_switch_theme(
    session: Uninfo,
    feature: Match[str] = AlconnaMatch("feature"),
    theme_name: Match[str] = AlconnaMatch("theme_name"),
):
    """处理切换个人主题命令。"""
    await theme_service.handle_switch_theme(session, feature, theme_name)


@theme_shop_matcher.handle()
async def handle_theme_shop(session: Uninfo):
    """处理主题商店命令。"""
    await theme_service.handle_theme_shop(session)


@buy_theme_matcher.handle()
async def handle_buy_theme(
    session: Uninfo,
    feature: Match[str] = AlconnaMatch("feature"),
    theme_name: Match[str] = AlconnaMatch("theme_name"),
):
    """处理购买主题命令。"""
    await theme_service.handle_buy_theme(session, feature, theme_name)
