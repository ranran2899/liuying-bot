from pathlib import Path

import nonebot

from liuying.services.log import logger



# # 加载平台插件
# nonebot.load_plugins(str(Path(__file__).parent.resolve()))


path = Path(__file__).parent


try:
    from nonebot.adapters.onebot.v11 import Bot

    nonebot.load_plugins(str((path / "onebot_api").resolve()))
except ImportError:
    logger.warning("未安装 onebot-adapter，无法加载Onebot平台专用插件...")


try:
    from nonebot.adapters.qq import (
        Bot,
    )

    nonebot.load_plugins(str((path / "qq_api").resolve()))
except ImportError:
    logger.warning("未安装 qq-adapter，无法加载QQ官平台专用插件...")

try:
    from nonebot.adapters.minecraft import (
        Bot,
    )

    nonebot.load_plugins(str((path / "minecraft_api").resolve()))
except ImportError:
    logger.warning("未安装 minecraft-adapter，无法加载Minecraft平台专用插件...")