"""主动行为任务

群空闲发话、私聊问候等定时任务。
基于 task_manager 注册定时任务。
所有提示词通过 persona_manager 的场景化模板渲染，
确保切换默认人设后主动行为也保持一致风格。
"""

from datetime import datetime, timedelta

from nonebot_plugin_alconna import Target

from liuying.models._user.user_info import UserInfo
from liuying.utils.apscheduler import task_manager
from liuying.utils.log import logger
from liuying.utils.message import MessageUtils

from ..config import get_config
from ..core.context import context_manager
from ..core.llm import llm_helper
from ..core.llm.model_router import ROLE_WARMUP, model_router
from ..core.persona import persona_manager
from ..core.tools.json_utils import extract_json_payload
from ..models.group_context import GroupContextSnapshot

_PROACTIVE_TASK_ID = "ai_proactive_group_message"
"""群主动发话任务ID"""

_PROACTIVE_PRIVATE_TASK_ID = "ai_proactive_private_greeting"
"""私聊问候任务ID"""

_PROACTIVE_FAVOR_THRESHOLD = 5
"""私聊问候触发的好感度阈值（亲密及以上）"""


class ProactiveHelper:
    """主动行为辅助工具类

    封装群空闲发话、私聊问候等任务逻辑。
    """

    @staticmethod
    async def _check_group_idle_and_send() -> None:
        """检查群空闲状态并主动发话

        遍历所有群上下文，对长时间无活动的群决策是否主动发话。
        深夜静默时段（默认0-7点跨午夜）跳过。
        """
        if not get_config("PROACTIVE", {}).get("enabled", True):
            return

        if context_manager.is_rest_time():
            return

        groups = await GroupContextSnapshot.filter(
            is_active=True
        ).all()

        if not groups:
            return

        idle_threshold = datetime.now() - timedelta(
            minutes=get_config("PROACTIVE", {}).get("group_idle_minutes", 90)
        )
        daily_limit = get_config("PROACTIVE", {}).get("daily_limit", 3)
        sent_count = 0

        for group in groups:
            if sent_count >= daily_limit:
                break

            last_active = group.last_activity_time
            if last_active and last_active > idle_threshold:
                continue

            if not context_manager.is_group_active_hour(
                group.group_id,
                quiet_start=get_config("GROUP_QUIET", {}).get("start", 0),
                quiet_end=get_config("GROUP_QUIET", {}).get("end", 7),
            ):
                logger.debug(
                    f"群 {group.group_id} 处于深夜静默时段，跳过",
                    command="AI",
                    group_id=group.group_id,
                )
                continue

            try:
                should_send, message = (
                    await ProactiveHelper._decide_proactive_message(
                        group.group_id,
                        group.style or "",
                        last_active,
                    )
                )
                if should_send and message:
                    await ProactiveHelper._send_proactive_message(
                        group.group_id, message
                    )
                    sent_count += 1
            except Exception as e:
                logger.debug(
                    f"群主动发话失败 {group.group_id}: {e}",
                    command="AI",
                    e=e,
                )

    @staticmethod
    async def _decide_proactive_message(
        group_id: str,
        group_style: str,
        last_active: datetime | None,
    ) -> tuple[bool, str]:
        """让LLM决策是否主动发话

        参数:
            group_id: 群组ID
            group_style: 群风格描述
            last_active: 最近活跃时间

        返回:
            tuple[bool, str]: (是否发送, 消息内容)
        """
        period = context_manager.get_current_time_period()
        time_flavor = context_manager.get_time_flavor_prompt()
        last_active_str = (
            last_active.strftime("%Y-%m-%d %H:%M")
            if last_active
            else "未知"
        )

        persona = persona_manager.get_default_persona()
        persona_name = persona.get("name") or "AI"
        interests_list = persona.get("interests") or []
        topics_list = persona.get("proactive_topics") or []
        if not isinstance(interests_list, list):
            interests_list = []
        if not isinstance(topics_list, list):
            topics_list = []
        interests_str = (
            "、".join(str(i) for i in interests_list)
            if interests_list
            else "未指定"
        )
        topics_str = (
            "、".join(str(t) for t in topics_list)
            if topics_list
            else "无"
        )
        prompt = (
            f"现在群里安静了一段时间，作为{persona_name}，"
            "决定是否要主动说点什么。\n\n"
            f"当前时段: {period}\n"
            f"时段氛围: {time_flavor}\n"
            f"群风格: {group_style or '未设置'}\n"
            f"最近活跃时间: {last_active_str}\n"
            f"兴趣领域: {interests_str}\n"
            f"建议话题: {topics_str}\n\n"
            "请用JSON格式返回决策:\n"
            "- should_send: 是否发送消息（true/false）\n"
            "- message: 要发送的消息内容（should_send为true时填写，不超过50字）\n"
            "- reason: 决策理由\n\n"
            "只返回JSON，不要其他内容。"
        )

        try:
            role = model_router.resolve(ROLE_WARMUP)
            response = await llm_helper.chat_text(
                [{"role": "user", "content": prompt}],
                model=role.model or None,
                options=role.apply_to_options(),
                provider_name=role.provider or None,
            )
            data = extract_json_payload(response)
            if data is None:
                return False, ""
            return bool(data.get("should_send", False)), str(
                data.get("message", "")
            )
        except Exception as e:
            logger.debug(
                f"决策主动发话失败: {e}", command="AI", e=e
            )
            return False, ""

    @staticmethod
    async def _send_proactive_message(
        group_id: str, message: str
    ) -> None:
        """发送主动消息到群

        参数:
            group_id: 群组ID
            message: 消息内容
        """
        try:
            target = Target(
                id=group_id, parent="", channel=False
            )
            await MessageUtils.build_message(message).send(
                target=target
            )
            await context_manager.update_group_activity(group_id)
            logger.info(
                f"群主动发话: {group_id} -> {message[:30]}",
                command="AI",
            )
        except Exception as e:
            logger.warning(
                f"发送主动消息失败: {e}", command="AI", e=e
            )

    @staticmethod
    async def _proactive_private_greeting() -> None:
        """私聊问候任务

        每天8点和22点检查高好感度用户发送早晚安问候。
        仅向 favor_value >= _PROACTIVE_FAVOR_THRESHOLD 的用户发送，
        每次执行受 PROACTIVE_DAILY_LIMIT 限制。
        """
        if not get_config("PROACTIVE", {}).get("enabled", True):
            return

        hour = datetime.now().hour
        if hour not in (8, 22):
            return

        greeting_type = "早安" if hour == 8 else "晚安"

        daily_limit = get_config("PROACTIVE", {}).get("daily_limit", 3)
        sent_count = 0

        users = await UserInfo.filter(
            favor_value__gte=_PROACTIVE_FAVOR_THRESHOLD
        ).all()

        if not users:
            return

        for user in users:
            if sent_count >= daily_limit:
                break
            if not user.user_id:
                continue
            try:
                message = (
                    await ProactiveHelper._generate_greeting(
                        greeting_type, user.user_id
                    )
                )
                if not message:
                    continue
                await ProactiveHelper._send_private_greeting(
                    user.user_id, message
                )
                sent_count += 1
            except Exception as e:
                logger.debug(
                    f"私聊问候失败 {user.user_id}: {e}",
                    command="AI",
                    e=e,
                )

        if sent_count > 0:
            logger.info(
                f"私聊问候任务完成: {greeting_type}，"
                f"已发送 {sent_count} 条",
                command="AI",
            )

    @staticmethod
    async def _generate_greeting(
        greeting_type: str,
        user_id: str | None = None,
    ) -> str:
        """生成问候消息

        参数:
            greeting_type: 问候类型（早安/晚安）
            user_id: 目标用户ID，用于按用户切换的人格口吻生成

        返回:
            str: 问候消息，失败返回空串
        """
        try:
            persona_name = (
                persona_manager.get_user_persona_name(user_id)
                if user_id
                else "AI"
            )
            prompt = (
                f"请以{persona_name}的口吻为一位高好感度好友"
                f"发送一条{greeting_type}问候。\n\n"
                "要求：\n"
                "1. 自然亲切，符合好友关系\n"
                "2. 不超过30字\n"
                "3. 不要使用称呼，直接说问候内容\n\n"
                "只返回问候文本，不要其他内容。"
            )
            role = model_router.resolve(ROLE_WARMUP)
            response = await llm_helper.chat_text(
                [{"role": "user", "content": prompt}],
                model=role.model or None,
                options=role.apply_to_options(),
                provider_name=role.provider or None,
            )
            return response.strip()
        except Exception as e:
            logger.debug(
                f"生成问候消息失败: {e}", command="AI", e=e
            )
            return ""

    @staticmethod
    async def _send_private_greeting(
        user_id: str, message: str
    ) -> None:
        """发送私聊问候

        参数:
            user_id: 用户ID
            message: 问候消息
        """
        try:
            target = Target(user_id, private=True)
            await MessageUtils.build_message(message).send(
                target=target
            )
            logger.info(
                f"私聊问候已发送: {user_id} -> {message[:20]}",
                command="AI",
            )
        except Exception as e:
            logger.warning(
                f"发送私聊问候失败: {e}", command="AI", e=e
            )


async def setup_proactive_jobs() -> None:
    """注册主动行为定时任务"""
    if not get_config("PROACTIVE", {}).get("enabled", True):
        logger.info("主动行为任务已禁用", command="AI")
        return

    interval_minutes = get_config("PROACTIVE", {}).get("interval_minutes", 30)
    await task_manager.add_interval(
        task_id=_PROACTIVE_TASK_ID,
        func=ProactiveHelper._check_group_idle_and_send,
        minutes=interval_minutes,
        name="AI群主动发话",
        group="ai_plugin",
        description="检查群空闲状态并主动发话",
        replace_existing=True,
    )
    logger.info(
        f"主动行为任务已注册，间隔{interval_minutes}分钟",
        command="AI",
    )

    # 注册私聊问候任务（每天8点和22点执行）
    await task_manager.add_cron(
        task_id=_PROACTIVE_PRIVATE_TASK_ID,
        func=ProactiveHelper._proactive_private_greeting,
        hour="8,22",
        minute=0,
        name="AI私聊问候",
        group="ai_plugin",
        description="每天早晚向高好感用户发送问候",
        replace_existing=True,
    )
    logger.info("私聊问候任务已注册（每天8:00和22:00）", command="AI")
