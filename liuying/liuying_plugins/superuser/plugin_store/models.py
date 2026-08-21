from typing import Any

from pydantic import BaseModel

from liuying.utils.enum import PluginType
from liuying.utils.pydantic_compat import model_dump

type2name: dict[str, str] = {
    "NORMAL": "普通插件",
    "ADMIN": "管理员插件",
    "SUPERUSER": "超级用户插件",
    "ADMIN_SUPER": "管理员/超级用户插件",
    "DEPENDANT": "依赖插件",
    "HIDDEN": "其他插件",
    "PARENT": "父插件",
}


class StorePluginInfo(BaseModel):
    """插件信息"""

    name: str
    """插件名"""
    module: str
    """模块名"""
    module_path: str
    """模块路径"""
    description: str
    """简介"""
    usage: str
    """用法"""
    author: str
    """作者"""
    version: str
    """版本"""
    plugin_type: PluginType
    """插件类型"""
    is_dir: bool
    """是否为文件夹插件"""
    gitee_url: str | None = None
    """gitee链接"""
    github_url: str | None = None
    """github链接"""

    @property
    def plugin_type_name(self) -> str:
        """插件类型中文名"""
        return type2name[self.plugin_type.value]

    def to_dict(self, **kwargs: Any) -> dict[str, Any]:
        """转换为字典

        参数:
            **kwargs: 传递给 model_dump 的额外参数

        返回:
            dict[str, Any]: 插件信息字典
        """
        return model_dump(self, **kwargs)
