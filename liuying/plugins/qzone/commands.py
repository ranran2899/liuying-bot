"""QZone 管理命令

注册 QZone cookie 配置与状态查询命令。
统一通过 on_alconna + nonebot_plugin_uninfo 实现多平台支持。
权限通过 admin_check Rule 校验。

命令列表：
- 流萤AI空间 [set|clear] --cookie xxx: 用完整cookie配置
- 流萤AI空间 [set|clear] --p_skey xxx --uin xxx: 用关键字段配置
- 流萤AI空间状态: 查看QZone状态
"""

from datetime import datetime

from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Option,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo

from liuying.utils.log import logger
from liuying.utils.message import MessageUtils
from liuying.utils.rules import admin_check

from .service import qzone_service

__all__ = ["setup_qzone_commands"]


_ADMIN_LEVEL = 5
"""QZone状态查询命令权限等级"""

_COOKIE_LEVEL = 7
"""QZone cookie配置命令权限等级"""


def setup_qzone_commands() -> None:
    """注册QZone管理命令matcher

    在插件启动时调用。cookie配置命令使用 admin_check(7)，
    状态查询命令使用 admin_check(5)。
    """

    qzone_cookie_cmd = on_alconna(
        Alconna(
            "流萤AI空间",
            Args["action", str],
            Option("--cookie", Args["cookie", str], default=""),
            Option("--p_skey", Args["p_skey", str], default=""),
            Option("--uin", Args["uin", str], default=""),
            Option("--skey", Args["skey", str], default=""),
        ),
        aliases={"AI空间"},
        rule=admin_check(_COOKIE_LEVEL),
        priority=48,
        block=True,
    )

    qzone_status_cmd = on_alconna(
        Alconna("流萤AI空间状态"),
        aliases={"AI空间状态"},
        rule=admin_check(_ADMIN_LEVEL),
        priority=48,
        block=True,
    )

    @qzone_cookie_cmd.handle()
    async def _handle_qzone_cookie(
        session: Uninfo,
        action: str = "",
        cookie: str = "",
        p_skey: str = "",
        uin: str = "",
        skey: str = "",
    ) -> None:
        """配置QZone cookie"""
        action = (action or "").strip().lower()

        if action in ("set", "update", "配置", "设置"):
            if cookie:
                qzone_service.update_cookie(cookie=cookie)
            elif p_skey and uin:
                qzone_service.update_cookie(
                    p_skey=p_skey, uin=uin, skey=skey
                )
            else:
                await MessageUtils.build_message(
                    "请提供 --cookie 完整cookie，"
                    "或同时提供 --p_skey 与 --uin"
                ).finish()
                return
            logger.info(
                f"管理员 {session.user.id} 更新QZone cookie",
                command="QZone",
                session=session,
            )
            await MessageUtils.build_message(
                f"QZone cookie已更新，uin={qzone_service.cookie_uin}"
            ).finish()
        elif action in ("clear", "reset", "清除", "重置"):
            qzone_service.clear_cookie()
            await MessageUtils.build_message(
                "QZone cookie已清除"
            ).finish()
        else:
            await MessageUtils.build_message(
                "用法: 流萤AI空间 [set|clear] "
                "--cookie xxx 或 --p_skey xxx --uin xxx [--skey xxx]"
            ).finish()

    @qzone_status_cmd.handle()
    async def _handle_qzone_status(session: Uninfo) -> None:
        """查看QZone状态"""
        enabled = qzone_service.enabled
        uin = qzone_service.cookie_uin or "(未配置)"
        updated_at = qzone_service.cookie_updated_at
        lines = [
            "=== QZone状态 ===",
            f"启用: {'是' if enabled else '否'}",
            f"QQ号: {uin}",
        ]
        if updated_at:
            update_str = datetime.fromtimestamp(
                updated_at
            ).strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"Cookie更新: {update_str}")
        await MessageUtils.build_message(
            "\n".join(lines)
        ).finish()
