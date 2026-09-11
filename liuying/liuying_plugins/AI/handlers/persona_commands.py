"""人格命令逻辑

bot人格切换与用户画像查看的业务处理。
"""

from nonebot_plugin_uninfo import Uninfo

from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from ..agent.warmup_persona import persona_manager
from ..config import get_config

__all__ = [
    "PersonaCommands",
]


class PersonaCommands:
    """人格命令逻辑

    matcher 在插件 __init__ 统一注册，此处仅承接业务逻辑。
    """

    @staticmethod
    async def handle_persona(
        session: Uninfo, name: str = ""
    ) -> None:
        """切换AI人格

        无参数时展示所有可用bot人格列表及简要说明；
        带参数时切换当前用户的bot人格（用户级隔离）。
        """
        if not get_config("ENABLE_AI", False):
            return

        user_id = session.user.id

        # 无参：展示人格列表及描述
        if not name:
            current = await persona_manager.get_user_persona_name(
                user_id
            )
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

    @staticmethod
    async def handle_profile(session: Uninfo) -> None:
        """查看用户画像"""
        if not get_config("ENABLE_AI", False):
            return

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
