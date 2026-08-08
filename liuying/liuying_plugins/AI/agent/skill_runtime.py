"""技能包运行时

标准skillpack结构加载与执行：
- skill.yaml 元数据
- scripts/main.py 入口
- 三种入口模式：register / build_tools / run
- SkillRuntime 依赖注入（参考参考插件 loader.py 设计）

参考 nonebot_plugin_personification 的 skill_runtime/loader.py：
1. build_tools(runtime) 接收 SkillRuntime 参数
2. 动态加载模块时构造合成包，让相对导入可用
3. 注册完成后调用 apply_tool_metadata_defaults 补全默认元数据
"""

from dataclasses import dataclass, field
from datetime import datetime
import importlib.util
from pathlib import Path
import re
import sys
from types import ModuleType
from typing import Any

import yaml

from liuying.utils.log import logger

from ..config import get_config
from .mcp_bridge import mcp_bridge
from .runtime.catalog.tool_catalog import apply_tool_metadata_defaults
from .skill_isolation import skill_isolation_runner
from .skill_runtime_api import SkillRuntime
from .tools import AgentTool, ToolRegistry, tool_registry

__all__ = [
    "SkillSpec",
    "SkillpackLoader",
    "skill_loader",
]


_SKILL_YAML_NAMES: tuple[str, ...] = ("skill.yaml", "skill.yml")
"""skill.yaml文件名候选"""


_ENTRYPOINT_NAMES: tuple[str, ...] = (
    "main.py",
    "run.py",
    "skill.py",
)
"""入口文件候选名"""


@dataclass(slots=True)
class SkillSpec:
    """技能规格

    Attributes:
        name: 技能名
        description: 描述
        category: 分类
        entrypoint: 入口文件路径
        parameters: 参数JSON Schema
        enabled: 是否启用
        metadata: 附加元信息
        isolation: 隔离配置（mode=process时子进程隔离）
    """

    name: str
    description: str = ""
    category: str = "general"
    entrypoint: Path | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    isolation: dict[str, Any] = field(default_factory=dict)


def _build_default_runtime() -> SkillRuntime:
    """构造默认SkillRuntime

    在未显式传入runtime时，从全局单例构建。
    延迟导入避免循环依赖。

    返回:
        SkillRuntime: 默认运行时实例
    """
    # 循环依赖：core.llm 模块在初始化时可能间接引用 AI 插件配置
    from ..core.knowledge_db import knowledge_base
    from ..core.llm import llm_helper
    from ..core.memory import memory_manager
    from ..core.persona import persona_manager

    return SkillRuntime(
        plugin_config=get_config,
        logger=logger,
        get_now=datetime.now,
        llm_helper=llm_helper,
        memory_manager=memory_manager,
        knowledge_base=knowledge_base,
        persona_manager=persona_manager,
    )


