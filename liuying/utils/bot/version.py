"""
机器人信息工具模块

提供异步获取机器人名称和版本号的功能
"""

import asyncio
from pathlib import Path

from liuying.configs.config import BotConfig

# async def get_bot_info() -> Tuple[str, str]:
#     """
#     异步获取机器人名称和版本号

#     返回:
#         Tuple[str, str]: (机器人名称, 版本号)
#     """
#     # 获取机器人名称
#     bot_name = NICKNAME or "流萤"

#     # 获取版本号
#     version = await get_bot_version()

#     return bot_name, version

class BotVersionInfo:
    """
    机器人版本信息类
    
    提供异步获取机器人版本号的功能
    """

    @classmethod
    async def get_version(cls) -> str:
        """
        异步获取机器人版本号
        
        返回:
            str: 版本号
        """
        return await get_bot_version()


async def get_bot_version() -> str:
    """
    获取机器人版本号
    
    返回:
        str: 版本号
    """
    # 使用异步方式读取版本文件
    loop = asyncio.get_event_loop()
    version_file = Path() / "__version__"

    try:
        # 使用run_in_executor避免阻塞事件循环
        with open(version_file, encoding="utf-8") as f:
            content = await loop.run_in_executor(None, f.read)
            # 解析版本号，格式为 __version__: v0.0.1
            for line in content.splitlines():
                if line.startswith("__version__:"):
                    return line.split(":", 1)[1].strip()
        return "未知版本"
    except Exception:
        return "未知版本"


async def get_bot_name() -> str:
    """
    获取机器人名称
    
    返回:
        str: 机器人名称
    """
    return BotConfig.self_nickname or "流萤"
