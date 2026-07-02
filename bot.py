""" 初始化流萤机器人 """
import nonebot
from nonebot.adapters.minecraft import (
    Adapter as MinecraftAdapter,  # 加载Minecraft适配器
)
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter
from nonebot.adapters.onebot.v12 import Adapter as OneBotV12Adapter
from nonebot.adapters.qq import Adapter as QQAdapter

# from nonebot.adapters.mail import Adapter as MailAdapter

# 初始化 NoneBot 框架

nonebot.init()

# 导入并注册适配器
driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)
driver.register_adapter(OneBotV12Adapter)
driver.register_adapter(QQAdapter)
driver.register_adapter(MinecraftAdapter)
# driver.register_adapter(MailAdapter) # 暂时不支持

from liuying.services.liuying_db import session_manager

# 注册数据库断开连接函数
driver.on_shutdown(session_manager.disconnect)


# 加载内置插件和本地插件
# nonebot.load_builtin_plugins("echo")  # 加载内置的 echo 插件
nonebot.load_plugins("liuying/liuying_plugins")  # 加载主插件目录
# nonebot.load_plugins("liuying/builtin_plugins")  # 加载副插件目录
nonebot.load_plugins("liuying/plugins") # 加载自定义插件目录


if __name__ == "__main__":
    nonebot.run()



# 想你了流萤小姐
