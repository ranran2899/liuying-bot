"""统一技能层

本包是 AI 插件所有可插拔技能的唯一入口，职责边界如下：

- `api.py`：`SkillRuntime` 依赖注入载体，技能包访问主插件服务的唯一通道
- `loader.py`：标准技能包的发现、元数据解析、模块加载与工具注册
- `skillpacks/`：全部标准技能包，每个技能一个目录，五件套结构

MCP 协议桥（`agent/mcp_bridge.py`）属于 Agent 侧基础设施，
由本层调用而不在本层实现。
"""

from .api import SkillRuntime
from .loader import (
    SkillLoadReport,
    SkillpackLoader,
    SkillSpec,
    skill_loader,
)

__all__ = [
    "SkillLoadReport",
    "SkillRuntime",
    "SkillSpec",
    "SkillpackLoader",
    "skill_loader",
]
