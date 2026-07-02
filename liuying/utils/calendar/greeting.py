"""
时间问候语工具模块
"""
from datetime import datetime
import random


class Greeting:
    """时间问候语工具类"""

    GREETINGS = {
        "midnight": [
            "还不睡呀？注意身体",
            "夜深了，早点休息",
            "还在忙碌吗？劳逸结合",
            "深夜好，辛苦了"
        ],
        "early_morning": [
            "这么早呀，早安",
            "清晨好，早安",
            "新的一天，早安",
            "早安，元气满满"
        ],
        "morning": [
            "早安，今天也要加油",
            "早上好，美好的一天",
            "早安，愿你心情愉快",
            "早上好，记得吃早餐"
        ],
        "forenoon": [
            "上午好，工作顺利",
            "上午好，记得多喝水",
            "上午好，有什么计划",
            "上午好，保持好心情"
        ],
        "noon": [
            "中午好，记得吃饭",
            "午饭时间到啦，休息一下",
            "中午好，今天怎么样",
            "午安，休息一下吧"
        ],
        "afternoon": [
            "下午好，继续加油",
            "下午好，下午茶时间",
            "下午好，今天辛苦了",
            "下午好，保持好状态"
        ],
        "evening": [
            "傍晚好，准备下班了",
            "傍晚好，今天如何",
            "傍晚好，记得吃晚饭",
            "傍晚好，辛苦了一天"
        ],
        "night": [
            "晚上好，今天辛苦了",
            "晚上好，早点休息",
            "晚上好，放松一下",
            "夜幕降临，早点休息"
        ]
    }

    @classmethod
    def get_greeting(cls) -> str:
        """获取当前时间段的问候语
        
        返回:
            str: 问候语文本
        """
        current_hour = datetime.now().hour
        if 0 <= current_hour < 5:
            time_period = "midnight"
        elif 5 <= current_hour < 7:
            time_period = "early_morning"
        elif 7 <= current_hour < 9:
            time_period = "morning"
        elif 9 <= current_hour < 11:
            time_period = "forenoon"
        elif 11 <= current_hour < 13:
            time_period = "noon"
        elif 13 <= current_hour < 17:
            time_period = "afternoon"
        elif 17 <= current_hour < 19:
            time_period = "evening"
        else:
            time_period = "night"
        return random.choice(cls.GREETINGS.get(time_period, ["再见真好！"]))
