"""漂流瓶管理 WebUI 数据模型"""
from datetime import datetime

from pydantic import BaseModel


class BottleReviewItem(BaseModel):
    """漂流瓶审核数据"""

    id: int
    """漂流瓶ID"""
    content: str
    """文本内容"""
    user_id: str
    """发送者用户ID"""
    uid: str
    """发送者UID"""
    platform: str
    """发送平台"""
    status: int
    """状态: 0待审核, 100已拒绝, 200已通过"""
    like_count: int
    """点赞数"""
    create_time: datetime
    """创建时间"""
    images: list[str]
    """图片base64列表"""


class CommentReviewItem(BaseModel):
    """评论审核数据"""

    id: int
    """评论ID"""
    bottle_id: int
    """关联漂流瓶ID"""
    content: str
    """评论内容"""
    user_id: str
    """评论者用户ID"""
    uid: str
    """评论者UID"""
    status: int
    """状态: 0待审核, 100已拒绝, 200已通过"""
    create_time: datetime
    """创建时间"""


class BottleReviewStats(BaseModel):
    """漂流瓶审核统计"""

    pending_bottles: int
    """待审核瓶子数量"""
    pending_comments: int
    """待审核评论数量"""
    total_bottles: int
    """瓶子总数"""
    total_comments: int
    """评论总数"""


class BottleOperationResult(BaseModel):
    """漂流瓶操作结果"""

    id: int
    """操作对象ID"""
    status: str
    """操作结果状态"""
