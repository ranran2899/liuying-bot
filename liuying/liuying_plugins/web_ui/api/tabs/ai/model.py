"""AI 标签页数据模型

定义流萤AI插件管理接口使用的Pydantic请求/响应模型，
覆盖配置更新、功能开关、人格切换等结构化交互场景。
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
    group_id: str = Field(default="", description="群组ID")
    user_id: str = Field(default="", description="用户ID")


class ConfigEntryView(BaseModel):
    """配置项视图"""

    key: str
    value: Any = None
    value_type: str = "str"
    help_text: str = ""
    default_value: Any = None
    group: str = ""


class ConfigEntriesResponse(BaseModel):
    """配置项列表响应"""

    entries: list[ConfigEntryView] = Field(default_factory=list)
    groups: list[str] = Field(default_factory=list)


class ConfigValueUpdate(BaseModel):
    """配置项更新请求体"""

    key: str = Field(..., description="配置键名")
    value: Any = Field(..., description="配置值")


class PersonaSwitchRequest(BaseModel):
    """人格切换请求体"""

    user_id: str = Field(default="", description="用户ID")
    persona_name: str = Field(default="", description="人格名")


class GlobalPersonaRequest(BaseModel):
    """全局人格切换请求体"""

    persona_name: str = Field(..., description="人格名")


class VisionPreferredRequest(BaseModel):
    """视觉首选provider设置请求体"""

    provider: str = Field(..., description="provider名")
    model: str = Field(..., description="模型名")


class MemoryClearRequest(BaseModel):
    """记忆清理请求体"""

    user_id: str = Field(..., description="用户ID")
    group_id: str = Field(default="", description="群组ID")
    persona_name: str = Field(default="default", description="人格名")
