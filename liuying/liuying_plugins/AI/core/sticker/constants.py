"""AI 插件业务常量

集中定义 AI 插件内部使用的业务标识常量，避免散落在公共模块中。
表情包情绪体系统一在本模块定义单一来源，供策展打分与导入分类
共用，防止两套定义漂移。
"""

# ===== bed_layout 图片来源 =====
SOURCE_AI_STICKER: str = "ai_sticker"
"""AI 插件表情包来源"""

SOURCE_AI_TEMP: str = "ai_temp"
"""AI 插件临时图片来源"""

SOURCE_AI_AVATAR: str = "ai_avatar"
"""AI 插件用户头像来源"""

SOURCE_AI_GENERATED: str = "ai_generated"
"""AI 插件生成图片来源"""

# ===== 表情包情绪体系（策展与导入共用单一来源） =====
STICKER_MOODS: tuple[str, ...] = (
    "happy",
    "sad",
    "excited",
    "angry",
    "shy",
    "calm",
    "warm",
    "playful",
    "greet",
    "bye",
)
"""统一情绪枚举（含 greet/bye 场景情绪，共10种）"""

MOOD_KEYWORDS: dict[str, list[str]] = {
    "happy": ["开心", "高兴", "快乐", "哈哈", "嘻嘻", "^_^", "好耶"],
    "sad": ["难过", "伤心", "哭", "呜呜", "失落"],
    "excited": ["激动", "兴奋", "太棒了", "好棒"],
    "angry": ["生气", "愤怒", "哼", "可恶"],
    "shy": ["害羞", "脸红", "不好意思"],
    "calm": ["嗯", "好的", "了解", "知道", "哦"],
    "warm": ["谢谢", "感谢", "辛苦", "温暖"],
    "playful": ["嘿嘿", "哈哈", "逗", "玩笑"],
    "greet": ["打招呼", "你好", "嗨", "欢迎"],
    "bye": ["再见", "拜拜", "告别", "晚安"],
}
"""情绪 -> 聊天文本关键词映射（策展情绪检测用）"""

MOOD_FILENAMES: dict[str, list[str]] = {
    "happy": ["happy", "smile", "laugh", "joy", "开心", "笑"],
    "sad": ["sad", "cry", "tear", "难过", "哭"],
    "excited": ["excited", "wow", "amazing", "兴奋", "激动"],
    "angry": ["angry", "mad", "huff", "生气", "怒"],
    "shy": ["shy", "blush", "embarrassed", "害羞", "脸红"],
    "calm": ["calm", "ok", "neutral", "平静", "嗯"],
    "warm": ["warm", "love", "heart", "care", "温暖", "谢谢"],
    "playful": ["playful", "fun", "joke", "调侃", "玩笑"],
    "greet": ["hi", "hello", "wave", "打招呼", "嗨"],
    "bye": ["bye", "goodbye", "告别", "再见"],
}
"""情绪 -> 文件名关键词映射（导入自动打标用）"""
