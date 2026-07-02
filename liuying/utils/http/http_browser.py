"""Playwright浏览器工具模块，提供页面管理与截图能力。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_htmlrender import get_browser
from playwright.async_api import ElementHandle, Page

from liuying.utils.message import MessageUtils

_DEFAULT_VIEWPORT = {"width": 2560, "height": 1080}


class BrowserIsNone(Exception):
    """浏览器实例不可用异常。"""


class AsyncPlaywright:
    """Playwright 浏览器异步工具类，提供页面管理与截图能力。"""

    @staticmethod
    def _normalize_cookies(
        cookies: list[dict[str, Any]] | dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """将cookies统一转换为列表格式。

        参数:
            cookies: 单个cookie字典或cookie列表。

        返回:
            cookie字典列表。
        """
        match cookies:
            case None:
                return []
            case dict():
                return [cookies]
            case list():
                return cookies
            case _:
                return []

    @classmethod
    @asynccontextmanager
    async def new_page(
        cls,
        cookies: list[dict[str, Any]] | dict[str, Any] | None = None,
        **kwargs,
    ) -> AsyncGenerator[Page, None]:
        """获取一个新页面，自动管理上下文生命周期。

        参数:
            cookies: cookie字典或列表，自动归一化。
            **kwargs: 传递给 browser.new_context 的参数。

        返回:
            Page: Playwright 页面对象。
        """
        browser = await get_browser()
        ctx = await browser.new_context(**kwargs)
        cookie_list = cls._normalize_cookies(cookies)
        if cookie_list:
            await ctx.add_cookies(cookie_list)  # type: ignore
        page = await ctx.new_page()
        try:
            yield page
        finally:
            await page.close()
            await ctx.close()

    @classmethod
    async def screenshot(
        cls,
        url: str,
        path: Path | str,
        element: str | list[str],
        *,
        wait_time: int | None = None,
        viewport_size: dict[str, int] | None = None,
        wait_until: Literal[
            "domcontentloaded", "load", "networkidle"
        ] = "networkidle",
        timeout: float | None = None,
        type_: Literal["jpeg", "png"] | None = None,
        user_agent: str | None = None,
        cookies: list[dict[str, Any]] | dict[str, Any] | None = None,
        **kwargs,
    ) -> UniMessage | None:
        """快捷截图方法，复杂截图请直接操作 page。

        参数:
            url: 目标网址。
            path: 截图存储路径。
            element: CSS选择器，支持单个或列表依次查找。
            wait_time: 元素等待超时时间(秒)，自动转为毫秒。
            viewport_size: 浏览器窗口大小。
            wait_until: 页面加载等待策略。
            timeout: 请求超时限制。
            type_: 截图保存格式。
            user_agent: 自定义UA。
            cookies: 页面cookie。
            **kwargs: 传递给 new_page 的额外参数。

        返回:
            UniMessage | None: 截图消息，失败返回None。
        """
        path = Path(path) if isinstance(path, str) else path
        element_list = [element] if isinstance(element, str) else element
        ms_wait = wait_time * 1000 if wait_time is not None else None

        async with cls.new_page(
            cookies,
            viewport=viewport_size or _DEFAULT_VIEWPORT,
            user_agent=user_agent,
            **kwargs,
        ) as page:
            await page.goto(url, timeout=timeout, wait_until=wait_until)
            card: Page | ElementHandle | None = page
            for sel in element_list:
                if not card:
                    return None
                card = await card.wait_for_selector(sel, timeout=ms_wait)
            if card:
                await card.screenshot(path=path, timeout=timeout, type=type_)
                return MessageUtils.build_message(path)
        return None
