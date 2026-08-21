from liuying.configs.path_config import PLUGIN_PATH

BASE_PATH = PLUGIN_PATH.parent
"""插件包根目录(liuying/)，目录由 path_config 统一创建"""

DEFAULT_VERSION = "0.1"
"""已安装插件缺失版本号时的默认值"""


DEFAULT_GITEE_URL = "https://gitee.com/shiranranran/liuying_bot_plugins/tree/main"
"""伴生插件库gitee仓库地址"""

EXTRA_GITEE_URL = "https://gitee.com/shiranranran/liuying_bot_plugins/tree/index/"
"""插件库第三方索引gitee仓库地址"""

LOG_COMMAND = "插件商店"
