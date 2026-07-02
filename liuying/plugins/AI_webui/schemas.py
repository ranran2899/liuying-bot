"""AI WebUI 数据模型

定义WebUI接口使用的Pydantic请求/响应模型，
覆盖配置更新、功能开关等结构化交互场景。
"""

from typing import Any

from pydantic import BaseModel, Field


class FeatureStatusView(BaseModel):
    """功能开关状态视图"""

    name: str = Field(..., description="功能名")
    enabled: bool = Field(..., description="是否启用")
    source: str = Field(default="global", description="生效来源")
    config_key: str = Field(default="", description="对应配置键")


class RuntimeStatusResponse(BaseModel):
    """运行时开关状态响应"""

    user_id: str = ""
    group_id: str = ""
    features: list[FeatureStatusView] = Field(default_factory=list)


class SwitchUpdateRequest(BaseModel):
    """开关更新请求"""

    feature: str = Field(..., description="功能名")
    enabled: bool = Field(..., description="是否启用")
    group_id: str = Field(default="", description="群组ID（群组级覆盖时使用）")
    user_id: str = Field(default="", description="用户ID（用户级覆盖时使用）")


class SwitchUpdateResponse(BaseModel):
    """开关更新响应"""

    ok: bool = Field(..., description="操作是否成功")
    feature: str = ""
    enabled: bool = False
    scope: str = "global"
    target: str = ""


class ConfigEntryView(BaseModel):
    """配置项视图（脱敏展示）"""

    key: str
    value: Any = None
    value_type: str = "str"
    help_text: str = ""
    secret: bool = False


class ConfigEntriesResponse(BaseModel):
    """配置项列表响应"""

    entries: list[ConfigEntryView] = Field(default_factory=list)
    groups: list[str] = Field(default_factory=list)


class HealthCheckResponse(BaseModel):
    """健康检查响应"""

    status: str = "ok"
    timestamp: str = ""


class MemoryItemView(BaseModel):
    """记忆条目视图"""

    user_id: str = ""
    group_id: str = ""
    content: str = ""
    importance: float = 0.0
    created_at: str = ""


class EmotionStateView(BaseModel):
    """情绪状态视图"""

    user_id: str
    mood: float = 0.0
    energy: float = 0.0
    relation_warmth: float = 0.0
    pending_thoughts: list[str] = Field(default_factory=list)


class GroupContextView(BaseModel):
    """群上下文视图"""

    group_id: str
    style: str = ""
    summary: str = ""
    last_activity: str = ""


class TokenSummaryView(BaseModel):
    """Token统计视图"""

    days: int = 7
    total_input: int = 0
    total_output: int = 0
    total_calls: int = 0
    by_provider: dict[str, Any] = Field(default_factory=dict)
