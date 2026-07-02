from collections.abc import Callable
import copy
from pathlib import Path
from typing import Any, TypeVar

import cattrs
from pydantic import BaseModel, Field
from ruamel.yaml import YAML
from ruamel.yaml.scanner import ScannerError

from liuying.configs.path_config import DATA_PATH
from liuying.utils.log import logger
from liuying.utils.pydantic_compat import (
    _dump_pydantic_obj,
    _is_pydantic_type,
    model_dump,
    parse_as,
)

for _bt in (int, float, str, bool, list, dict, tuple, set, type(None)):
    cattrs.register_structure_hook(_bt, lambda v, _: v)

from .models import (
    AICallableParam,
    AICallableProperties,
    AICallableTag,
    BaseBlock,
    Command,
    ConfigModel,
    Example,
    PluginCdBlock,
    PluginCountBlock,
    PluginExtraData,
    PluginSetting,
    RegisterConfig,
    Task,
)

_yaml = YAML(pure=True)
_yaml.indent = 2
_yaml.allow_unicode = True

T = TypeVar("T")


class NoSuchConfig(Exception):
    pass


def _try_type_convert(
    value: Any,
    cfg_type: type | None,
    *,
    module: str,
    key: str,
    build_model: bool = True,
) -> Any:
    """尝试将配置值通过类型转换为目标类型

    优先使用Pydantic原生方式解析，回退到cattrs结构化。

    参数:
        value: 待转换的值
        cfg_type: 目标类型
        module: 模块名（用于日志）
        key: 配置键名（用于日志）
        build_model: 是否构建模型实例

    返回:
        转换后的值，失败时返回原始值
    """
    if not cfg_type or not build_model:
        return value

    if isinstance(cfg_type, type) and isinstance(value, cfg_type):
        return value

    if _is_pydantic_type(cfg_type):
        try:
            return parse_as(cfg_type, value)
        except Exception as e:
            logger.warning(
                f"pydantic类型转换失败 MODULE: "
                f"[<u><y>{module}</y></u>] | "
                f"KEY: [<u><y>{key}</y></u>].",
                e=e,
            )
    else:
        try:
            return cattrs.structure(value, cfg_type)
        except Exception as e:
            logger.warning(
                f"cattrs类型转换失败 MODULE: "
                f"[<u><y>{module}</y></u>] | "
                f"KEY: [<u><y>{key}</y></u>].",
                e=e,
            )

    return value


class ConfigGroup(BaseModel):
    """配置组"""

    module: str
    """模块名"""
    name: str | None = None
    """插件名"""
    configs: dict[str, ConfigModel] = Field(default_factory=dict)
    """配置项列表"""

    def get(self, c: str, default: Any = None, *, build_model: bool = True) -> Any:
        """获取配置项的值，支持自动类型转换

        参数:
            c: 配置键名
            default: 默认值
            build_model: 是否自动构建模型实例

        返回:
            配置值，未找到时返回默认值
        """
        key = c.upper()
        cfg = self.configs.get(key)
        if cfg is None:
            return default

        value = cfg.value if cfg.value is not None else cfg.default_value
        if value is None:
            return default

        if cfg.arg_parser:
            try:
                return cfg.arg_parser(value)
            except Exception as e:
                logger.debug(
                    f"配置项类型转换 MODULE: [<u><y>{self.module}</y></u>] | "
                    f"KEY: [<u><y>{key}</y></u>] 的自定义解析器失败，"
                    f"将使用原始值",
                    e=e,
                )
                return value

        return _try_type_convert(
            value,
            cfg.type,
            module=self.module,
            key=key,
            build_model=build_model,
        )

    def to_dict(self, **kwargs):
        return model_dump(self, **kwargs)


