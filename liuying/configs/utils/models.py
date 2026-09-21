from collections.abc import Callable
from datetime import datetime
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field

from liuying.utils.enum import BlockType, LimitWatchType, PluginLimitType, PluginType

__all__ = [
    "AICallableParam",
    "AICallableProperties",
    "AICallableTag",
    "BaseBlock",
    "Command",
    "ConfigModel",
    "Example",
    "PluginCdBlock",
    "PluginCountBlock",
    "PluginExtraData",
    "PluginSetting",
    "RegisterConfig",
    "SchedulerModel",
    "Task",
]


class Example(BaseModel):
    """示例"""

    exec: str
    """执行命令"""
    description: str = ""
    """命令描述"""


class Command(BaseModel):
    """具体参数说明"""

    command: str
    """命令名称"""
    params: list[str] = Field(default_factory=list)
    """参数"""
    description: str = ""
    """描述"""
    examples: list[Example] = Field(default_factory=list)
    """示例列表"""


class RegisterConfig(BaseModel):
    """注册配置项"""

    key: str
    """配置项键"""
    value: Any
    """配置项值"""
    module: str | None = None
    """模块名"""
    help: str | None
    """配置注解"""
    default_value: Any | None = None
    """默认值"""
    type: Any = None
    """参数类型"""
    arg_parser: Callable | None = None
    """参数解析"""


class ConfigModel(BaseModel):
    """配置项"""

    value: Any
    """配置项值"""
    help: str | None
    """配置注解"""
    default_value: Any | None = None
    """默认值"""
    type: Any = None
    """参数类型"""
    arg_parser: Callable | None = None
    """参数解析"""

    def to_dict(self, **kwargs):
        return self.model_dump(**kwargs)


class BaseBlock(BaseModel):
    """插件阻断基本类（插件阻断限制）"""

    status: bool = True
    """限制状态"""
    check_type: BlockType = BlockType.ALL
    """检查类型"""
    watch_type: LimitWatchType = LimitWatchType.USER
    """监听对象"""
    result: str | None = None
    """阻断时回复内容"""
    _type: ClassVar[PluginLimitType] = PluginLimitType.BLOCK
    """类型"""

    def to_dict(self, **kwargs):
        return self.model_dump(**kwargs)


class PluginCdBlock(BaseBlock):
    """插件cd限制"""

    cd: int = 5
    """cd"""
    _type: ClassVar[PluginLimitType] = PluginLimitType.CD
    """类型"""


class PluginCountBlock(BaseBlock):
    """插件次数限制"""

    max_count: int
    """最大调用次数"""
    _type: ClassVar[PluginLimitType] = PluginLimitType.COUNT
    """类型"""


class PluginSetting(BaseModel):
    """插件基本配置"""

    level: int = 5
    """群权限等级"""
    default_status: bool = True
    """进群默认开关状态"""
    limit_superuser: bool = False
    """是否限制超级用户"""
    cost_gold: int = 0
    """调用插件花费金币"""


class AICallableProperties(BaseModel):
    """参数属性"""
    type: str
    """参数类型"""
    description: str
    """参数描述"""


class AICallableParam(BaseModel):
    """工具参数"""
    type: str
    """类型"""
    properties: dict[str, AICallableProperties]
    """参数列表"""
    required: list[str]
    """必要参数"""


class AICallableTag(BaseModel):
    """工具标签"""
    name: str
    """工具名称"""
    parameters: AICallableParam | None = None
    """工具参数"""
    description: str
    """工具描述"""
    func: Callable | None = None
    """工具函数"""
    intent_tags: list[str] = Field(default_factory=list)
    """意图标签列表，帮助Agent决策何时调用该工具。
    可选值: realtime(实时信息查询), network(网络请求),
    image(图片相关), admin(管理操作), memory(记忆召回),
    local(本地操作), plugin(插件调用)"""
    latency_class: str = "fast"
    """延迟级别: fast(<1s), network(1-5s), slow(>5s)"""
    requires_network: bool = False
    """是否需要网络连接才能执行，Agent可据此在网络不可用时跳过该工具"""
    requires_image: bool = False
    """是否需要图片输入，Agent可据此判断当前对话是否有图片可用"""
    evidence_kind: str = "tool"
    """证据类型，影响Agent循环中对工具结果的引用方式。
    可选值: tool(工具证据), context(上下文证据)"""
    metadata: dict[str, Any] = Field(default_factory=dict)
    """附加元信息"""

    def to_dict(self, **kwargs):
        return self.model_dump(exclude={"func"}, **kwargs)


class SchedulerModel(BaseModel):
    """定时任务配置"""
    id: str | None = None
    """任务ID"""
    trigger: Literal["date", "interval", "cron"]
    """trigger"""
    month: int | str | None = None
    """月份(cron, 支持 1-12 或 "*/3" 表达式)"""
    day: int | str | None = None
    """日期(cron, 支持 1-31 或 "*/2" 表达式)"""
    day_of_week: int | str | None = None
    """星期几(cron, 0=周一, 支持 "0,3" 表达式)"""
    hour: int | str | None = None
    """小时"""
    minute: int | str | None = None
    """分钟"""
    second: int | str | None = None
    """秒"""
    run_date: datetime | None = None
    """运行时间"""
    max_instances: int | None = None
    """最大实例数"""
    args: list | None = None
    """参数"""
    kwargs: dict | None = None
    """关键字参数"""


class Task(BaseBlock):
    """技能被动任务"""

    module: str
    """被动技能模块名"""
    name: str
    """被动技能名称"""
    status: bool = True
    """全局开关状态"""
    create_status: bool = False
    """初次加载默认开关状态"""
    default_status: bool = True
    """进群时默认状态"""
    scheduler: SchedulerModel | None = None
    """定时任务配置"""
    run_func: Callable | None = None
    """运行函数"""
    check: Callable | None = None
    """检查函数"""
    check_args: list = Field(default_factory=list)
    """检查函数参数"""


class PluginExtraData(BaseModel):
    """插件扩展信息"""

    author: str | None = None
    """作者"""
    version: str | None = None
    """版本"""
    plugin_type: PluginType = PluginType.NORMAL
    """插件类型"""
    menu_type: str = "功能"
    """菜单类型"""
    admin_level: int | None = None
    """管理员插件所需权限等级"""
    configs: list[RegisterConfig] | None = None
    """插件配置"""
    setting: PluginSetting | None = None
    """插件基本配置"""
    limits: list[BaseBlock | PluginCdBlock | PluginCountBlock] | None = None
    """插件限制"""
    commands: list[Command] = Field(default_factory=list)
    """命令列表，用于说明帮助"""
    ignore_prompt: bool = False
    """是否忽略阻断提示"""
    tasks: list[Task] | None = None
    """技能被动"""
    superuser_help: str | None = None
    """超级用户帮助"""
    aliases: set[str] = Field(default_factory=set)
    """额外名称"""
    sql_list: list[str] | None = None
    """常用sql"""
    is_show: bool = True
    """是否显示在菜单中"""
    smart_tools: list[AICallableTag] | None = None
    """智能模式函数工具集"""

    def to_dict(self, **kwargs):
        return self.model_dump(**kwargs)
