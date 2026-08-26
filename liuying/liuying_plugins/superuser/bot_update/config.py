from pathlib import Path

BASE_PATH = Path().resolve()
"""机器人本体根目录(liuying-a/)"""

REPO_URL = "https://gitee.com/shiranranran/liuying-bot/tree/main"
"""机器人本体仓库地址"""

VERSION_FILE = "__version__"
"""版本文件名"""

LOG_COMMAND = "检查更新"
"""日志命令名"""

EXCLUDE_FILES = {".env"}
"""更新时排除的文件，仓库的 .env 是模板，本地是用户敏感配置，防止覆盖"""

REQUIRED_FILES = (
    "bot.py",
    "__version__",
    "pyproject.toml",
    "liuying/configs/config.py",
)
"""更新前校验文件列表完整性所需的关键文件"""

UPDATE_CONFIRM = {"true", "是", "好", "确定", "确认"}
"""更新确认词"""

RESTART_MARK = Path() / "is_restart"
"""重启标记文件，与机器人重启插件共用"""
