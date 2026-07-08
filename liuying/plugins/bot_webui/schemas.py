"""本体 WebUI 数据模型

定义本体 WebUI 接口使用的 Pydantic 请求/响应模型，
覆盖机器人账号、插件、群组、定时任务、系统信息等结构化交互场景。
"""

from typing import Any

from pydantic import BaseModel, Field


class BotAccountView(BaseModel):
    """机器人账号视图"""

    bot_id: str = ""
    status: bool = True
    platform: str = ""
    create_time: str = ""
    online: bool = False
    available_plugins: int = 0
    block_plugins: int = 0
    available_tasks: int = 0
    block_tasks: int = 0


class PluginView(BaseModel):
    """插件信息视图"""

    id: int = 0
    module: str = ""
    name: str = ""
    status: bool = True
    load_status: bool = True
    block_type: str | None = None
    author: str | None = None
    version: str | None = None
    level: int = 5
    menu_type: str = ""
    plugin_type: str | None = None
    cost_gold: int = 0
    admin_level: int | None = 0
    is_show: bool = True
    parent: str | None = None


class PluginToggleRequest(BaseModel):
    """插件启用/禁用请求"""

    bot_id: str = Field(..., description="目标机器人ID")
    module: str = Field(..., description="插件模块名")
    enabled: bool = Field(..., description="True启用 False禁用")


class GroupView(BaseModel):
    """群组视图"""

    group_id: str = ""
    channel_id: str | None = None
    group_name: str = ""
    member_count: int = 0
    max_member_count: int = 0
    status: bool = True
    level: int = 5
    is_super: bool = False
    platform: str = "qq"
    proactive_allowed: bool = True


class GroupLevelUpdateRequest(BaseModel):
    """群组权限等级更新请求"""

    group_id: str
    level: int = Field(..., ge=0, le=10)


class GroupStatusUpdateRequest(BaseModel):
    """群组状态更新请求"""

    group_id: str
    status: bool


class TaskView(BaseModel):
    """定时任务视图"""

    id: str = ""
    name: str = ""
    trigger_type: str = ""
    status: str = ""
    group: str = "default"
    description: str = ""
    run_count: int = 0
    last_run_time: str | None = None
    created_at: str = ""
    priority: int = 0
    save_to_db: bool = False


class SystemInfoView(BaseModel):
    """系统信息视图"""

    bot_name: str = ""
    bot_version: str = ""
    python_version: str = ""
    platform: str = ""
    os_release: str = ""
    hostname: str = ""
    cpu_percent: float = 0.0
    cpu_count: int = 0
    memory_total: int = 0
    memory_used: int = 0
    memory_percent: float = 0.0
    disk_total: int = 0
    disk_used: int = 0
    disk_percent: float = 0.0
    process_pid: int = 0
    process_memory_rss: int = 0
    process_threads: int = 0
    uptime_seconds: float = 0.0
    uptime_text: str = ""


class LogFileView(BaseModel):
    """日志文件视图"""

    name: str = ""
    size: int = 0
    modified: str = ""


class LogContentView(BaseModel):
    """日志内容视图"""

    name: str = ""
    lines: list[str] = Field(default_factory=list)
    truncated: bool = False


class StatsSummaryView(BaseModel):
    """调用统计摘要视图"""

    total: int = 0
    by_plugin: dict[str, int] = Field(default_factory=dict)
    by_group: dict[str, int] = Field(default_factory=dict)
    by_user: dict[str, int] = Field(default_factory=dict)
    recent: list[dict[str, Any]] = Field(default_factory=list)
