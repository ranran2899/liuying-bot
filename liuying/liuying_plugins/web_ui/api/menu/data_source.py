import ujson as json

from liuying.configs.path_config import DATA_PATH
from liuying.utils.log import logger

from ...public import get_version
from .model import MenuData, MenuItem

default_menus = [
    MenuItem(
        name="仪表盘",
        module="dashboard",
        router="/dashboard",
        icon="dashboard",
        default=True,
    ),
    MenuItem(
        name="流萤控制台",
        module="command",
        router="/command",
        icon="command",
    ),
    MenuItem(name="插件列表", module="plugin", router="/plugin", icon="plugin"),
    MenuItem(name="插件商店", module="store", router="/store", icon="store"),
    MenuItem(name="好友/群组", module="manage", router="/manage", icon="user"),
    MenuItem(
        name="数据库管理",
        module="database",
        router="/database",
        icon="database",
    ),
    MenuItem(name="系统信息", module="system", router="/system", icon="system"),
    MenuItem(name="关于我们", module="about", router="/about", icon="about"),
    MenuItem(name="流萤AI", module="ai", router="/ai", icon="ai"),
]


class MenuManager:
    def __init__(self) -> None:
        self.file = DATA_PATH / "web_ui" / "menu.json"
        self.menu = []
        if self.file.exists():
            try:
                temp_menu = []
                with self.file.open(encoding="utf8") as f:
                    self.menu = json.load(f)
                # 提取已存菜单的 module 标识，用于与默认菜单比对
                self_menu_module = [m.get("module") for m in self.menu]
                for module in [m.module for m in default_menus]:
                    if module in self_menu_module:
                        temp_menu.append(
                            MenuItem(
                                **next(m for m in self.menu if m["module"] == module)
                            )
                        )
                    else:
                        temp_menu.append(self.__get_menu_model(module))
                self.menu = temp_menu
            except Exception as e:
                logger.warning(
                    "菜单文件损坏，已重新生成...", command="WebUi", e=e
                )
        if not self.menu:
            self.menu = default_menus
        self.save()

    def __get_menu_model(self, module: str):
        return default_menus[
            next(i for i, m in enumerate(default_menus) if m.module == module)
        ]

    def get_menus(self):
        return MenuData(version=get_version(), menus=self.menu)

    def add_external(self, item: MenuItem):
        """新增外部插件注册的菜单项（按 module 去重）"""
        if any(m.module == item.module for m in self.menu):
            return
        self.menu.append(item)
        self.save()

    def keep_modules(self, modules: set[str]):
        """仅保留指定 module 的菜单项（同步清理已卸载插件的残留菜单）"""
        temp = [m for m in self.menu if m.module in modules]
        if len(temp) != len(self.menu):
            self.menu = temp
            self.save()

    def save(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        temp = [menu.to_dict() for menu in self.menu]
        with self.file.open("w", encoding="utf8") as f:
            json.dump(temp, f, ensure_ascii=False, indent=4)


menu_manage = MenuManager()
