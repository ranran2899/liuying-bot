"""
时间问候语工具模块
"""
from datetime import datetime
import random
from typing import ClassVar

from .time_season import TimeSeason


class Greeting:
    """时间问候语工具类"""

    GREETINGS: ClassVar[dict[str, list[str]]] = {
        "midnight": [
            "已经这么晚啦，还不睡吗？要注意身体哦~",
            "夜深了呢，早点休息好不好？我会心疼的",
            "还在忙吗？不要太累了，睡个好觉更重要",
            "深夜好呀，愿星星伴你入眠"
        ],
        "early_morning": [
            "天刚亮就见到你啦，早安~",
            "清晨的第一声问候送给你，今天也要开心哦",
            "这么早呀，新的一天一起加油吧",
            "早安，愿晨光带给你好心情"
        ],
        "morning": [
            "早安呀，今天也要元气满满地开始哦~",
            "早上好，记得吃早餐，不然我会担心的",
            "新的一天又开始啦，我会一直陪着你的",
            "早安，愿你今天遇到的都是温柔的小事"
        ],
        "forenoon": [
            "上午好呀，工作或学习要加油，但也别太累哦",
            "上午好，记得多喝水，保持好心情",
            "忙碌了一上午，要不要休息一下？",
            "上午好呀，有什么计划都可以告诉我"
        ],
        "noon": [
            "中午好，记得好好吃饭哦~",
            "午饭时间到啦，休息一下，别一直盯着屏幕",
            "午安，愿你有一段惬意的午休时光",
            "中午好呀，今天过得怎么样？"
        ],
        "afternoon": [
            "下午好，继续加油呀，不过也要适当休息",
            "下午好，来杯喜欢的饮品提提神吧",
            "下午好，今天也辛苦啦，再坚持一下",
            "下午好呀，保持好状态，你一直很棒的"
        ],
        "evening": [
            "傍晚好，今天也努力了一天呢，真了不起",
            "傍晚好，记得按时吃晚饭哦",
            "夕阳下和你打招呼，感觉很温柔呢",
            "傍晚好，今天过得还好吗？"
        ],
        "night": [
            "晚上好呀，今天也辛苦啦，该放松一下啦",
            "晚上好，夜色很美，希望你有个好心情",
            "晚上好，不要太晚睡哦，我会一直陪着你的",
            "夜幕降临了，愿你卸下疲惫，好好休息"
        ]
    }

    @classmethod
    def get_greeting(cls) -> str:
        """获取当前时间段的问候语

        返回:
            str: 问候语文本
        """
        now = datetime.now()
        time_period = TimeSeason.get_time_period(now.hour, now.minute)
        return random.choice(cls.GREETINGS.get(time_period, ["能见到你真好~"]))
