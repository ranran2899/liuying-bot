"""群风格自动学习任务

定时分析群聊历史记录，用LLM推断群组风格特征，
自动更新 GroupContextSnapshot.style 字段。

分析维度：
- 语言风格（正式/休闲/玩梗/技术向等）
- 话题偏好（游戏/学习/日常/工作等）
- 群氛围（活跃/安静/友好/竞争等）
- 交流节奏（快节奏/慢节奏/碎片化等）

运行周期：默认12小时，通过 GROUP_STYLE_AUTOBUILD_INTERVAL 配置。
"""

from datetime import datetime, timedelta

from liuying.utils.apscheduler import task_manager
from liuying.utils.log import logger

from ..config import get_config
from ..core.llm import llm_helper
from ..core.llm.model_router import ROLE_WARMUP, model_router
from ..core.tools.json_utils import extract_json_payload
from ..models.conversation_record import ConversationRecord
from ..models.group_context import GroupContextSnapshot

__all__ = ["setup_group_style_autobuild_job"]

_STYLE_TASK_ID = "ai_group_style_autobuild"
"""群风格自动学习任务ID"""

_SAMPLE_LIMIT = 50
"""每次采样消息数"""


async def _analyze_group_style(
    group_id: str,
) -> str:
    """分析群组风格

    从 ConversationRecord 采样群组最近的user消息，
    用LLM推断群组风格特征，返回风格描述文本。

    参数:
        group_id: 群组ID

    返回:
        str: 风格描述文本，分析失败返回空串
    """
    # 采样最近24小时的群聊user消息
    since = datetime.now() - timedelta(hours=24)
    records = await (
        ConversationRecord.filter(
            group_id=group_id,
            role="user",
        )
        .filter(create_time__gte=since)
        .order_by("-create_time")
        .limit(_SAMPLE_LIMIT)
        .all()
    )
    if len(records) < 5:
        logger.debug(
            f"群 {group_id} 采样消息不足5条，跳过风格分析",
            command="AI",
        )
        return ""

    # 构建消息样本文本
    samples: list[str] = []
    for rec in records:
        content = rec.content.strip()[:100]
        if content:
            samples.append(f"- {content}")
    if not samples:
        return ""
    messages_text = "\n".join(samples)

    prompt = (
        "你是群聊风格分析器。\n"
        "分析以下群聊消息样本，推断群组的风格特征。\n"
        "\n"
        "消息样本：\n"
        f"{messages_text}\n"
        "\n"
        "请输出JSON格式（只输出JSON，不要其他内容）：\n"
        "{\n"
        '  "language_style": "语言风格描述（如休闲/正式/玩梗/技术向）",\n'
        '  "topic_preference": "话题偏好描述（如游戏/学习/日常/工作）",\n'
        '  "atmosphere": "群氛围描述（如活跃/安静/友好/竞争）",\n'
        '  "pace": "交流节奏描述（如快节奏/慢节奏/碎片化）",\n'
        '  "summary": "一句话总结群风格"\n'
        "}"
    )
    try:
        role = model_router.resolve(ROLE_WARMUP)
        _, response = await llm_helper.chat(
            [{"role": "user", "content": prompt}],
            model=role.model or None,
            options=role.apply_to_options(
                {"temperature": 0.3}
            ),
            provider_name=role.provider or None,
        )
        data = extract_json_payload(response)
        if data is None:
            return ""
        # 构建风格描述文本
        parts: list[str] = []
        language_style = str(data.get("language_style", "")).strip()
        topic = str(data.get("topic_preference", "")).strip()
        atmosphere = str(data.get("atmosphere", "")).strip()
        pace = str(data.get("pace", "")).strip()
        summary = str(data.get("summary", "")).strip()
        if language_style:
            parts.append(f"语言风格: {language_style}")
        if topic:
            parts.append(f"话题偏好: {topic}")
        if atmosphere:
            parts.append(f"群氛围: {atmosphere}")
        if pace:
            parts.append(f"交流节奏: {pace}")
        if summary:
            parts.append(f"总结: {summary}")
        return " | ".join(parts) if parts else ""
    except Exception as e:
        logger.warning(
            f"群 {group_id} 风格分析失败: {e}",
            command="AI",
            e=e,
        )
        return ""


async def _run_group_style_autobuild() -> None:
    """执行群风格自动学习

    遍历所有群上下文记录，对每个活跃群组采样消息并分析风格，
    更新 GroupContextSnapshot.style 字段。
    """
    if not get_config("GROUP_STYLE_AUTOBUILD", {}).get("enabled", True):
        return
    logger.info(
        "群风格自动学习任务启动",
        command="AI",
    )
    # 前置查询失败不应让定时任务崩溃退出
    try:
        groups = await GroupContextSnapshot.filter(
            is_active=True
        ).all()
    except Exception as e:
        logger.warning(
            f"群风格学习查询活跃群失败: {e}",
            command="AI",
            e=e,
        )
        return
    if not groups:
        logger.debug("无活跃群组，跳过风格学习", command="AI")
        return

    updated = 0
    for group in groups:
        # 单群失败（LLM/DB异常）不中断其余群组的风格学习
        try:
            style = await _analyze_group_style(group.group_id)
            if style:
                await GroupContextSnapshot.update_context(
                    group_id=group.group_id,
                    style=style,
                )
                updated += 1
                logger.debug(
                    f"群 {group.group_id} 风格已更新: {style[:50]}",
                    command="AI",
                )
        except Exception as e:
            logger.warning(
                f"群 {group.group_id} 风格学习失败: {e}",
                command="AI",
                e=e,
            )

    logger.info(
        f"群风格自动学习完成: 共{len(groups)}个群组，"
        f"更新{updated}个",
        command="AI",
    )


async def setup_group_style_autobuild_job() -> None:
    """注册群风格自动学习定时任务

    默认12小时执行一次，通过 GROUP_STYLE_AUTOBUILD_INTERVAL 配置。
    """
    autobuild_cfg = get_config("GROUP_STYLE_AUTOBUILD", {})
    if not autobuild_cfg.get("enabled", True):
        return
    interval_hours = int(autobuild_cfg.get("interval", 12))
    interval_hours = max(1, interval_hours)

    await task_manager.add_interval(
        task_id=_STYLE_TASK_ID,
        func=_run_group_style_autobuild,
        hours=interval_hours,
        name="AI群风格自动学习",
        group="ai_plugin",
        description="定时分析群聊历史推断群组风格",
        replace_existing=True,
    )
    logger.info(
        f"群风格自动学习任务已注册，间隔{interval_hours}小时",
        command="AI",
    )
