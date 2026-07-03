from pathlib import Path

BASE_PATH = Path() / "liuying"
BASE_PATH.mkdir(parents=True, exist_ok=True)


DEFAULT_GITEE_URL = "https://gitee.com/shiranranran/liuying_bot_plugins/tree/main"
"""伴生插件库gitee仓库地址"""

EXTRA_GITEE_URL = "https://gitee.com/shiranranran/liuying_bot_plugins/tree/index/"
"""插件库第三方索引gitee仓库地址"""

LOG_COMMAND = "插件商店"
