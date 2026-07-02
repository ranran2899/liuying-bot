"""
帮助插件配置模块
"""
import nonebot

from liuying.configs.config import Config
from liuying.configs.path_config import IMAGE_PATH, TEMP_PATH

GROUP_HELP_PATH = TEMP_PATH / "group_help"
GROUP_HELP_PATH.mkdir(exist_ok=True, parents=True)

for file in GROUP_HELP_PATH.iterdir():
    file.unlink()

SIMPLE_HELP_IMAGE = IMAGE_PATH / "SIMPLE_HELP.png"
if SIMPLE_HELP_IMAGE.exists():
    SIMPLE_HELP_IMAGE.unlink()

SIMPLE_DETAIL_HELP_IMAGE = IMAGE_PATH / "SIMPLE_DETAIL_HELP.png"
if SIMPLE_DETAIL_HELP_IMAGE.exists():
    SIMPLE_DETAIL_HELP_IMAGE.unlink()

base_config = Config.get("help")
driver = nonebot.get_driver()
