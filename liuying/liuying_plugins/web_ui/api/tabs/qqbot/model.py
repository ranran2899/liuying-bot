"""QQ机器人配置管理请求模型"""

from pydantic import BaseModel


class AddBot(BaseModel):
    """添加机器人配置请求"""

    user_id: str = "webui"
    """归属用户ID"""
    bot_id: str
    """机器人ID(AppID)"""
    secret: str
    """机器人AppSecret"""
    use_websocket: bool = True
    """是否使用WebSocket"""


class UpdateBot(BaseModel):
    """更新机器人配置请求(仅更新非None字段)"""

    user_id: str
    """归属用户ID"""
    bot_id: str
    """机器人ID(AppID)"""
    secret: str | None = None
    """新AppSecret,None表示不修改"""
    use_websocket: bool | None = None
    """是否使用WebSocket,None表示不修改"""
    intent: dict[str, bool] | None = None
    """完整意图配置,None表示不修改"""


class DeleteBot(BaseModel):
    """删除机器人配置请求"""

    user_id: str
    """归属用户ID"""
    bot_id: str
    """机器人ID(AppID)"""
