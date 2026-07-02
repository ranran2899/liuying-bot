"""初始化管理器"""

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

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

LIMIT_TYPE_MAP = {
    PluginLimitType.CD: ("PluginCdLimit", CD_TEST, "cd_data"),
    PluginLimitType.BLOCK: ("PluginBlockLimit", BLOCK_TEST, "block_data"),
    PluginLimitType.COUNT: ("PluginCountLimit", COUNT_TEST, "count_data"),
}

LIMIT_MODEL_MAP = {
    PluginLimitType.CD: PluginCdBlock,
    PluginLimitType.BLOCK: BaseBlock,
    PluginLimitType.COUNT: PluginCountBlock,
}


class Manager:
    """插件命令限制管理器"""

    def __init__(self) -> None:
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
        check_type = self._convert_check_type(data.check_type)

        match data.limit_type:
            case PluginLimitType.CD:
                return PluginCdBlock(
                    status=data.status,
                    check_type=check_type,
                    watch_type=data.watch_type,
                    result=data.result,
                    cd=data.cd,
                )
            case PluginLimitType.BLOCK:
                return BaseBlock(
                    status=data.status,
                    check_type=check_type,
                    watch_type=data.watch_type,
                    result=data.result,
                )
            case PluginLimitType.COUNT:
                return PluginCountBlock(
                    status=data.status,
                    watch_type=data.watch_type,
                    result=data.result,
                    max_count=data.max_count,
                )
            case _:
                return BaseBlock(
                    status=data.status,
                    check_type=check_type,
                    watch_type=data.watch_type,
                    result=data.result,
                )

    @staticmethod
    def _convert_check_type(check_type: LimitCheckType) -> BlockType:
        """转换检查类型

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
            case _:
                return BlockType.ALL

    def exists(self, module: str, limit_type: PluginLimitType) -> bool:
        """检查限制是否存在

        参数:
            module: 模块名称
            limit_type: 限制类型

        返回:
            是否存在
        """
        match limit_type:
            case PluginLimitType.CD:
                return module in self.cd_data
            case PluginLimitType.BLOCK:
                return module in self.block_data
            case PluginLimitType.COUNT:
                return module in self.count_data
            case _:
                return False

    def init(self) -> None:
        """初始化管理器"""
        for limit_type in (
            PluginLimitType.CD,
            PluginLimitType.BLOCK,
            PluginLimitType.COUNT,
        ):
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
            case _:
                return self.block_file

    def _load_all_files(self) -> None:
        """加载所有限制文件"""
        for limit_type in (
            PluginLimitType.CD,
            PluginLimitType.BLOCK,
            PluginLimitType.COUNT,
        ):
            self._load_limit_file(limit_type)

    def _load_limit_file(self, limit_type: PluginLimitType) -> None:
        """加载指定类型的限制文件

        参数:
            limit_type: 限制类型
        """
        file_path = self._get_file_path(limit_type)
        type_name, _, data_attr = LIMIT_TYPE_MAP[limit_type]
        model_class = LIMIT_MODEL_MAP[limit_type]

        data_dict: dict[str, Any] = {}
        if file_path.exists():
            with open(file_path, encoding="utf8") as f:
                temp = _yaml.load(f) or {}
                if type_name in temp:
                    for k, v in temp[type_name].items():
                        key = k.split(".")[-1] if "." in k else k
                        data_dict[key] = model_class.parse_obj(v)

        setattr(self, data_attr, data_dict)

    def save_file(self) -> None:
        """保存所有限制文件"""
        for limit_type in (
            PluginLimitType.CD,
            PluginLimitType.BLOCK,
            PluginLimitType.COUNT,
        ):
            self._save_limit_file(limit_type)

    def _save_limit_file(self, limit_type: PluginLimitType) -> None:
        """保存指定类型的限制文件

        参数:
            limit_type: 限制类型
        """
        type_name, comment, data_attr = LIMIT_TYPE_MAP[limit_type]
        data: dict = getattr(self, data_attr)

        temp_data = self._prepare_save_data(data, limit_type)
        file_path = self._get_file_path(limit_type)

        with open(file_path, "w", encoding="utf8") as f:
            _yaml.dump({type_name: temp_data}, f)

        with open(file_path, encoding="utf8") as rf:
            _data = _yaml.load(rf)

        _data.yaml_set_comment_before_after_key(after=comment, key=type_name)
        with open(file_path, "w", encoding="utf8") as wf:
            _yaml.dump(_data, wf)

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

        temp_data = {}
        for k, v in data.items():
            temp_data[k] = v.to_dict()
            if check_type := temp_data[k].get("check_type"):
                temp_data[k]["check_type"] = str(check_type)
            if watch_type := temp_data[k].get("watch_type"):
                temp_data[k]["watch_type"] = str(watch_type)
            if limit_type == PluginLimitType.COUNT:
                temp_data[k].pop("check_type", None)

        return temp_data

    @staticmethod
    def _create_default_data(limit_type: PluginLimitType) -> dict[str, Any]:
        """创建默认数据

        参数:
            limit_type: 限制类型

        返回:
            默认数据字典
        """
        default_data = {
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

        return default_data

    def _replace_data(
        self,
        db_data: PluginLimit | None,
        limit: BaseBlock | PluginCdBlock | PluginCountBlock,
    ) -> PluginLimit:
        """替换数据

        参数:
            db_data: 数据库数据
            limit: 限制数据

        返回:
            更新后的 PluginLimit
        """
        if not db_data:
            db_data = PluginLimit()

        db_data.status = limit.status
        db_data.check_type = self._convert_block_to_check_type(limit.check_type)
        db_data.watch_type = limit.watch_type
        db_data.result = limit.result or ""

        return db_data

    @staticmethod
    def _convert_block_to_check_type(check_type: BlockType | None) -> LimitCheckType:
        """转换阻塞类型为检查类型

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
            case _:
                return LimitCheckType.ALL

    def _set_data(
        self,
        k: str,
        db_data: PluginLimit | None,
        limit: BaseBlock | PluginCdBlock | PluginCountBlock,
        limit_type: PluginLimitType,
        module2plugin: dict[str, PluginInfo],
    ) -> tuple[PluginLimit, bool]:
        """设置数据

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
            return (
                PluginLimit(
                    module=k,
                    module_path=module2plugin[k].module_path,
                    limit_type=limit_type,
                    plugin=module2plugin[k],
                    cd=getattr(limit, "cd", None),
                    max_count=getattr(limit, "max_count", None),
                    status=limit.status,
                    check_type=limit.check_type,
                    watch_type=limit.watch_type,
                    result=limit.result,
                ),
                True,
            )

        db_data = self._replace_data(db_data, limit)

        match limit_type:
            case PluginLimitType.CD:
                db_data.cd = limit.cd  # type: ignore
            case PluginLimitType.COUNT:
                db_data.max_count = limit.max_count  # type: ignore

        return db_data, False

    def _get_file_data(self, limit_type: PluginLimitType) -> dict:
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
            case _:
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

        for limit_type in (
            PluginLimitType.CD,
            PluginLimitType.COUNT,
            PluginLimitType.BLOCK,
        ):
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

        try:
            for limit in create_list:
                await limit.save()

            for limit in update_list:
                await limit.save()

            for limit_id in delete_list:
                if limit := await PluginLimit.safe_get_or_none(id=limit_id):
                    await limit.delete()

            cnt = len(await PluginLimit.filter(status=True).all())
            logger.info(f"已经加载 {cnt} 个插件限制.")
        except Exception as e:
            logger.error(f"加载插件限制到数据库失败: {e}")
            raise


manager = Manager()
