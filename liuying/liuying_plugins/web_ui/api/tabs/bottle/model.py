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


class BottleListItem(BaseModel):
    """漂流瓶列表项（精简版，不含图片数据）"""

    id: int
    """漂流瓶ID"""
    content: str
    """文本内容"""
    user_id: str
    """发送者用户ID"""
    platform: str
    """发送平台"""
    status: int
    """状态: 0待审核, 100已拒绝, 200已通过"""
    like_count: int
    """点赞数"""
    create_time: datetime
    """创建时间"""
    image_count: int
    """图片数量"""


class BottleBatchDeletePayload(BaseModel):
    """批量删除漂流瓶请求体"""

    ids: list[int]
    """待删除的漂流瓶ID列表"""


class BottleBatchDeleteResult(BaseModel):
    """批量删除结果"""

    success: list[int]
    """成功删除的ID列表"""
    failed: list[int]
    """删除失败的ID列表"""
    total: int
    """传入总数"""


class BottleImagesResult(BaseModel):
    """漂流瓶图片查询结果"""

    bottle_id: int
    """漂流瓶ID"""
    images: list[str]
    """base64 编码图片列表"""
