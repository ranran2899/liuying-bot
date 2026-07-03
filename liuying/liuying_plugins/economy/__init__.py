from pathlib import Path

import nonebot

# 加载目录下的全部插件
nonebot.load_plugins(str(Path(__file__).parent.resolve()))