class ConfigsManager:
    """插件配置与资源管理器"""

    def __init__(self, file: Path):
        self._data: dict[str, ConfigGroup] = {}
        self._simple_data: dict = {}
        self._simple_file = DATA_PATH / "config.yaml"
        self.add_module: list[str] = []
        if file:
            file.parent.mkdir(exist_ok=True, parents=True)
            self.file = file
            self.load_data()
        if self._simple_file.exists():
            try:
                with self._simple_file.open(encoding="utf8") as f:
                    self._simple_data = _yaml.load(f) or {}
            except ScannerError as e:
                raise ScannerError(
                    f"{e}\n**********************************************\n"
                    f"****** 可能为config.yaml配置文件填写不规范 ******\n"
                    f"**********************************************"
                ) from e

    def set_name(self, module: str, name: str):
        """设置插件配置中文名称

        参数:
            module: 模块名
            name: 中文名称

        异常:
            ValueError: module不能为空
        """
        if not module:
            raise ValueError("set_name: module不能为空")
        if data := self._data.get(module):
            data.name = name

    def _merge_dicts(self, new_data: dict, original_data: dict) -> dict:
        """合并两个字典，只新增key不修改原有key的值

        递归处理嵌套字典，确保所有层级的key保持一致。

        参数:
            new_data: 新数据字典
            original_data: 原数据字典

        返回:
            合并后的字典
        """
        result = dict(original_data)
        for key, value in new_data.items():
            if key not in original_data:
                result[key] = value
            elif isinstance(value, dict) and isinstance(original_data[key], dict):
                result[key] = self._merge_dicts(value, original_data[key])
        return result

    def _normalize_config_data(self, value: Any, original_value: Any = None) -> Any:
        """标准化配置数据，处理BaseModel和字典的合并

        参数:
            value: 要标准化的值
            original_value: 原始值，用于合并字典

        返回:
            标准化后的值
        """
        processed_value = _dump_pydantic_obj(value)
        if isinstance(processed_value, dict) and original_value is not None:
            processed_original = _dump_pydantic_obj(original_value)
            if isinstance(processed_original, dict):
                return self._merge_dicts(processed_value, processed_original)
        return processed_value

    def add_plugin_config(
        self,
        module: str,
        key: str,
        value: Any,
        *,
        help: str | None = None,
        default_value: Any = None,
        type: type | None = None,
        arg_parser: Callable | None = None,
        _override: bool = False,
    ):
        """为插件添加一个配置，不会被覆盖，只有第一个生效

        参数:
            module: 模块
            key: 键
            value: 值
            help: 配置注解
            default_value: 默认值
            type: 值类型
            arg_parser: 值解析器，一般与webui配合使用
            _override: 强制覆盖值

        异常:
            ValueError: module和key不能为空
        """
        key = key.upper()
        if not module or not key:
            raise ValueError("add_plugin_config: module和key不能为空")

        existing_value = None
        if module in self._data and (config := self._data[module].configs.get(key)):
            existing_value = config.value

        processed_value = self._normalize_config_data(value, existing_value)
        processed_default_value = self._normalize_config_data(default_value)
        self.add_module.append(f"{module}:{key}".lower())

        if module in self._data and (config := self._data[module].configs.get(key)):
            config.help = help
            config.arg_parser = arg_parser
            config.type = type
            if _override:
                config.value = processed_value
                config.default_value = processed_default_value
        else:
            if module not in self._data:
                self._data[module] = ConfigGroup(module=module)
            self._data[module].configs[key] = ConfigModel(
                value=processed_value,
                help=help,
                default_value=processed_default_value,
                type=type,
                arg_parser=arg_parser,
            )

    def set_config(
        self,
        module: str,
        key: str,
        value: Any,
        auto_save: bool = False,
    ):
        """设置配置值

        参数:
            module: 模块名
            key: 配置名称
            value: 值
            auto_save: 自动保存
        """
        key = key.upper()
        if module not in self._data:
            return
        if module not in self._simple_data:
            self._simple_data[module] = {}
        if self._data[module].configs.get(key):
            self._data[module].configs[key].value = value
        else:
            self.add_plugin_config(module, key, value)
        self._simple_data[module][key] = value
        if auto_save:
            self.save(save_simple_data=True)

    def get_config(
        self,
        module: str,
        key: str,
        default: Any = None,
        *,
        build_model: bool = True,
    ) -> Any:
        """获取指定配置值，自动构建Pydantic模型或其它类型实例

        参数:
            module: 模块名
            key: 配置键名
            default: 默认值
            build_model: 是否构建模型实例

        返回:
            配置值，未找到时返回默认值
        """
        key = key.upper()
        config_group = self._data.get(module)
        if not config_group:
            return default

        config = config_group.configs.get(key)
        if not config:
            return default

        value = config.value if config.value is not None else config.default_value
        if value is None:
            return default

        if config.arg_parser:
            try:
                return config.arg_parser(value)
            except Exception as e:
                logger.debug(
                    f"配置项类型转换 MODULE: [<u><y>{module}</y></u>]"
                    f" | KEY: [<u><y>{key}</y></u>] 将使用原始值",
                    e=e,
                )

        return _try_type_convert(
            value,
            config.type,
            module=module,
            key=key,
            build_model=build_model,
        )

    def get(self, key: str) -> ConfigGroup:
        """获取插件配置数据

        参数:
            key: 键，一般为模块名

        返回:
            ConfigGroup实例
        """
        return self._data.get(key) or ConfigGroup(module="")

    def save(self, path: str | Path | None = None, save_simple_data: bool = False):
        """保存数据

        参数:
            path: 路径
            save_simple_data: 同时保存至config.yaml
        """
        if save_simple_data:
            with self._simple_file.open("w", encoding="utf8") as f:
                _yaml.dump(self._simple_data, f)
        save_path = Path(path or self.file)
        save_data = {
            module: {
                config_key: model_dump(config_model, exclude={"type", "arg_parser"})
                for config_key, config_model in config_group.configs.items()
            }
            for module, config_group in self._data.items()
        }
        with save_path.open("w", encoding="utf8") as f:
            _yaml.dump(save_data, f)

    def reload(self):
        """重新加载配置文件"""
        if self._simple_file.exists():
            with self._simple_file.open(encoding="utf8") as f:
                self._simple_data = _yaml.load(f) or {}
        for module, simple_configs in self._simple_data.items():
            if not isinstance(simple_configs, dict):
                continue
            if module not in self._data:
                continue
            for k, v in simple_configs.items():
                upper_k = k.upper()
                if upper_k in self._data[module].configs:
                    self._data[module].configs[upper_k].value = v
        self.save()

    def load_data(self):
        """加载数据

        异常:
            ValueError: 配置文件为空
        """
        if not self.file.exists():
            return
        with self.file.open(encoding="utf8") as f:
            temp_data = _yaml.load(f)
        if not temp_data:
            self.file.unlink()
            raise ValueError(
                "配置文件为空！\n"
                "***********************************************************\n"
                "****** 配置文件 plugins2config.yaml 为空，已删除，请重启 ******\n"
                "***********************************************************"
            )
        count = 0
        for module, configs in temp_data.items():
            config_group = ConfigGroup(module=module)
            for config_name, config_data in configs.items():
                config_group.configs[config_name] = ConfigModel(**config_data)
                count += 1
            self._data[module] = config_group
        logger.info(
            f"加载配置完成，共加载 <u><y>{len(temp_data)}</y></u> 个配置组及对应"
            f" <u><y>{count}</y></u> 个配置项"
        )

    def get_data(self) -> dict[str, ConfigGroup]:
        return copy.deepcopy(self._data)

    def is_empty(self) -> bool:
        return not self._data

    def keys(self):
        return self._data.keys()

    def __str__(self):
        return str(self._data)

    def __setitem__(self, key, value):
        self._data[key] = value

    def __getitem__(self, key):
        return self._data[key]


__all__ = [
    "AICallableParam",
    "AICallableProperties",
    "AICallableTag",
    "BaseBlock",
    "Command",
    "ConfigGroup",
    "ConfigModel",
    "ConfigsManager",
    "Example",
    "NoSuchConfig",
    "PluginCdBlock",
    "PluginCountBlock",
    "PluginExtraData",
    "PluginSetting",
    "RegisterConfig",
    "Task",
]
