"""初始化配置"""

from pathlib import Path

import nonebot
from nonebot.plugin import Plugin
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from liuying.configs.config import Config
from liuying.configs.path_config import DATA_PATH
from liuying.configs.utils.models import RegisterConfig
from liuying.utils.log import logger
from liuying.utils.manager.priority_manager import PriorityLifecycle

_yaml = YAML(pure=True)
_yaml.allow_unicode = True
_yaml.indent = 2

SIMPLE_CONFIG_FILE = DATA_PATH / "config.yaml"

old_config_file = Path() / "liuying" / "configs" / "config.yaml"
if old_config_file.exists():
    old_config_file.rename(SIMPLE_CONFIG_FILE)


def _handle_config(plugin: Plugin, exists_module: list[str]) -> None:
    """处理配置项

    参数:
        plugin: Plugin 实例
        exists_module: 已存在的模块列表
    """
    if not (plugin.metadata and plugin.metadata.extra):
        return

    extra = plugin.metadata.extra
    if not (configs := extra.get("configs")):
        return

    for config in configs:
        if isinstance(config, dict):
            config = RegisterConfig(**config)

        module = config.module or plugin.name
        g_config = Config.get(module)
        g_config.name = plugin.metadata.name

        Config.add_plugin_config(
            module,
            config.key,
            config.value if hasattr(config, "value") else config.default_value,
            help=config.help,
            default_value=config.default_value,
            type=config.type,
            _override=False,
        )
        exists_module.append(f"{module}:{config.key}".lower())


def _load_yaml_data(file_path: Path) -> dict:
    """加载 YAML 数据

    参数:
        file_path: 文件路径

    返回:
        解析后的数据字典
    """
    if not file_path.exists():
        return {}

    try:
        with file_path.open(encoding="utf8") as f:
            return _yaml.load(f) or {}
    except Exception:
        return {}


def _generate_simple_config(exists_module: list[str]) -> None:
    """生成简易配置

    参数:
        exists_module: 已存在的模块列表

    异常:
        AttributeError: 配置文件填写不规范
    """
    _data = _load_yaml_data(SIMPLE_CONFIG_FILE)
    _tmp_data: dict = {}
    exists_module += Config.add_module

    for module in Config.keys():
        _tmp_data[module] = {}
        for k in Config[module].configs.keys():
            try:
                if _data.get(module) and k in _data[module]:
                    Config.set_config(module, k, _data[module][k])

                if f"{module}:{k}".lower() in exists_module:
                    _tmp_data[module][k] = Config.get_config(
                        module, k, build_model=False
                    )
            except AttributeError as e:
                raise AttributeError(f"{e}\n可能为config.yaml配置文件填写不规范") from e

        if not _tmp_data[module]:
            _tmp_data.pop(module)

    Config.save()
    _write_simple_config(_tmp_data)


def _write_simple_config(_tmp_data: dict) -> None:
    """写入简易配置文件

    参数:
        _tmp_data: 临时数据字典
    """
    temp_file = DATA_PATH / "temp_config.yaml"

    try:
        with temp_file.open("w", encoding="utf8") as wf:
            _yaml.dump(_tmp_data, wf)

        with temp_file.open(encoding="utf8") as rf:
            _data = _yaml.load(rf)

        for module in _data.keys():
            help_text = _build_module_help_text(module)
            _data.yaml_set_comment_before_after_key(after=help_text, key=module)

        with SIMPLE_CONFIG_FILE.open("w", encoding="utf8") as wf:
            _yaml.dump(_data, wf)

    except Exception as e:
        logger.error(f"生成简易配置文件失败: {e}")
    finally:
        if temp_file.exists():
            temp_file.unlink()


def _build_module_help_text(module: str) -> str:
    """构建模块帮助文本

    参数:
        module: 模块名称

    返回:
        帮助文本
    """
    plugin_name = Config.get(module).name or module
    help_text = plugin_name + "\n"

    for k in Config[module].configs.keys():
        help_text += f"{k}: {Config[module].configs[k].help}\n"

    return help_text[:-1]


def _update_plugins_config_file() -> None:
    """更新插件配置文件"""
    plugins2config_file = DATA_PATH / "configs" / "plugins2config.yaml"

    if Config.is_empty():
        return

    Config.save()

    if not plugins2config_file.exists():
        return

    try:
        with plugins2config_file.open(encoding="utf8") as f:
            _data: CommentedMap = _yaml.load(f)

        for module in _data.keys():
            if module in Config:
                plugin_name = Config.get(module).name
                _data.yaml_set_comment_before_after_key(
                    after=f"{plugin_name}",
                    key=module,
                )

        with plugins2config_file.open("w", encoding="utf8") as wf:
            _yaml.dump(_data, wf)

    except Exception as e:
        logger.error(f"更新plugins2config.yaml失败: {e}")


@PriorityLifecycle.on_startup(priority=0)
def _() -> None:
    """初始化插件数据配置"""
    exists_module: list[str] = []

    for plugin in nonebot.get_loaded_plugins():
        _handle_config(plugin, exists_module)

    _generate_simple_config(exists_module)
    _update_plugins_config_file()

    Config.reload()
    logger.info(f"加载配置完成，共加载 {len(Config.keys())} 个配置组及对应配置项")
