"""技能包加载器

统一技能目录 `skills/skillpacks/` 的标准化加载与注册。

标准技能包五件套结构::

    skillpacks/<name>/
        SKILL.md            # 人类可读说明，可含 YAML frontmatter 作为兜底元数据
        skill.yaml          # 机器可读元数据（权威来源）
        agents/openai.yaml  # 面向 Agent 的展示元数据
        references/         # 设计说明与映射文档
        scripts/main.py     # 入口：register / build_tools / run 三段式

入口三段式优先级为 ``register`` > ``build_tools`` > ``run``：

- ``register(runtime, registry)``：技能自行注册任意数量工具
- ``build_tools(runtime)``：返回 ``AgentTool`` 列表，由加载器统一注册
- ``run(**kwargs)``：单函数技能，由加载器按 skill.yaml 的 parameters 合成工具
"""

from dataclasses import dataclass, field
import importlib.util
import json
from pathlib import Path
import re
import sys
import threading
from types import ModuleType
from typing import Any

import yaml

from liuying.utils.log import logger

from ..agent.runtime.tool_catalog import (
    apply_tool_metadata_defaults,
)
from ..config import get_config
from ..tools import AgentTool, ToolRegistry, tool_registry
from ..tools.mcp import mcp_bridge
from .api import SkillRuntime

__all__ = [
    "SkillLoadReport",
    "SkillSpec",
    "SkillpackLoader",
    "skill_loader",
]


_SKILL_YAML_NAMES: tuple[str, ...] = ("skill.yaml", "skill.yml")
"""skill.yaml 文件名候选"""


_ENTRYPOINT_NAMES: tuple[str, ...] = (
    "main.py",
    "run.py",
    "skill.py",
)
"""入口文件候选名"""


_FRONTMATTER_RE = re.compile(
    r"^---\n([\s\S]*?)\n---\n?([\s\S]*)$"
)
"""SKILL.md frontmatter 匹配模式"""


_SYS_PATH_LOCK = threading.Lock()
"""sys.path 注入窗口串行化锁，防止并发加载时模块解析冲突"""


@dataclass(slots=True)
class SkillSpec:
    """技能规格

    Attributes:
        name: 技能名
        description: 描述
        entrypoint: 入口文件路径
        parameters: 参数JSON Schema
        enabled: 是否启用
        metadata: 附加元信息（skill.yaml 与 SKILL.md frontmatter 合并结果）
    """

    name: str
    description: str = ""
    entrypoint: Path | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SkillLoadReport:
    """技能加载报告

    Attributes:
        discovered: 发现的技能数
        loaded: 成功加载的技能数
        tools: 注册的工具数
        skipped: 被禁用或无入口而跳过的技能名
        failed: 加载失败的技能名到错误信息的映射
    """

    discovered: int = 0
    loaded: int = 0
    tools: int = 0
    skipped: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def _read_yaml(path: Path) -> dict[str, Any]:
    """读取YAML文件为字典

    参数:
        path: 文件路径

    返回:
        dict[str, Any]: 解析结果，失败或非字典时返回空字典
    """
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError) as e:
        logger.warning(
            f"技能元数据解析失败 {path.name}: {e}",
            command="AI",
            e=e,
        )
        return {}
    return data if isinstance(data, dict) else {}


