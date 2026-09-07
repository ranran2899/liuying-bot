"""UI 主题管理业务服务，全部方法返回消息文本，由 handler 统一发送。"""

from functools import lru_cache
from typing import Any

from liuying.models._user.user_theme import UserTheme
from liuying.services.log import logger
from liuying.services.renderer import renderer_service as render_service
from liuying.utils.user.gold import UserGold

DEFAULT_THEME_NAMES = frozenset({"默认", "default"})
"""表示默认主题的指令别名。"""


class ThemeCommandService:
    """UI 主题命令业务服务，支持中文标签与英文键的双向解析。

    所有 handle_* 方法仅组装并返回消息文本，不负责发送，
    由插件 handler 统一通过 MessageUtils 发送。
    """

    # ---------- 基础解析 ----------

    @lru_cache(maxsize=1)
    def _features(self) -> dict[str, dict[str, str]]:
        """获取自动发现的功能映射（带缓存）。

        返回:
            dict[str, dict[str, str]]: 功能键到 {page_path, label} 的映射，
                渲染服务未初始化时返回空字典。
        """
        try:
            return render_service.discover_features()
        except RuntimeError:
            return {}

    def clear_cache(self) -> None:
        """清除功能映射缓存，供主题重载后刷新功能列表。"""
        self._features.cache_clear()

    def _feature_info(self, f_key: str) -> dict[str, str]:
        """获取功能键的完整信息。

        参数:
            f_key: 功能键。

        返回:
            dict[str, str]: 功能信息字典，未知功能时返回空字典。
        """
        return self._features().get(f_key, {})

    def _feature_label(self, f_key: str) -> str:
        """获取功能的显示名称。

        参数:
            f_key: 功能键。

        返回:
            str: 功能的中文标签，未配置时返回功能键本身。
        """
        return self._feature_info(f_key).get("label", f_key)

    def _features_hint(self) -> str:
        """生成可用功能列表提示串。

        返回:
            str: 形如 "签到(sign), 银行(bank)" 的提示文本。
        """
        return ", ".join(
            f"{info.get('label', key)}({key})"
            for key, info in sorted(self._features().items())
        )

    def _themes_hint(self, page_path: str) -> str:
        """生成指定功能的可用主题列表提示串。

        参数:
            page_path: 功能对应的页面路径。

        返回:
            str: 形如 "粉色(pink), 默认(default)" 的提示文本。
        """
        return ", ".join(
            f"{render_service.get_theme_label(page_path, t)}({t})"
            for t in render_service.list_page_themes(page_path)
        )

    @staticmethod
    def _format_price(price: int) -> str:
        """格式化价格显示。

        参数:
            price: 价格数值。

        返回:
            str: 0 显示为 "免费"，其余显示为 "{price}金币"。
        """
        return "免费" if price == 0 else f"{price}金币"

    # ---------- 个人主题 ----------

    async def handle_switch_theme(
        self, user_id: str, raw_feature: str, raw_theme: str
    ) -> str:
        """处理切换个人主题命令。

        指令格式：切换主题 [功能] [主题名]，
        主题名为"默认/default"时切换回默认主题。

        参数:
            user_id: 用户 ID。
            raw_feature: 用户输入的功能名（中文标签或英文键）。
            raw_theme: 用户输入的主题名（中文标签或英文目录名）。

        返回:
            str: 切换结果的消息文本。
        """
        if not (parsed := self._parse_feature(raw_feature)):
            return f"未知功能 '{raw_feature}'，可用功能: {self._features_hint()}"
        f_key, page_path = parsed
        f_label = self._feature_label(f_key)

        if raw_theme in DEFAULT_THEME_NAMES:
            if await UserTheme.set_current_theme(user_id, f_key, "default"):
                return f"已将 {f_label}({f_key}) 的主题切换为默认主题"
            return "切换主题失败"

        if not page_path:
            return f"功能 '{f_key}' 缺少页面路径配置"
        if not (t_name := self._parse_theme(page_path, raw_theme)):
            return (
                f"功能 '{f_label}' 不存在主题 '{raw_theme}'\n"
                f"可用主题: {self._themes_hint(page_path)}"
            )

        if not await UserTheme.has_theme(user_id, f_key, t_name):
            price = render_service.get_theme_price(page_path, t_name)
            t_label = render_service.get_theme_label(page_path, t_name)
            hint = f"你没有 {f_label} 的 '{t_label}'({t_name}) 主题"
            if price > 0:
                hint += f"，可使用'购买主题 {f_label} {t_label}'购买({price}金币)"
            return hint

        if not await UserTheme.set_current_theme(user_id, f_key, t_name):
            return "切换主题失败"
        t_label = render_service.get_theme_label(page_path, t_name)
        logger.info(
            f"用户 {user_id} 将 {f_label}({f_key}) 的主题切换为: "
            f"{t_label}({t_name})",
            "UI管理器",
        )
        return (
            f"已将 {f_label}({f_key}) 的主题切换为 '{t_label}'({t_name})"
        )

    async def handle_my_theme(self, user_id: str) -> str:
        """处理查看个人主题命令。

        参数:
            user_id: 用户 ID。

        返回:
            str: 个人主题清单的消息文本。
        """
        owned: dict[str, Any] = (await UserTheme.get_owned_themes(user_id)).get(
            "data", {}
        )
        if not owned:
            return (
                "你目前没有额外的主题资源，使用的是默认主题。\n"
                f"可用功能: {self._features_hint()}\n"
                "输入'主题商店'查看可购买的主题"
            )

        current = await UserTheme.get_current_themes_dict(user_id)
        lines = ["你的主题资源:"]
        for f_key, themes in sorted(owned.items()):
            current_name = current.get(f_key, "default")
            page_path = self._feature_info(f_key).get("page_path")
            theme_items = [
                f"{render_service.get_theme_label(page_path, t) if page_path else t}"
                f"({t}){'(当前)' if t == current_name else ''}"
                for t in themes
            ]
            lines.append(
                f"  [{f_key}]({self._feature_label(f_key)}): "
                f"{', '.join(theme_items)}"
            )
        return "\n".join(lines)

    # ---------- 主题商店 ----------

    async def handle_theme_shop(self, user_id: str) -> str:
        """处理主题商店命令，输出按功能分组的主题列表。

        参数:
            user_id: 用户 ID，用于展示持有状态与当前金币。

        返回:
            str: 商店条目的消息文本。
        """
        store_items = render_service.get_store_items()
        if not store_items:
            return "主题商店暂无可用主题。"

        owned: dict[str, Any] = (await UserTheme.get_owned_themes(user_id)).get(
            "data", {}
        )
        lines: list[str] = ["主题商店:"]
        current_feature = ""
        for item in store_items:
            if item.feature != current_feature:
                current_feature = item.feature
                lines.append(f"\n  [{item.feature}]({item.feature_label}):")
            status = ""
            if item.theme_name in owned.get(item.feature, []):
                status = " [已拥有]"
            elif item.theme_name == "default":
                status = " [免费]"
            lines.append(
                f"    - {item.theme_label}({item.theme_name}) "
                f"({self._format_price(item.price)}){status}"
            )

        lines.append(f"\n当前金币: {await UserGold.get_user_gold(user_id)}")
        lines.append("购买方式: 购买主题 [功能] [主题名]")
        return "\n".join(lines)

    async def handle_buy_theme(
        self, user_id: str, raw_feature: str, raw_theme: str
    ) -> str:
        """处理购买主题命令，支持免费主题直接领取与金币购买。

        金币扣除成功但主题添加失败时自动退还金币。

        参数:
            user_id: 用户 ID。
            raw_feature: 用户输入的功能名。
            raw_theme: 用户输入的主题名。

        返回:
            str: 购买结果的消息文本。
        """
        if not (parsed := self._parse_feature(raw_feature)):
            return f"未知功能 '{raw_feature}'，可用功能: {self._features_hint()}"
        f_key, page_path = parsed
        f_label = self._feature_label(f_key)

        if raw_theme in DEFAULT_THEME_NAMES:
            await UserTheme.add_owned_theme(user_id, f_key, "default")
            return "默认主题已添加到你的主题列表"

        if not page_path:
            return f"未知功能 '{raw_feature}'"
        if not (t_name := self._parse_theme(page_path, raw_theme)):
            return (
                f"功能 '{f_label}' 不存在主题 '{raw_theme}'\n"
                f"可用主题: {self._themes_hint(page_path)}"
            )
        t_label = render_service.get_theme_label(page_path, t_name)

        if await UserTheme.has_theme(user_id, f_key, t_name):
            return f"你已经拥有 {f_label} 的 '{t_label}'({t_name}) 主题"

        price = render_service.get_theme_price(page_path, t_name)
        if price == 0:
            if await UserTheme.add_owned_theme(user_id, f_key, t_name):
                logger.info(
                    f"用户 {user_id} 免费获取 {f_label}({f_key}) 的 "
                    f"'{t_label}'({t_name}) 主题",
                    "UI管理器",
                )
                return (
                    f"已免费获取 {f_label}({f_key}) 的 '{t_label}'({t_name}) 主题！"
                )
            return "获取主题失败"

        user_gold = await UserGold.get_user_gold(user_id)
        if user_gold < price:
            return (
                f"金币不足！{f_label}({f_key}) 的 '{t_label}'({t_name})"
                f"主题需要 {price} 金币，你当前只有 {user_gold} 金币"
            )
        if not await UserGold.reduce_user_gold(
            user_id=user_id, amount=price, source="theme_shop"
        ):
            return "金币扣除失败，请稍后再试"

        if await UserTheme.add_owned_theme(user_id, f_key, t_name):
            logger.info(
                f"用户 {user_id} 花费 {price} 金币购买了 "
                f"{f_label}({f_key}) 的 '{t_label}'({t_name}) 主题",
                "UI管理器",
            )
            return (
                f"购买成功！已花费 {price} 金币获取 "
                f"{f_label}({f_key}) 的 '{t_label}'({t_name}) 主题\n"
                f"使用'切换主题 {f_label} {t_label}'来切换"
            )
        await UserGold.add_user_gold(
            user_id=user_id, amount=price, source="theme_shop_refund"
        )
        logger.warning(
            f"用户 {user_id} 购买主题后添加失败，已退还 {price} 金币",
            "UI管理器",
        )
        return "购买失败，金币已退还"

    # ---------- 管理命令 ----------

    async def handle_grant(
        self, target_user_id: str, raw_feature: str, raw_theme: str
    ) -> str:
        """处理为用户授予主题命令（超级用户）。

        参数:
            target_user_id: 目标用户 ID。
            raw_feature: 用户输入的功能名。
            raw_theme: 用户输入的主题名，"默认/default" 表示授予默认主题。

        返回:
            str: 授予结果的消息文本。
        """
        if not (parsed := self._parse_feature(raw_feature)):
            return f"未知功能 '{raw_feature}'，可用功能: {self._features_hint()}"
        f_key, page_path = parsed
        f_label = self._feature_label(f_key)

        if raw_theme in DEFAULT_THEME_NAMES:
            t_name = "default"
        elif not page_path:
            return f"功能 '{f_label}' 无可用主题"
        elif not (t_name := self._parse_theme(page_path, raw_theme)):
            return (
                f"功能 '{f_label}' 不存在主题 '{raw_theme}'\n"
                f"可用主题: {self._themes_hint(page_path)}"
            )

        if await UserTheme.add_owned_theme(target_user_id, f_key, t_name):
            t_label = (
                "默认"
                if t_name == "default"
                else render_service.get_theme_label(page_path, t_name)
            )
            logger.info(
                f"已为用户 {target_user_id} 授予 {f_label}({f_key}) 功能的 "
                f"'{t_label}'({t_name}) 主题",
                "UI管理器",
            )
            return (
                f"已为用户 {target_user_id} 授予 {f_label}({f_key}) 功能的 "
                f"'{t_label}'({t_name}) 主题"
            )
        return "授予主题失败，用户可能已拥有该主题"

    async def handle_revoke(
        self, target_user_id: str, raw_feature: str, raw_theme: str
    ) -> str:
        """处理撤销用户主题命令（超级用户）。

        撤销的主题若正被目标用户使用，会自动切回默认主题。

        参数:
            target_user_id: 目标用户 ID。
            raw_feature: 用户输入的功能名。
            raw_theme: 用户输入的主题名。

        返回:
            str: 撤销结果的消息文本。
        """
        if raw_theme in DEFAULT_THEME_NAMES:
            return "无法撤销默认主题"
        if not (parsed := self._parse_feature(raw_feature)):
            return f"未知功能 '{raw_feature}'，可用功能: {self._features_hint()}"
        f_key, page_path = parsed
        f_label = self._feature_label(f_key)

        if not page_path:
            return f"功能 '{f_label}' 无可用主题"
        if not (t_name := self._parse_theme(page_path, raw_theme)):
            return f"功能 '{f_label}' 不存在主题 '{raw_theme}'"

        if not await UserTheme.remove_owned_theme(target_user_id, f_key, t_name):
            return "撤销主题失败，用户可能不拥有该主题"

        if await UserTheme.get_current_theme(target_user_id, f_key) == t_name:
            await UserTheme.set_current_theme(target_user_id, f_key, "default")
        t_label = render_service.get_theme_label(page_path, t_name)
        logger.info(
            f"已撤销用户 {target_user_id} 的 {f_label}({f_key}) 功能的 "
            f"'{t_label}'({t_name}) 主题",
            "UI管理器",
        )
        return (
            f"已撤销用户 {target_user_id} 的 {f_label}({f_key}) 功能的 "
            f"'{t_label}'({t_name}) 主题"
        )

    async def handle_page_themes(self, raw_feature: str | None) -> str:
        """处理查看页面级主题命令。

        参数:
            raw_feature: 用户输入的功能名；为 None 时输出全部功能与主题。

        返回:
            str: 功能与主题列表的消息文本。
        """
        features = self._features()
        if raw_feature is None:
            lines = ["可用功能及主题:"]
            for f_key, info in sorted(features.items()):
                try:
                    theme_str = self._themes_hint(info["page_path"])
                except Exception:
                    theme_str = "获取失败"
                lines.append(f"  [{f_key}]({info['label']}): {theme_str}")
            return "\n".join(lines)

        if not (f_key := render_service.resolve_feature_key(raw_feature)):
            return f"未知功能 '{raw_feature}'，可用功能: {self._features_hint()}"
        info = features.get(f_key)
        if not info:
            return f"未知功能 '{raw_feature}'"

        page_path = info["page_path"]
        themes = render_service.list_page_themes(page_path)
        if not themes:
            return f"{info['label']}({f_key}) 暂无可用主题"
        theme_lines = [
            f"  - {render_service.get_theme_label(page_path, t)}({t}) "
            f"({self._format_price(render_service.get_theme_price(page_path, t))})"
            for t in themes
        ]
        return f"{info['label']}({f_key}) 可用主题:\n" + "\n".join(theme_lines)

    # ---------- 内部辅助 ----------

    def _parse_feature(self, label_or_key: str) -> tuple[str, str | None] | None:
        """解析功能标识。

        参数:
            label_or_key: 中文功能标签或英文功能键。

        返回:
            tuple[str, str | None] | None: (功能键, 页面路径)，
                功能未知时返回 None。
        """
        f_key = render_service.resolve_feature_key(label_or_key)
        if not f_key:
            return None
        return f_key, self._feature_info(f_key).get("page_path")

    def _parse_theme(self, page_path: str, label_or_name: str) -> str | None:
        """解析主题名称。

        参数:
            page_path: 功能对应的页面路径。
            label_or_name: 中文标签或英文目录名。

        返回:
            str | None: 匹配的主题目录名，未匹配时返回 None。
        """
        return render_service.resolve_theme_name(page_path, label_or_name)


theme_service = ThemeCommandService()
