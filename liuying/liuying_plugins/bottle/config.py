"""
漂流瓶插件配置
"""
from pydantic import BaseModel


class Config(BaseModel):
    max_bottle_pic: int = 2
    """最大漂流瓶图片数量"""
    max_bottle_lines: int = 9
    """最大漂流瓶文本行数"""
    max_bottle_word: int = 1200
    """最大漂流瓶文本字符数"""
    embedded_help: bool = True
    """是否嵌入帮助信息"""
    cooling_time: int = 6
    """冷却时间，单位秒"""
    default_nickname: str = "未知昵称"
    """默认昵称"""
    bottle_msg_split: bool = True
    """是否将漂流瓶消息拆分成多行"""
    max_bottle_comments: int = 3
    """最大漂流瓶评论数量"""
    bottle_msg_uname: bool = True
    """是否在漂流瓶消息中包含用户昵称"""
    bottle_msg_gname: bool = True
    """是否在漂流瓶消息中包含群昵称"""
    bottle_account: str = "admin"
    """漂流瓶账号"""
    bottle_password: str = "password"
    """漂流瓶密码"""
    expire_time: int = 12
    """漂流瓶过期时间，单位小时"""
    gzip_level: int = 9
    """GZIP压缩等级"""
