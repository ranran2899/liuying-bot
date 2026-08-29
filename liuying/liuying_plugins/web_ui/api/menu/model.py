from nonebot.compat import model_dump
from pydantic import BaseModel


class MenuItem(BaseModel):
    module: str
    """模块名称"""
    name: str
    """菜单名称"""
    router: str
    """路由"""
    icon: str
    """图标"""
    default: bool = False
    """默认选中"""
    js: str = ""
    """外部页面模块地址（为空表示前端内置路由）"""
    css: list[str] = []
    """外部页面样式表地址列表（为空不注入）"""

    def to_dict(self, **kwargs):
        return model_dump(self, **kwargs)


class MenuData(BaseModel):
    bot_type: str = "liuying"
    """bot类型"""
    version: str = ""
    """前端资源版本指纹（由 public.get_version 生成）"""
    menus: list[MenuItem]
    """菜单列表"""