class SkillpackLoader:
    """技能包加载器

    扫描skillpacks目录，加载所有技能并注册到工具注册表。
    通过SkillRuntime依赖注入，让技能包访问主插件服务。
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        """初始化技能包加载器

        参数:
            base_dir: skillpacks根目录
        """
        if base_dir is None:
            base_dir = Path(__file__).parent / "skillpacks"
        self._base_dir = base_dir
        self._skills: dict[str, SkillSpec] = {}

    @property
    def base_dir(self) -> Path:
        """获取skillpacks根目录"""
        return self._base_dir

    def discover_skills(self) -> list[SkillSpec]:
        """扫描发现所有技能

        返回:
            list[SkillSpec]: 技能规格列表
        """
        if not self._base_dir.exists():
            return []

        specs: list[SkillSpec] = []
        for item in sorted(self._base_dir.iterdir()):
            if not item.is_dir():
                continue
            spec = self._load_skill_spec(item)
            if spec:
                specs.append(spec)
                self._skills[spec.name] = spec

        logger.info(
            f"发现{len(specs)}个技能包",
            command="AI",
        )
        return specs

    def _load_skill_spec(
        self, skill_dir: Path
    ) -> SkillSpec | None:
        """加载单个技能规格

        参数:
            skill_dir: 技能目录

        返回:
            SkillSpec | None: 技能规格
        """
        frontmatter: dict[str, Any] = {}

        for yaml_name in _SKILL_YAML_NAMES:
            yaml_path = skill_dir / yaml_name
            if yaml_path.exists():
                try:
                    data = yaml.safe_load(
                        yaml_path.read_text(encoding="utf-8")
                    )
                    if isinstance(data, dict):
                        frontmatter = data
                    break
                except Exception as e:
                    logger.warning(
                        f"加载skill.yaml失败 {skill_dir.name}: {e}",
                        command="AI",
                        e=e,
                    )

        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists() and not frontmatter:
            try:
                text = skill_md.read_text(encoding="utf-8")
                frontmatter, _ = self._extract_frontmatter(text)
            except (yaml.YAMLError, OSError):
                pass

        name = str(
            frontmatter.get("name") or skill_dir.name
        )
        entrypoint = self._resolve_entrypoint(
            skill_dir, frontmatter
        )
        if entrypoint is None:
            logger.debug(
                f"技能 {name} 未找到入口文件，跳过",
                command="AI",
            )
            return None

        return SkillSpec(
            name=name,
            description=str(frontmatter.get("description", "")),
            category=str(frontmatter.get("category", "general")),
            entrypoint=entrypoint,
            parameters=frontmatter.get("parameters", {}),
            enabled=bool(frontmatter.get("enabled", True)),
            metadata=frontmatter,
            isolation=frontmatter.get("isolation", {}),
        )

    def register_all(
        self,
        registry: ToolRegistry = tool_registry,
        runtime: SkillRuntime | None = None,
    ) -> int:
        """注册所有技能到工具注册表

        参考参考插件 load_builtin_skillpacks_sync 设计：
        通过 SkillRuntime 依赖注入，将主插件服务传递给技能包。

        参数:
            registry: 工具注册表
            runtime: 技能运行时（依赖注入载体），None时构造默认实例

        返回:
            int: 注册成功的工具数
        """
        use_runtime = runtime or _build_default_runtime()
        specs = self.discover_skills()
        registered = 0

        for spec in specs:
            if not spec.enabled or spec.entrypoint is None:
                continue
            # 非可信技能使用子进程隔离执行
            if spec.isolation.get("mode") == "process":
                registered += self._register_isolated_skill(
                    spec, registry
                )
                continue
            module = self._load_skill_module(
                spec.entrypoint, spec
            )
            registered += self._register_module(
                module, spec, registry, use_runtime
            )

        # 补全默认元数据（参考参考插件 apply_tool_metadata_defaults）
        apply_tool_metadata_defaults(registry)

        logger.info(
            f"技能包注册完成，共{registered}个工具",
            command="AI",
        )
        return registered

    def _register_module(
        self,
        module: Any,
        spec: SkillSpec,
        registry: ToolRegistry,
        runtime: SkillRuntime,
    ) -> int:
        """按三段式接口注册技能模块

        参考参考插件 loader.py 的三段式注册接口：
        register > build_tools > run

        参数:
            module: 技能模块
            spec: 技能规格
            registry: 工具注册表
            runtime: 技能运行时

        返回:
            int: 注册的工具数
        """
        if hasattr(module, "register"):
            # register(runtime, registry) 模式
            try:
                module.register(runtime, registry)
            except TypeError:
                module.register(registry)
            return 1
        if hasattr(module, "build_tools"):
            # build_tools(runtime) 模式
            try:
                tools = module.build_tools(runtime)
            except TypeError:
                tools = module.build_tools()
            if not tools:
                return 0
            count = 0
            for tool in tools:
                if tool is None:
                    continue
                registry.register(tool)
                count += 1
            return count
        if hasattr(module, "run"):
            # run(**kwargs) 模式
            async def _run(
                _module: Any = module, **kwargs: Any
            ) -> str:
                """执行技能

                参数:
                    _module: 绑定的技能模块
                    **kwargs: 参数

                返回:
                    str: 执行结果
                """
                result = await _module.run(**kwargs)
                return (
                    result
                    if isinstance(result, str)
                    else str(result)
                )

            registry.register(
                AgentTool(
                    name=spec.name,
                    description=spec.description,
                    parameters=spec.parameters,
                    func=_run,
                )
            )
            return 1
        return 0

    def _register_isolated_skill(
        self, spec: SkillSpec, registry: ToolRegistry
    ) -> int:
        """注册子进程隔离执行的技能

        为非可信技能创建隔离执行handler，调用时在子进程中运行。

        参数:
            spec: 技能规格
            registry: 工具注册表

        返回:
            int: 注册的工具数
        """
        if spec.entrypoint is None:
            return 0
        entrypoint = spec.entrypoint
        timeout = int(spec.isolation.get("timeout", 30))
        inherit_env = bool(
            spec.isolation.get("inherit_env", False)
        )

        async def _isolated_run(**kwargs: Any) -> str:
            """在子进程中隔离执行技能

            参数:
                **kwargs: 技能参数

            返回:
                str: 执行结果
            """
            return await skill_isolation_runner.run_in_subprocess(
                script_path=entrypoint,
                function="run",
                kwargs=kwargs,
                timeout=timeout,
                inherit_env=inherit_env,
            )

        registry.register(
            AgentTool(
                name=spec.name,
                description=f"[隔离] {spec.description}",
                parameters=spec.parameters,
                func=_isolated_run,
            )
        )
        logger.info(
            f"隔离技能 {spec.name} 已注册",
            command="AI",
        )
        return 1

    async def register_mcp_tools(
        self, registry: ToolRegistry = tool_registry
    ) -> int:
        """注册MCP远程工具

        从配置加载MCP服务器定义，发现并注册远程工具。
        需在异步上下文中调用（MCP注册涉及子进程通信）。

        参数:
            registry: 工具注册表

        返回:
            int: 注册的工具数
        """
        if not get_config("MCP", {}).get("enabled", False):
            return 0
        config_json = str(get_config("MCP", {}).get("servers", ""))
        if not config_json.strip():
            return 0
        count = mcp_bridge.load_config(config_json)
        if count == 0:
            return 0
        return await mcp_bridge.register_tools(registry)

    def _extract_frontmatter(
        self, text: str
    ) -> tuple[dict[str, Any], str]:
        """从SKILL.md提取YAML frontmatter

        参数:
            text: SKILL.md内容

        返回:
            tuple[dict, str]: (frontmatter字典, 正文)
        """
        normalized = text.replace("\r\n", "\n")
        if not normalized.startswith("---\n"):
            return {}, normalized

        match = re.match(
            r"^---\n([\s\S]*?)\n---\n?([\s\S]*)$", normalized
        )
        if not match:
            return {}, normalized
        try:
            data = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            data = {}
        return (
            data if isinstance(data, dict) else {},
            match.group(2),
        )

    def _resolve_entrypoint(
        self,
        skill_dir: Path,
        frontmatter: dict[str, Any],
    ) -> Path | None:
        """解析入口文件路径

        优先级：frontmatter.entrypoint → frontmatter.script →
        scripts/main.py → scripts/run.py → scripts/skill.py → scripts/首个.py

        参数:
            skill_dir: 技能目录
            frontmatter: frontmatter字典

        返回:
            Path | None: 入口文件路径
        """
        scripts_dir = skill_dir / "scripts"

        entry = str(
            frontmatter.get("entrypoint")
            or frontmatter.get("script")
            or ""
        ).strip()
        if entry:
            candidate = skill_dir / entry
            if candidate.exists():
                return candidate
            candidate = scripts_dir / entry
            if candidate.exists():
                return candidate

        for name in _ENTRYPOINT_NAMES:
            candidate = scripts_dir / name
            if candidate.exists():
                return candidate

        if scripts_dir.exists():
            py_files = sorted(scripts_dir.glob("*.py"))
            if py_files:
                return py_files[0]

        return None

    def _load_skill_module(
        self,
        script_path: Path,
        spec: SkillSpec | None = None,
    ) -> Any:
        """加载技能模块

        参考参考插件 module_loader.py 设计：
        构造合成包让相对导入（from . import impl）可用，
        注入sys.path让绝对导入可用。

        参数:
            script_path: 脚本路径
            spec: 技能规格（用于日志）

        返回:
            Any: 模块对象

        异常:
            ImportError: 加载失败
        """
        # scripts/main.py → scripts/ → skill_dir/
        scripts_dir = script_path.parent
        skill_dir = scripts_dir.parent

        # 构造合成包让相对导入可用
        package_name = f"_skillpack_{skill_dir.name}"
        if package_name not in sys.modules:
            pkg = ModuleType(package_name)
            pkg.__path__ = [str(scripts_dir)]
            sys.modules[package_name] = pkg

        # 注入sys.path让绝对导入可用
        added_paths: list[str] = []
        for p in [
            str(scripts_dir),
            str(skill_dir),
            str(self._base_dir),
        ]:
            if p not in sys.path:
                sys.path.insert(0, p)
                added_paths.append(p)

        module_name = f"{package_name}.{script_path.stem}"
        spec_obj = importlib.util.spec_from_file_location(
            module_name, script_path
        )
        if spec_obj is None or spec_obj.loader is None:
            raise ImportError(f"无法加载技能模块: {script_path}")
        module = importlib.util.module_from_spec(spec_obj)
        module.__package__ = package_name
        sys.modules[module_name] = module
        try:
            spec_obj.loader.exec_module(module)
        finally:
            # 还原sys.path，防止污染
            for p in added_paths:
                if p in sys.path:
                    sys.path.remove(p)
        return module


skill_loader = SkillpackLoader()
"""技能包加载器单例"""
