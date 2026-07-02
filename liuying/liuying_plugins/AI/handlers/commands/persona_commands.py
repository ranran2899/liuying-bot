"""人格命令处理

注册bot人格切换与用户画像查看命令。
"""

from nonebot_plugin_alconna import (
    Alconna,
    Args,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo

from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from ...core.persona import persona_manager

__all__ = ["setup_persona_commands"]


def setup_persona_commands() -> None:
    """注册人格相关matcher

    - bot人格切换 [name]: 切换/查看可用人格
    - 我的画像: 查看当前用户画像
    """
    persona_cmd = on_alconna(
        Alconna("bot人格切换", Args["name?", str]),
        aliases={"AI人格切换", "bot人设切换"},
        priority=49,
        block=True,
    )

    profile_cmd = on_alconna(
        Alconna("我的画像"),
        aliases={"查看我的画像"},
        priority=49,
        block=True,
    )

    @persona_cmd.handle()
    async def _handle_persona(
        session: Uninfo, name: str = ""
    ) -> None:
        """切换AI人格

        无参数时展示所有可用bot人格列表及简要说明；
        带参数时切换当前用户的bot人格（用户级隔离）。
        """
        user_id = session.user.id

        # 无参：展示人格列表及描述
        if not name:
            try:
                current = await persona_manager.get_user_persona_name(
                    user_id
                )
            except Exception:
                current = persona_manager.get_active_persona_name()
            personas = persona_manager.list_personas_with_desc()
            if not personas:
                await MessageUtils.build_message(
                    "暂无可用的人格配置"
                ).finish()
                return
            lines = [f"当前人格: {current}", "可用人格列表:"]
            for p in personas:
                display = p.get("display_name") or p.get("name", "")
                mark = " *" if p.get("name") == current else ""
                lines.append(f"- {display}（{p['name']}）{mark}")
            lines.append("\n使用: bot人格切换 <人格名>")
            await MessageUtils.build_message(
                "\n".join(lines)
            ).finish()
            return

        # 带参：切换用户人格
        err_msg = ""
        try:
            await persona_manager.set_user_persona(user_id, name)
        except FileNotFoundError:
            err_msg = f"人格 '{name}' 不存在，使用 'bot人格切换' 查看可用列表"
        except Exception as e:
            logger.warning(
                f"切换人格失败: {e}", command="AI", e=e
            )
            err_msg = f"切换人格失败: {e}"

        if err_msg:
            await MessageUtils.build_message(err_msg).finish()
            return

        await MessageUtils.build_message(
            f"已切换人格: {name}\n（仅对你生效，对话与记忆已隔离）"
        ).finish()

    @profile_cmd.handle()
    async def _handle_profile(session: Uninfo) -> None:
        """查看用户画像"""
        user_id = session.user.id
        persona = await persona_manager.get_user_persona(user_id)
        if persona:
            await MessageUtils.build_message(
                f"你的画像:\n{persona}"
            ).finish()
        else:
            await MessageUtils.build_message(
                "还没有你的画像记录，多聊几次吧~"
            ).finish()
