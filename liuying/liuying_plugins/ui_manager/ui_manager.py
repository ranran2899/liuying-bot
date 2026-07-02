"""UI管理插件，提供主题切换、商店和管理功能。

支持统一的中文指令体系：
    切换主题 [插件主题名称] [主题名称] - 切换个人主题
    我的主题 - 查看个人主题
    主题商店 - 浏览可购买主题
    购买主题 [插件主题名称] [主题名称] - 购买主题
"""

from functools import lru_cache
from typing import Any

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
from liuying.models._user.user_theme import UserTheme
from liuying.services.log import logger
from liuying.services.renderer import renderer_service as render_service
from liuying.utils.enum import PluginType
from liuying.utils.message import MessageUtils
from liuying.utils.user.gold import UserGold


class ThemeCommandService:
    """UI主题管理命令服务，封装所有主题相关业务逻辑。

    提供功能名称解析、主题名称解析和统一的命令处理方法，
    支持中文标签和英文键的双向解析。
    """

    @lru_cache(maxsize=1)
    def _features(self) -> dict[str, dict[str, str]]:
        """获取自动发现的功能映射（带缓存）。"""
        try:
            return render_service.discover_features()
        except RuntimeError:
            return {}

    def clear_cache(self) -> None:
        """清除功能映射缓存。"""
        self._features.cache_clear()

    def _feature_info(self, f_key: str) -> dict[str, str]:
        """获取功能标识的完整信息字典。"""
        return self._features().get(f_key, {})

    def _feature_page_path(self, f_key: str) -> str | None:
        """获取功能标识对应的页面路径。"""
        return self._feature_info(f_key).get("page_path")

    def _feature_label(self, f_key: str) -> str:
        """获取功能标识的显示名称。"""
        return self._feature_info(f_key).get("label", f_key)

    def _available_features_str(self) -> str:
        """获取可用功能列表字符串（中文标签 / 英文键）。"""
        items = [
            f"{info.get('label', key)}({key})"
            for key, info in sorted(self._features().items())
        ]
        return ", ".join(items)

    def _available_themes_str(self, page_path: str) -> str:
        """获取指定功能的可用主题列表字符串（中文标签 / 英文名）。"""
        themes = render_service.list_page_themes(page_path)
        items = [
            f"{render_service.get_theme_label(page_path, t)}({t})"
            for t in themes
        ]
        return ", ".join(items)

    def resolve_feature(self, label_or_key: str) -> str | None:
        """解析功能标识，支持中文标签和英文键。"""
        return render_service.resolve_feature_key(label_or_key)

    def resolve_theme(
        self, page_path: str, label_or_name: str
    ) -> str | None:
        """解析主题名称，支持中文标签和英文名。"""
        return render_service.resolve_theme_name(page_path, label_or_name)

    @staticmethod
    def _format_price(price: int) -> str:
        """格式化价格显示。"""
        return "免费" if price == 0 else f"{price}金币"

    @staticmethod
    def _all_available(*matches: Match) -> bool:
        """检查所有匹配参数是否可用。"""
        return all(m.available for m in matches)

    async def handle_switch_theme(
        self,
        session: Uninfo,
        feature: Match[str],
        theme_name: Match[str],
    ) -> None:
        """处理切换个人主题命令。

        指令格式：切换主题 [插件主题名称] [主题名称]
        示例：切换主题 签到 粉色
        """
        user_id = session.user.id

        if not self._all_available(feature, theme_name):
            await MessageUtils.build_message(
                "用法: 切换主题 [功能] [主题名]\n"
                "示例: 切换主题 签到 粉色\n"
                f"可用功能: {self._available_features_str()}"
            ).send(reply_to=True)
            return

        raw_feature = feature.result
        raw_theme = theme_name.result

        f_key = self.resolve_feature(raw_feature)
        if not f_key:
            await MessageUtils.build_message(
                f"未知功能 '{raw_feature}'，可用功能: "
                f"{self._available_features_str()}"
            ).send(reply_to=True)
            return

        page_path = self._feature_page_path(f_key)
        if not page_path:
            await MessageUtils.build_message(
                f"功能 '{f_key}' 缺少页面路径配置"
            ).send(reply_to=True)
            return

        f_label = self._feature_label(f_key)

        if raw_theme in ("默认", "default"):
            success = await UserTheme.set_current_theme(
                user_id, f_key, "default"
            )
            if success:
                await MessageUtils.build_message(
                    f"已将 {f_label}({f_key}) 的主题切换为默认主题"
                ).send(reply_to=True)
            else:
                await MessageUtils.build_message(
                    "切换主题失败"
                ).send(reply_to=True)
            return

        t_name = self.resolve_theme(page_path, raw_theme)
        if not t_name:
            await MessageUtils.build_message(
                f"功能 '{f_label}' 不存在主题 '{raw_theme}'\n"
                f"可用主题: {self._available_themes_str(page_path)}"
            ).send(reply_to=True)
            return

        if not await UserTheme.has_theme(user_id, f_key, t_name):
            price = render_service.get_theme_price(page_path, t_name)
            t_label = render_service.get_theme_label(page_path, t_name)
            hint = f"你没有 {f_label} 的 '{t_label}'({t_name}) 主题"
            if price > 0:
                hint += (
                    f"，可使用'购买主题 {f_label} {t_label}'"
                    f"购买({price}金币)"
                )
            await MessageUtils.build_message(hint).send(reply_to=True)
            return

        success = await UserTheme.set_current_theme(user_id, f_key, t_name)
        if success:
            t_label = render_service.get_theme_label(page_path, t_name)
            logger.info(
                f"用户 {user_id} 将 {f_label}({f_key}) 的主题切换为: "
                f"{t_label}({t_name})",
                "UI管理器",
                session=session,
            )
            await MessageUtils.build_message(
                f"已将 {f_label}({f_key}) 的主题切换为 "
                f"'{t_label}'({t_name})"
            ).send(reply_to=True)
        else:
            await MessageUtils.build_message(
                "切换主题失败"
            ).send(reply_to=True)

    async def handle_my_theme(self, session: Uninfo) -> None:
        """处理查看个人主题命令。"""
        user_id = session.user.id
        try:
            owned = await UserTheme.get_owned_themes(user_id)
            current = await UserTheme.get_current_themes_dict(user_id)

            data: dict[str, Any] = owned.get("data", {})
            if not data:
                await MessageUtils.build_message(
                    "你目前没有额外的主题资源，使用的是默认主题。\n"
                    f"可用功能: {self._available_features_str()}\n"
                    "输入'主题商店'查看可购买的主题"
                ).send(reply_to=True)
                return

            lines = ["你的主题资源:"]
            for f_key, themes in sorted(data.items()):
                current_name = current.get(f_key, "default")
                f_label = self._feature_label(f_key)
                page_path = self._feature_page_path(f_key)
                theme_items = []
                for t in themes:
                    t_label = (
                        render_service.get_theme_label(page_path, t)
                        if page_path else t
                    )
                    mark = "(当前)" if t == current_name else ""
                    theme_items.append(f"{t_label}({t}){mark}")
                lines.append(
                    f"  [{f_key}]({f_label}): {', '.join(theme_items)}"
                )

            await MessageUtils.build_message(
                "\n".join(lines)
            ).send(reply_to=True)
        except Exception as e:
            logger.error(
                f"获取个人主题时发生错误: {e}",
                "UI管理器",
                session=session,
                e=e,
            )
            await MessageUtils.build_message(
                "获取个人主题失败。"
            ).send(reply_to=True)

    async def handle_theme_shop(self, session: Uninfo) -> None:
        """处理主题商店命令。"""
        user_id = session.user.id
        try:
            store_items = render_service.get_store_items()
            if not store_items:
                await MessageUtils.build_message(
                    "主题商店暂无可用主题。"
                ).send(reply_to=True)
                return

            owned = await UserTheme.get_owned_themes(user_id)
            owned_data: dict[str, Any] = owned.get("data", {})

            current_feature = ""
            lines: list[str] = ["主题商店:"]
            for item in store_items:
                if item.feature != current_feature:
                    current_feature = item.feature
                    lines.append(
                        f"\n  [{item.feature}]({item.feature_label}):"
                    )

                owned_themes = owned_data.get(item.feature, [])
                status = ""
                if item.theme_name in owned_themes:
                    status = " [已拥有]"
                elif item.theme_name == "default":
                    status = " [免费]"

                price_str = self._format_price(item.price)
                lines.append(
                    f"    - {item.theme_label}({item.theme_name}) "
                    f"({price_str}){status}"
                )

            user_gold = await UserGold.get_user_gold(user_id)
            lines.append(f"\n当前金币: {user_gold}")
            lines.append("购买方式: 购买主题 [功能] [主题名]")

            await MessageUtils.build_message(
                "\n".join(lines)
            ).send(reply_to=True)
        except Exception as e:
            logger.error(
                f"获取主题商店时发生错误: {e}",
                "UI管理器",
                session=session,
                e=e,
            )
            await MessageUtils.build_message(
                "获取主题商店失败。"
            ).send(reply_to=True)

    async def handle_buy_theme(
        self,
        session: Uninfo,
        feature: Match[str],
        theme_name: Match[str],
    ) -> None:
        """处理购买主题命令。

        指令格式：购买主题 [插件主题名称] [主题名称]
        示例：购买主题 签到 粉色
        """
        user_id = session.user.id

        if not self._all_available(feature, theme_name):
            await MessageUtils.build_message(
                "用法: 购买主题 [功能] [主题名]\n"
                "示例: 购买主题 签到 粉色\n"
                "输入'主题商店'查看可购买的主题"
            ).send(reply_to=True)
            return

        raw_feature = feature.result
        raw_theme = theme_name.result

        f_key = self.resolve_feature(raw_feature)
        if not f_key:
            await MessageUtils.build_message(
                f"未知功能 '{raw_feature}'，可用功能: "
                f"{self._available_features_str()}"
            ).send(reply_to=True)
            return

        page_path = self._feature_page_path(f_key)
        if not page_path:
            await MessageUtils.build_message(
                f"未知功能 '{raw_feature}'"
            ).send(reply_to=True)
            return

        f_label = self._feature_label(f_key)

        if raw_theme in ("默认", "default"):
            await UserTheme.add_owned_theme(user_id, f_key, "default")
            await MessageUtils.build_message(
                "默认主题已添加到你的主题列表"
            ).send(reply_to=True)
            return

        t_name = self.resolve_theme(page_path, raw_theme)
        if not t_name:
            await MessageUtils.build_message(
                f"功能 '{f_label}' 不存在主题 '{raw_theme}'\n"
                f"可用主题: {self._available_themes_str(page_path)}"
            ).send(reply_to=True)
            return

        if await UserTheme.has_theme(user_id, f_key, t_name):
            t_label = render_service.get_theme_label(page_path, t_name)
            await MessageUtils.build_message(
                f"你已经拥有 {f_label} 的 '{t_label}'({t_name}) 主题"
            ).send(reply_to=True)
            return

        price = render_service.get_theme_price(page_path, t_name)
        t_label = render_service.get_theme_label(page_path, t_name)

        if price == 0:
            success = await UserTheme.add_owned_theme(user_id, f_key, t_name)
            if success:
                logger.info(
                    f"用户 {user_id} 免费获取 {f_label}({f_key}) 的 "
                    f"'{t_label}'({t_name}) 主题",
                    "UI管理器",
                    session=session,
                )
                await MessageUtils.build_message(
                    f"已免费获取 {f_label}({f_key}) 的 "
                    f"'{t_label}'({t_name}) 主题！"
                ).send(reply_to=True)
            return

        user_gold = await UserGold.get_user_gold(user_id)
        if user_gold < price:
            await MessageUtils.build_message(
                f"金币不足！{f_label}({f_key}) 的 '{t_label}'({t_name})"
                f"主题需要 {price} 金币，你当前只有 {user_gold} 金币"
            ).send(reply_to=True)
            return

        success = await UserGold.reduce_user_gold(
            user_id=user_id,
            amount=price,
            source="theme_shop",
        )
        if not success:
            await MessageUtils.build_message(
                "金币扣除失败，请稍后再试"
            ).send(reply_to=True)
            return

        success = await UserTheme.add_owned_theme(user_id, f_key, t_name)
        if success:
            logger.info(
                f"用户 {user_id} 花费 {price} 金币购买了 "
                f"{f_label}({f_key}) 的 '{t_label}'({t_name}) 主题",
                "UI管理器",
                session=session,
            )
            await MessageUtils.build_message(
                f"购买成功！已花费 {price} 金币获取 "
                f"{f_label}({f_key}) 的 '{t_label}'({t_name}) 主题\n"
                f"使用'切换主题 {f_label} {t_label}'来切换"
            ).send(reply_to=True)
        else:
            await UserGold.add_user_gold(
                user_id=user_id,
                amount=price,
                source="theme_shop_refund",
            )
            logger.warning(
                f"用户 {user_id} 购买主题后添加失败，已退还 {price} 金币",
                "UI管理器",
                session=session,
            )
            await MessageUtils.build_message(
                "购买失败，金币已退还"
            ).send(reply_to=True)

    async def handle_grant(
        self,
        session: Uninfo,
        user_id: Match[str],
        target_feature: Match[str],
        theme_name: Match[str],
    ) -> None:
        """处理为用户授予主题命令（管理员）。"""
        if not self._all_available(user_id, target_feature, theme_name):
            await MessageUtils.build_message(
                "用法: ui grant [用户ID] [功能] [主题名]\n"
                "示例: ui grant 123456 签到 粉色\n"
                f"可用功能: {self._available_features_str()}"
            ).send(reply_to=True)
            return

        uid = user_id.result
        raw_feature = target_feature.result
        raw_theme = theme_name.result

        f_key = self.resolve_feature(raw_feature)
        if not f_key:
            await MessageUtils.build_message(
                f"未知功能 '{raw_feature}'，"
                f"可用功能: {self._available_features_str()}"
            ).send(reply_to=True)
            return

        page_path = self._feature_page_path(f_key)
        f_label = self._feature_label(f_key)

        if raw_theme in ("默认", "default"):
            t_name = "default"
        else:
            if not page_path:
                await MessageUtils.build_message(
                    f"功能 '{f_label}' 无可用主题"
                ).send(reply_to=True)
                return
            t_name = self.resolve_theme(page_path, raw_theme)
            if not t_name:
                await MessageUtils.build_message(
                    f"功能 '{f_label}' 不存在主题 '{raw_theme}'\n"
                    f"可用主题: {self._available_themes_str(page_path)}"
                ).send(reply_to=True)
                return

        success = await UserTheme.add_owned_theme(uid, f_key, t_name)
        t_label = (
            "默认" if t_name == "default"
            else render_service.get_theme_label(page_path, t_name)
        )
        if success:
            logger.info(
                f"已为用户 {uid} 授予 {f_label}({f_key}) 功能的 "
                f"'{t_label}'({t_name}) 主题",
                "UI管理器",
                session=session,
            )
            await MessageUtils.build_message(
                f"已为用户 {uid} 授予 {f_label}({f_key}) 功能的 "
                f"'{t_label}'({t_name}) 主题"
            ).send(reply_to=True)
        else:
            await MessageUtils.build_message(
                "授予主题失败，用户可能已拥有该主题"
            ).send(reply_to=True)

    async def handle_revoke(
        self,
        session: Uninfo,
        user_id: Match[str],
        target_feature: Match[str],
        theme_name: Match[str],
    ) -> None:
        """处理撤销用户主题命令（管理员）。"""
        if not self._all_available(user_id, target_feature, theme_name):
            await MessageUtils.build_message(
                "用法: ui revoke [用户ID] [功能] [主题名]\n"
                "示例: ui revoke 123456 签到 粉色"
            ).send(reply_to=True)
            return

        uid = user_id.result
        raw_feature = target_feature.result
        raw_theme = theme_name.result

        f_key = self.resolve_feature(raw_feature)
        if not f_key:
            await MessageUtils.build_message(
                f"未知功能 '{raw_feature}'，"
                f"可用功能: {self._available_features_str()}"
            ).send(reply_to=True)
            return

        page_path = self._feature_page_path(f_key)
        f_label = self._feature_label(f_key)

        if raw_theme in ("默认", "default"):
            await MessageUtils.build_message(
                "无法撤销默认主题"
            ).send(reply_to=True)
            return

        if not page_path:
            await MessageUtils.build_message(
                f"功能 '{f_label}' 无可用主题"
            ).send(reply_to=True)
            return

        t_name = self.resolve_theme(page_path, raw_theme)
        if not t_name:
            await MessageUtils.build_message(
                f"功能 '{f_label}' 不存在主题 '{raw_theme}'"
            ).send(reply_to=True)
            return

        success = await UserTheme.remove_owned_theme(uid, f_key, t_name)
        if success:
            current = await UserTheme.get_current_theme(uid, f_key)
            if current == t_name:
                await UserTheme.set_current_theme(uid, f_key, "default")
            t_label = render_service.get_theme_label(page_path, t_name)
            logger.info(
                f"已撤销用户 {uid} 的 {f_label}({f_key}) 功能的 "
                f"'{t_label}'({t_name}) 主题",
                "UI管理器",
                session=session,
            )
            await MessageUtils.build_message(
                f"已撤销用户 {uid} 的 {f_label}({f_key}) 功能的 "
                f"'{t_label}'({t_name}) 主题"
            ).send(reply_to=True)
        else:
            await MessageUtils.build_message(
                "撤销主题失败，用户可能不拥有该主题"
            ).send(reply_to=True)

    async def handle_page_themes(
        self,
        session: Uninfo,
        feature: Match[str],
    ) -> None:
        """处理查看页面级主题命令。"""
        features = self._features()
        if not feature.available:
            lines = ["可用功能及主题:"]
            for f_key, info in sorted(features.items()):
                try:
                    theme_str = self._available_themes_str(
                        info["page_path"]
                    )
                except Exception:
                    theme_str = "获取失败"
                lines.append(
                    f"  [{f_key}]({info['label']}): {theme_str}"
                )
            await MessageUtils.build_message(
                "\n".join(lines)
            ).send(reply_to=True)
            return

        raw_feature = feature.result
        f_key = self.resolve_feature(raw_feature)
        if not f_key:
            await MessageUtils.build_message(
                f"未知功能 '{raw_feature}'，"
                f"可用功能: {self._available_features_str()}"
            ).send(reply_to=True)
            return

        info = features.get(f_key)
        if not info:
            await MessageUtils.build_message(
                f"未知功能 '{raw_feature}'"
            ).send(reply_to=True)
            return

        try:
            page_path = info["page_path"]
            themes = render_service.list_page_themes(page_path)
            if not themes:
                await MessageUtils.build_message(
                    f"{info['label']}({f_key}) 暂无可用主题"
                ).send(reply_to=True)
                return
            theme_lines: list[str] = []
            for t_name in themes:
                price = render_service.get_theme_price(page_path, t_name)
                t_label = render_service.get_theme_label(page_path, t_name)
                price_str = self._format_price(price)
                theme_lines.append(
                    f"  - {t_label}({t_name}) ({price_str})"
                )
            await MessageUtils.build_message(
                f"{info['label']}({f_key}) 可用主题:\n"
                + "\n".join(theme_lines)
            ).send(reply_to=True)
        except Exception as e:
            logger.error(
                f"获取页面主题时发生错误: {e}",
                "UI管理器",
                session=session,
                e=e,
            )
            await MessageUtils.build_message(
                "获取页面主题失败。"
            ).send(reply_to=True)


theme_service = ThemeCommandService()


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
