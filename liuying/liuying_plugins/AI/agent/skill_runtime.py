"""技能包运行时

标准skillpack结构加载与执行：
- skill.yaml 元数据
- scripts/main.py 入口
- 三种入口模式：register / build_tools / run
"""

from dataclasses import dataclass, field
import importlib.util
from pathlib import Path
import re
import sys
from typing import Any

import yaml

from liuying.utils.log import logger

from .skillpacks import BuiltinSkillpackRegistrar
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
    """

    name: str
    description: str = ""
    category: str = "general"
    entrypoint: Path | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


def _extract_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """从SKILL.md提取YAML frontmatter

    参数:
        text: SKILL.md内容

    返回:
        tuple[dict, str]: (frontmatter字典, 正文)
    """
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return {}, normalized

    match = re.match(r"^---\n([\s\S]*?)\n---\n?([\s\S]*)$", normalized)
    if not match:
        return {}, normalized
    try:
        data = yaml.safe_load(match.group(1)) or {}
    except Exception:
        data = {}
    return (
        data if isinstance(data, dict) else {},
        match.group(2),
    )


def _resolve_entrypoint(
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
    script_path: Path,
    sys_paths: list[str] | None = None,
) -> Any:
    """加载技能模块

    参数:
        script_path: 脚本路径
        sys_paths: 额外sys.path

    返回:
        Any: 模块对象

    异常:
        ImportError: 加载失败
    """
    for p in sys_paths or []:
        if p not in sys.path:
            sys.path.insert(0, p)

    module_name = f"_skill_{script_path.stem}_{hash(str(script_path))}"
    spec = importlib.util.spec_from_file_location(
        module_name, script_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载技能模块: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class SkillpackLoader:
    """技能包加载器

    扫描skillpacks目录，加载所有技能并注册到工具注册表。
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
                frontmatter, _ = _extract_frontmatter(text)
            except Exception:
                pass

        name = str(
            frontmatter.get("name") or skill_dir.name
        )
        entrypoint = _resolve_entrypoint(skill_dir, frontmatter)
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
        )

    def register_all(
        self, registry: ToolRegistry = tool_registry
    ) -> int:
        """注册所有技能到工具注册表

        参数:
            registry: 工具注册表

        返回:
            int: 注册成功的工具数
        """
        specs = self.discover_skills()
        registered = 0

        for spec in specs:
            if not spec.enabled or spec.entrypoint is None:
                continue
            try:
                module = _load_skill_module(spec.entrypoint)

                if hasattr(module, "register"):
                    module.register(registry)
                    registered += 1
                elif hasattr(module, "build_tools"):
                    tools = module.build_tools()
                    for tool in tools:
                        registry.register(tool)
                    registered += len(tools)
                elif hasattr(module, "run"):

                    async def _run(
                        _module: Any = module, **kwargs: Any
                    ) -> str:
                        """执行技能

                        参数:
                            _module: 绑定的技能模块（默认参数避免闭包捕获循环变量）
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
                    registered += 1
            except Exception as e:
                logger.warning(
                    f"注册技能 {spec.name} 失败: {e}",
                    command="AI",
                    e=e,
                )

        # 注册内置单文件技能包（news/weather/datetime/wiki/game_info）
        try:
            registered += (
                BuiltinSkillpackRegistrar.register_builtin_skillpacks(
                    registry
                )
            )
        except Exception as e:
            logger.warning(
                f"内置技能包注册失败: {e}",
                command="AI",
                e=e,
            )

        logger.info(
            f"技能包注册完成，共{registered}个工具",
            command="AI",
        )
        return registered


skill_loader = SkillpackLoader()
"""技能包加载器单例"""