class SkillpackLoader:
    """技能包加载器

    扫描 skillpacks 目录，加载所有技能并注册到工具注册表。
    通过 SkillRuntime 依赖注入让技能包访问主插件服务。
    单个技能加载失败不影响其余技能，失败信息汇总到加载报告。
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        """初始化技能包加载器

        参数:
            base_dir: skillpacks 根目录，默认取本模块同级目录
        """
        self._base_dir = (
            base_dir or Path(__file__).parent / "skillpacks"
        )
        self._skills: dict[str, SkillSpec] = {}
        self._report = SkillLoadReport()

    @property
    def base_dir(self) -> Path:
        """获取 skillpacks 根目录"""
        return self._base_dir

    @property
    def report(self) -> SkillLoadReport:
        """获取最近一次加载报告"""
        return self._report

    def list_specs(self) -> list[SkillSpec]:
        """列出已发现的技能规格

        返回:
            list[SkillSpec]: 按技能名排序的规格列表
        """
        return sorted(self._skills.values(), key=lambda s: s.name)

    def get_spec(self, name: str) -> SkillSpec | None:
        """按名称获取技能规格

        参数:
            name: 技能名

        返回:
            SkillSpec | None: 技能规格
        """
        return self._skills.get(name)

    def discover_skills(self) -> list[SkillSpec]:
        """扫描发现所有技能

        返回:
            list[SkillSpec]: 技能规格列表
        """
        if not self._base_dir.exists():
            logger.warning(
                f"技能目录不存在: {self._base_dir}",
                command="AI",
            )
            return []

        self._skills.clear()
        specs = [
            spec
            for item in sorted(self._base_dir.iterdir())
            if item.is_dir() and not item.name.startswith(("_", "."))
            if (spec := self._load_skill_spec(item)) is not None
        ]
        self._skills = {spec.name: spec for spec in specs}
        logger.info(f"发现{len(specs)}个技能包", command="AI")
        return specs

    def register_all(
        self,
        runtime: SkillRuntime,
        registry: ToolRegistry = tool_registry,
    ) -> int:
        """注册所有技能到工具注册表

        参数:
            runtime: 技能运行时（依赖注入载体）
            registry: 工具注册表

        返回:
            int: 注册成功的工具数
        """
        specs = self.discover_skills()
        report = SkillLoadReport(discovered=len(specs))

        for spec in specs:
            if not spec.enabled:
                report.skipped.append(spec.name)
                continue
            count = self._register_one(
                spec, registry, runtime, report
            )
            if count >= 0:
                report.loaded += 1
                report.tools += count

        apply_tool_metadata_defaults(registry)
        self._report = report

        logger.info(
            f"技能包注册完成: 工具{report.tools}个 "
            f"加载{report.loaded}/{report.discovered} "
            f"跳过{len(report.skipped)} 失败{len(report.failed)}",
            command="AI",
        )
        if report.failed:
            for name, err in report.failed.items():
                logger.warning(
                    f"技能 {name} 加载失败: {err}", command="AI"
                )
        return report.tools

    def _register_one(
        self,
        spec: SkillSpec,
        registry: ToolRegistry,
        runtime: SkillRuntime,
        report: SkillLoadReport,
    ) -> int:
        """注册单个技能并隔离其失败

        参数:
            spec: 技能规格
            registry: 工具注册表
            runtime: 技能运行时
            report: 加载报告，失败时写入 failed

        返回:
            int: 注册的工具数，失败返回 -1
        """
        # 技能包为可插拔外部代码，单个技能的导入或构建异常
        # 不应中断整体注册流程，故在此收敛为加载报告。
        try:
            module = self._load_skill_module(spec)
            return self._register_module(
                module, spec, registry, runtime
            )
        except Exception as e:
            report.failed[spec.name] = f"{type(e).__name__}: {e}"
            return -1

    def _load_skill_spec(
        self, skill_dir: Path
    ) -> SkillSpec | None:
        """加载单个技能规格

        元数据来源优先级：skill.yaml > SKILL.md frontmatter。
        两者按字段级合并，skill.yaml 缺失的字段由 frontmatter 兜底。

        参数:
            skill_dir: 技能目录

        返回:
            SkillSpec | None: 技能规格，无入口时返回 None
        """
        meta: dict[str, Any] = {}
        for yaml_name in _SKILL_YAML_NAMES:
            if data := _read_yaml(skill_dir / yaml_name):
                meta = data
                break

        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            front, _ = self._extract_frontmatter(
                skill_md.read_text(encoding="utf-8")
            )
            meta = front | meta

        name = str(meta.get("name") or skill_dir.name)
        entrypoint = self._resolve_entrypoint(skill_dir, meta)
        if entrypoint is None:
            logger.debug(
                f"技能 {name} 未找到入口文件，跳过", command="AI"
            )
            return None

        return SkillSpec(
            name=name,
            description=str(meta.get("description", "")),
            entrypoint=entrypoint,
            parameters=meta.get("parameters") or {},
            enabled=bool(meta.get("enabled", True)),
            metadata=meta,
        )

    def _register_module(
        self,
        module: Any,
        spec: SkillSpec,
        registry: ToolRegistry,
        runtime: SkillRuntime,
    ) -> int:
        """按三段式接口注册技能模块

        优先级：register > build_tools > run。

        参数:
            module: 技能模块
            spec: 技能规格
            registry: 工具注册表
            runtime: 技能运行时

        返回:
            int: 注册的工具数
        """
        if register := getattr(module, "register", None):
            before = len(registry.list_names())
            register(runtime, registry)
            return max(len(registry.list_names()) - before, 1)

        if build_tools := getattr(module, "build_tools", None):
            try:
                tools = build_tools(runtime)
            except TypeError:
                tools = build_tools()
            count = 0
            for tool in tools or ():
                if tool is None:
                    continue
                registry.register(tool)
                count += 1
            return count

        if getattr(module, "run", None) is None:
            return 0

        async def _run(_module: Any = module, **kwargs: Any) -> str:
            """执行单函数技能

            参数:
                _module: 绑定的技能模块
                **kwargs: 技能参数

            返回:
                str: 执行结果文本
            """
            result = await _module.run(**kwargs)
            return result if isinstance(result, str) else str(result)

        registry.register(
            AgentTool(
                name=spec.name,
                description=spec.description,
                parameters=spec.parameters,
                func=_run,
            )
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
        mcp_conf = get_config("MCP", {}) or {}
        if not mcp_conf.get("enabled", False):
            return 0
        servers = mcp_conf.get("servers", "")
        if isinstance(servers, str):
            config_json = servers
        elif isinstance(servers, (dict, list)):
            # dict/list 直接 str() 会产生 Python repr，
            # 下游 json.loads 必然失败，须用标准 JSON 序列化。
            config_json = json.dumps(servers, ensure_ascii=False)
        else:
            logger.warning(
                f"MCP servers 配置类型无效: "
                f"{type(servers).__name__}，跳过注册",
                command="AI",
            )
            return 0
        if not config_json.strip():
            return 0
        if mcp_bridge.load_config(config_json) == 0:
            return 0
        return await mcp_bridge.register_tools(registry)

    def _extract_frontmatter(
        self, text: str
    ) -> tuple[dict[str, Any], str]:
        """从SKILL.md提取YAML frontmatter

        参数:
            text: SKILL.md 内容

        返回:
            tuple[dict, str]: (frontmatter字典, 正文)
        """
        normalized = text.replace("\r\n", "\n")
        if not normalized.startswith("---\n"):
            return {}, normalized
        match = _FRONTMATTER_RE.match(normalized)
        if match is None:
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
        self, skill_dir: Path, meta: dict[str, Any]
    ) -> Path | None:
        """解析入口文件路径

        优先级：meta.entrypoint / meta.script → scripts/main.py →
        scripts/run.py → scripts/skill.py → scripts 下首个 .py。
        声明式入口必须位于技能目录内，越界路径直接拒绝加载。

        参数:
            skill_dir: 技能目录
            meta: 元数据字典

        返回:
            Path | None: 入口文件路径
        """
        scripts_dir = skill_dir / "scripts"
        entry = str(
            meta.get("entrypoint") or meta.get("script") or ""
        ).strip()
        if entry:
            root = skill_dir.resolve()
            for candidate in (skill_dir / entry, scripts_dir / entry):
                # 入口路径可由外部 skill.yaml 声明，必须锁定在
                # 技能目录内，防止 ../ 路径穿越加载任意文件。
                if not candidate.resolve().is_relative_to(root):
                    logger.warning(
                        f"技能入口路径越界，拒绝加载: {candidate}",
                        command="AI",
                    )
                    return None
                if candidate.exists():
                    return candidate

        for name in _ENTRYPOINT_NAMES:
            if (candidate := scripts_dir / name).exists():
                return candidate

        if scripts_dir.exists() and (
            py_files := sorted(scripts_dir.glob("*.py"))
        ):
            return py_files[0]
        return None

    def _load_skill_module(self, spec: SkillSpec) -> Any:
        """加载技能模块

        构造合成包让相对导入（from . import impl）可用，
        并临时注入 sys.path 让绝对导入可用，执行完毕后还原。
        注入窗口通过模块级锁串行化，防止并发加载时
        其他模块误解析到临时路径。

        参数:
            spec: 技能规格

        返回:
            Any: 模块对象

        异常:
            ImportError: 入口缺失或模块规格构建失败
        """
        script_path = spec.entrypoint
        if script_path is None:
            raise ImportError(f"技能 {spec.name} 缺少入口文件")

        scripts_dir = script_path.parent
        skill_dir = scripts_dir.parent

        package_name = f"_skillpack_{skill_dir.name}"
        module_name = f"{package_name}.{script_path.stem}"
        module_spec = importlib.util.spec_from_file_location(
            module_name, script_path
        )
        if module_spec is None or module_spec.loader is None:
            raise ImportError(f"无法加载技能模块: {script_path}")

        with _SYS_PATH_LOCK:
            if package_name not in sys.modules:
                pkg = ModuleType(package_name)
                pkg.__path__ = [str(scripts_dir)]
                sys.modules[package_name] = pkg

            added_paths = [
                p
                for p in (
                    str(scripts_dir),
                    str(skill_dir),
                    str(self._base_dir),
                )
                if p not in sys.path
            ]
            for p in added_paths:
                sys.path.insert(0, p)

            module = importlib.util.module_from_spec(module_spec)
            module.__package__ = package_name
            sys.modules[module_name] = module
            try:
                module_spec.loader.exec_module(module)
            except BaseException:
                # 半初始化模块残留在 sys.modules 会污染
                # 后续加载，务必清理后原样上抛。
                sys.modules.pop(module_name, None)
                raise
            finally:
                for p in added_paths:
                    if p in sys.path:
                        sys.path.remove(p)
            return module


skill_loader = SkillpackLoader()
"""技能包加载器单例"""
