"""初始化管理器"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any, NamedTuple

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from liuying.configs.path_config import DATA_PATH
from liuying.configs.utils.models import BaseBlock, PluginCdBlock, PluginCountBlock
from liuying.models.plugin_info import PluginInfo
from liuying.models.plugin_limit import PluginLimit
from liuying.utils.enum import BlockType, LimitCheckType, PluginLimitType
from liuying.utils.log import logger

_yaml = YAML(pure=True)
_yaml.indent = 2
_yaml.allow_unicode = True

CD_TEST = """需要cd的功能
自定义的功能需要cd也可以在此配置
key：模块名称
cd：cd 时长（秒）
status：此限制的开关状态
check_type：'PRIVATE'/'GROUP'/'ALL'，限制私聊/群聊/全部
watch_type：监听对象，以user_id或group_id作为键来限制，'USER'：用户id，'GROUP'：群id
                                 示例：'USER':用户N秒内触发1次，'GROUP':群N秒内触发1次
result：回复的话,可以添加[at],[uname],[nickname]来对应艾特，用户群名称，昵称系统昵称
result 为 "" 或 None 时则不回复
result示例："[uname]你冲的太快了，[nickname]先生，请稍后再冲[at]"
result回复："老色批你冲的太快了，欧尼酱先生，请稍后再冲@老色批"
     用户昵称↑     昵称系统的昵称↑          艾特用户↑"""

BLOCK_TEST = """用户调用阻塞
即 当用户调用此功能还未结束时
用发送消息阻止用户重复调用此命令直到该命令结束
key：模块名称
status：此限制的开关状态
check_type：'PRIVATE'/'GROUP'/'ALL'，限制私聊/群聊/全部
watch_type：监听对象，以user_id或group_id作为键来限制，'USER'：用户id，'GROUP'：群id
                                    示例：'USER'：阻塞用户，'group'：阻塞群聊
result：回复的话，可以添加[at]，[uname]，[nickname]来对应艾特，用户群名称，昵称系统昵称
result 为 "" 或 None 时则不回复
result示例："[uname]你冲的太快了，[nickname]先生，请稍后再冲[at]"
result回复："老色批你冲的太快了，欧尼酱先生，请稍后再冲@老色批"
     用户昵称↑     昵称系统的昵称↑          艾特用户↑"""

COUNT_TEST = """命令每日次数限制
即 用户/群聊 每日可调用命令的次数 [数据内存存储，重启将会重置]
每日调用直到 00:00 刷新
key：模块名称
max_count: 每日调用上限
status：此限制的开关状态
watch_type：监听对象，以user_id或group_id作为键来限制，'USER'：用户id，'GROUP'：群id
                                     示例：'USER'：用户上限，'group'：群聊上限
