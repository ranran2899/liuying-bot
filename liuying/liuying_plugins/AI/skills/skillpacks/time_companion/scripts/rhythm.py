"""时段节律实现

给出当前时段的确定性判定与轻量作息建议，供人格在回复里自然带出。

刻意不调 LLM：时段与作息建议是规则问题，用规则表比让模型自由生成
更稳定、零延迟、零 token，也避免模型把凌晨三点说成「早上好」。
"""

from datetime import datetime

__all__ = ["PHASE_NAMES", "advise", "resolve_phase"]

_Phase = tuple[int, int, str, str, str]
"""时段元组：(起始小时, 结束小时, 时段名, 招呼, 作息建议)"""

_PHASES: tuple[_Phase, ...] = (
    (0, 5, "深夜", "还没睡啊", "这个点该躺下了，熬下去明天一整天都废"),
    (5, 8, "清晨", "早", "刚醒别急着看手机，先喝口水"),
    (8, 11, "上午", "早上好", "上午脑子最清醒，难的事先干掉"),
    (11, 13, "午间", "中午了", "该吃饭了，别拖到下午低血糖"),
    (13, 14, "午后", "下午好", "困的话趴二十分钟，比硬撑管用"),
    (14, 18, "下午", "下午好", "坐久了起来走两步，别一动不动到天黑"),
    (18, 20, "傍晚", "傍晚好", "该收工了，晚饭别糊弄"),
    (20, 23, "夜晚", "晚上好", "留点时间给自己，别一直刷手机"),
    (23, 24, "夜深", "很晚了", "早点睡，明天还有明天的事"),
)
"""时段规则表，按 [起始, 结束) 小时区间划分，覆盖 0-24 全域"""

PHASE_NAMES: tuple[str, ...] = tuple(
    phase[2] for phase in _PHASES
)
"""全部时段名，供文档与测试引用"""

_MOOD_NOTES = {
    "positive": "情绪不错，趁着状态好多做点想做的事",
    "negative": "情绪有点低，别硬扛，做点让自己舒服的事",
    "tired": "看着挺累，优先补觉而不是补进度",
    "neutral": "",
}
"""心情附注，按情绪倾向补一句，未知情绪不附注"""

_LATE_HOURS = (0, 1, 2, 3, 4, 23)
"""需要额外提醒作息的小时，用于加重深夜提示"""


def resolve_phase(hour: int) -> _Phase:
    """按小时定位所属时段

    参数:
        hour: 24小时制小时数

    返回:
        _Phase: 命中的时段元组，越界小时归入深夜
    """
    normalized = hour % 24
    for phase in _PHASES:
        if phase[0] <= normalized < phase[1]:
            return phase
    return _PHASES[0]


def advise(now: datetime, mood: str = "") -> str:
    """生成当前时段的陪伴式描述

    参数:
        now: 带时区的当前时间
        mood: 情绪倾向，取 positive/negative/tired/neutral

    返回:
        str: 时段、招呼、作息建议与心情附注拼成的中文描述
    """
    _, _, name, greeting, tip = resolve_phase(now.hour)
    parts = [
        f"现在是{now:%H:%M}，{name}。",
        f"打招呼可以说「{greeting}」。",
        f"作息提醒：{tip}。",
    ]
    if note := _MOOD_NOTES.get((mood or "").strip().lower(), ""):
        parts.append(f"{note}。")
    if now.hour in _LATE_HOURS:
        parts.append("这个点说话语气可以更轻一些。")
    return "".join(parts)