result：回复的话，可以添加[at]，[uname]，[nickname]来对应艾特，用户群名称，昵称系统昵称
result 为 "" 或 None 时则不回复
result示例："[uname]你冲的太快了，[nickname]先生，请稍后再冲[at]"
result回复："老色批你冲的太快了，欧尼酱先生，请稍后再冲@老色批"
     用户昵称↑     昵称系统的昵称↑          艾特用户↑"""


class LimitTypeConfig(NamedTuple):
    """限制类型配置项"""

    type_name: str
    """YAML 文件中的类型键名"""
    comment: str
    """YAML 文件头部注释"""
    data_attr: str
    """Manager 实例上对应数据字典的属性名"""
    model_class: type[BaseBlock | PluginCdBlock | PluginCountBlock]
    """该类型对应的 Pydantic 模型类"""


_LIMIT_TYPE_CONFIG: Mapping[PluginLimitType, LimitTypeConfig] = {
    PluginLimitType.CD: LimitTypeConfig(
        "PluginCdLimit", CD_TEST, "cd_data", PluginCdBlock
    ),
    PluginLimitType.BLOCK: LimitTypeConfig(
        "PluginBlockLimit", BLOCK_TEST, "block_data", BaseBlock
    ),
    PluginLimitType.COUNT: LimitTypeConfig(
        "PluginCountLimit", COUNT_TEST, "count_data", PluginCountBlock
    ),
}

_ALL_LIMIT_TYPES: tuple[PluginLimitType, ...] = (
    PluginLimitType.CD,
    PluginLimitType.BLOCK,
    PluginLimitType.COUNT,
)


def _convert_check_type_to_block(check_type: LimitCheckType) -> BlockType:
    """将限制检查类型转换为阻塞类型

    参数:
        check_type: 限制检查类型

    返回:
        阻塞类型
    """
    match check_type:
        case LimitCheckType.GROUP:
            return BlockType.GROUP
        case LimitCheckType.PRIVATE:
            return BlockType.PRIVATE
        case LimitCheckType.ALL:
            return BlockType.ALL


def _convert_block_to_check_type(check_type: BlockType | None) -> LimitCheckType:
    """将阻塞类型转换为限制检查类型

    参数:
        check_type: 阻塞类型

    返回:
        限制检查类型
    """
    match check_type:
        case BlockType.GROUP:
            return LimitCheckType.GROUP
        case BlockType.PRIVATE:
            return LimitCheckType.PRIVATE
        case BlockType.ALL | None:
            return LimitCheckType.ALL


class Manager:
    """插件命令限制管理器"""

    def __init__(self) -> None:
        """初始化管理器，配置各限制类型对应的文件路径与数据容器"""
        self.cd_file = DATA_PATH / "configs" / "plugins2cd.yaml"
        self.block_file = DATA_PATH / "configs" / "plugins2block.yaml"
        self.count_file = DATA_PATH / "configs" / "plugins2count.yaml"
        self.cd_data: dict[str, PluginCdBlock] = {}
        self.block_data: dict[str, BaseBlock] = {}
        self.count_data: dict[str, PluginCountBlock] = {}

    def add(
        self,
        module: str,
        data: BaseBlock | PluginCdBlock | PluginCountBlock | PluginLimit,
    ) -> None:
        """添加限制

        参数:
            module: 模块名称
            data: 限制数据
        """
        if isinstance(data, PluginLimit):
            data = self._convert_plugin_limit(data)

        match data:
            case PluginCdBlock():
                self.cd_data[module] = data
            case PluginCountBlock():
                self.count_data[module] = data
            case BaseBlock():
                self.block_data[module] = data

    def _convert_plugin_limit(
        self, data: PluginLimit
    ) -> BaseBlock | PluginCdBlock | PluginCountBlock:
        """将 PluginLimit 转换为对应的限制类型

        参数:
            data: PluginLimit 实例

        返回:
            转换后的限制实例
        """
        check_type = _convert_check_type_to_block(data.check_type)
        base_fields = {
            "status": data.status,
            "check_type": check_type,
            "watch_type": data.watch_type,
            "result": data.result,
        }

        match data.limit_type:
            case PluginLimitType.CD:
                return PluginCdBlock(**base_fields, cd=data.cd or 5)
            case PluginLimitType.COUNT:
                return PluginCountBlock(
                    status=data.status,
                    watch_type=data.watch_type,
                    result=data.result,
                    max_count=data.max_count or 0,
                )
            case PluginLimitType.BLOCK:
                return BaseBlock(**base_fields)

    def exists(self, module: str, limit_type: PluginLimitType) -> bool:
        """检查限制是否存在

        参数:
            module: 模块名称
            limit_type: 限制类型

        返回:
            是否存在
        """
        data = self._get_file_data(limit_type)
        return module in data

    def init(self) -> None:
        """初始化管理器，确保文件存在并加载所有数据"""
        for limit_type in _ALL_LIMIT_TYPES:
            file_path = self._get_file_path(limit_type)
            if not file_path.exists():
                self._save_limit_file(limit_type)

        self._load_all_files()

    def _get_file_path(self, limit_type: PluginLimitType) -> Path:
        """获取限制类型对应的文件路径

        参数:
            limit_type: 限制类型

        返回:
            文件路径
        """
        match limit_type:
            case PluginLimitType.CD:
                return self.cd_file
            case PluginLimitType.BLOCK:
                return self.block_file
            case PluginLimitType.COUNT:
                return self.count_file

    def _load_all_files(self) -> None:
        """加载所有限制文件"""
        for limit_type in _ALL_LIMIT_TYPES:
            self._load_limit_file(limit_type)

    def _load_limit_file(self, limit_type: PluginLimitType) -> None:
        """加载指定类型的限制文件

        参数:
            limit_type: 限制类型
        """
        file_path = self._get_file_path(limit_type)
        config = _LIMIT_TYPE_CONFIG[limit_type]

        data_dict: dict[str, Any] = {}
        if file_path.exists():
            with file_path.open(encoding="utf8") as f:
                temp = _yaml.load(f) or {}
                if config.type_name in temp:
                    for k, v in temp[config.type_name].items():
                        key = k.split(".")[-1] if "." in k else k
                        data_dict[key] = config.model_class.model_validate(v)

        setattr(self, config.data_attr, data_dict)

    def save_file(self) -> None:
        """保存所有限制文件"""
        for limit_type in _ALL_LIMIT_TYPES:
            self._save_limit_file(limit_type)

    def _save_limit_file(self, limit_type: PluginLimitType) -> None:
        """保存指定类型的限制文件

        参数:
            limit_type: 限制类型
        """
        config = _LIMIT_TYPE_CONFIG[limit_type]
        data: dict = getattr(self, config.data_attr)
        temp_data = self._prepare_save_data(data, limit_type)
        file_path = self._get_file_path(limit_type)

        commented_data = CommentedMap()
        commented_data[config.type_name] = temp_data
        commented_data.yaml_set_comment_before_after_key(
            after=config.comment, key=config.type_name
        )

        with file_path.open("w", encoding="utf8") as f:
            _yaml.dump(commented_data, f)

    def _prepare_save_data(
        self, data: dict, limit_type: PluginLimitType
    ) -> dict[str, Any]:
        """准备保存的数据

        参数:
            data: 原始数据
            limit_type: 限制类型

        返回:
            处理后的数据
        """
        if not data:
            return self._create_default_data(limit_type)

        temp_data: dict[str, Any] = {}
        for k, v in data.items():
            item = v.model_dump(mode="json")
            if limit_type == PluginLimitType.COUNT:
                item.pop("check_type", None)
            temp_data[k] = item

        return temp_data

    @staticmethod
    def _create_default_data(limit_type: PluginLimitType) -> dict[str, Any]:
        """创建默认数据

        参数:
            limit_type: 限制类型

        返回:
            默认数据字典
        """
        default_data: dict[str, Any] = {
            "test": {
                "status": False,
                "check_type": "ALL",
                "limit_type": "USER",
                "result": "你冲的太快了，请稍后再冲",
            }
        }

        match limit_type:
            case PluginLimitType.CD:
                default_data["test"]["cd"] = 5
            case PluginLimitType.COUNT:
                default_data["test"]["max_count"] = 5
                default_data["test"].pop("check_type")
            case PluginLimitType.BLOCK:
                pass

        return default_data

    def _replace_data(
        self,
        db_data: PluginLimit | None,
        limit: BaseBlock | PluginCdBlock | PluginCountBlock,
    ) -> PluginLimit:
        """用文件数据替换数据库记录的通用字段

        参数:
            db_data: 数据库数据
            limit: 限制数据

        返回:
            更新后的 PluginLimit
        """
        if not db_data:
            db_data = PluginLimit()

        db_data.status = limit.status
        db_data.check_type = _convert_block_to_check_type(limit.check_type)
        db_data.watch_type = limit.watch_type
        db_data.result = limit.result or ""

        return db_data

    def _set_data(
        self,
        k: str,
        db_data: PluginLimit | None,
        limit: BaseBlock | PluginCdBlock | PluginCountBlock,
        limit_type: PluginLimitType,
        module2plugin: dict[str, PluginInfo],
    ) -> tuple[PluginLimit, bool]:
        """设置数据，返回创建或更新后的 PluginLimit

        参数:
            k: 模块名
            db_data: 数据库数据
            limit: 文件数据
            limit_type: 限制类型
            module2plugin: 模块:插件信息

        返回:
            tuple[PluginLimit, bool]: PluginLimit，是否创建
        """
        if not db_data:
            check_type = _convert_block_to_check_type(limit.check_type)
            return (
                PluginLimit(
                    module=k,
                    module_path=module2plugin[k].module_path,
                    limit_type=limit_type,
                    plugin=module2plugin[k],
                    cd=limit.cd if isinstance(limit, PluginCdBlock) else None,
                    max_count=(
                        limit.max_count
                        if isinstance(limit, PluginCountBlock)
                        else None
                    ),
                    status=limit.status,
                    check_type=check_type,
                    watch_type=limit.watch_type,
                    result=limit.result,
                ),
                True,
            )

        db_data = self._replace_data(db_data, limit)

        match limit:
            case PluginCdBlock():
                db_data.cd = limit.cd
            case PluginCountBlock():
                db_data.max_count = limit.max_count

        return db_data, False

    def _get_file_data(
        self, limit_type: PluginLimitType
    ) -> dict[str, BaseBlock | PluginCdBlock | PluginCountBlock]:
        """获取文件数据

        参数:
            limit_type: 限制类型

        返回:
            文件数据字典
        """
        match limit_type:
            case PluginLimitType.CD:
                return self.cd_data
            case PluginLimitType.COUNT:
                return self.count_data
            case PluginLimitType.BLOCK:
                return self.block_data

    def _set_db_limits(
        self,
        db_limits: list[PluginLimit],
        module2plugin: dict[str, PluginInfo],
        limit_type: PluginLimitType,
    ) -> tuple[list[PluginLimit], list[PluginLimit], list[int]]:
        """更新限制数据

        参数:
            db_limits: 数据库limits
            module2plugin: 模块:插件信息
            limit_type: 限制类型

        返回:
            tuple[list[PluginLimit], list[PluginLimit], list[int]]:
            创建列表，更新列表，删除列表
        """
        update_list: list[PluginLimit] = []
        create_list: list[PluginLimit] = []
        delete_list: list[int] = []

        db_type_limits = [
            limit for limit in db_limits if limit.limit_type == limit_type
        ]

        if data := self._get_file_data(limit_type):
            db_type_limit_modules = [
                (limit.module, limit.id) for limit in db_type_limits
            ]
            delete_list.extend(
                id_ for module, id_ in db_type_limit_modules if module not in data
            )

            for k, v in data.items():
                if not module2plugin.get(k):
                    if k != "test":
                        logger.warning(
                            f"插件模块 {k} 未加载，已过滤当前 {v._type} 限制..."
                        )
                    continue

                db_limit_list = [limit for limit in db_type_limits if limit.module == k]
                db_limit, is_create = self._set_data(
                    k,
                    db_limit_list[0] if db_limit_list else None,
                    v,
                    limit_type,
                    module2plugin,
                )

                if is_create:
                    create_list.append(db_limit)
                else:
                    update_list.append(db_limit)
        else:
            delete_list = [limit.id for limit in db_type_limits]

        return create_list, update_list, delete_list

    async def _set_all_limit(
        self,
    ) -> tuple[list[PluginLimit], list[PluginLimit], list[int]]:
        """获取所有插件限制数据

        返回:
            tuple[list[PluginLimit], list[PluginLimit], list[int]]:
            创建列表，更新列表，删除列表
        """
        db_limits = await PluginLimit.filter().all()

        modules = set(
            list(self.cd_data.keys())
            + list(self.block_data.keys())
            + list(self.count_data.keys())
        )

        plugins = await PluginInfo.filter(PluginInfo.module.in_(modules)).all()
        module2plugin = {p.module: p for p in plugins}

        all_create: list[PluginLimit] = []
        all_update: list[PluginLimit] = []
        all_delete: list[int] = []

        for limit_type in _ALL_LIMIT_TYPES:
            create, update, delete = self._set_db_limits(
                db_limits, module2plugin, limit_type
            )
            all_create.extend(create)
            all_update.extend(update)
            all_delete.extend(delete)

        return all_create, all_update, all_delete

    async def load_to_db(self) -> None:
        """读取配置文件并加载到数据库"""
        create_list, update_list, delete_list = await self._set_all_limit()

        for limit in create_list + update_list:
            await limit.save()

        for limit_id in delete_list:
            if limit := await PluginLimit.safe_get_or_none(id=limit_id):
                await limit.delete()

        cnt = len(await PluginLimit.filter(status=True).all())
        logger.info(f"已经加载 {cnt} 个插件限制.")


manager = Manager()
