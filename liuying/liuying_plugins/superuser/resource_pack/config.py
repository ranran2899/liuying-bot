from pathlib import Path

from liuying.configs.path_config import RESOURCES_PATH, WEB_UI_PATH

LOG_COMMAND = "资源包管理"
"""日志命令标识"""

DEFAULT_VERSION = "1.0.0"
"""资源包缺失版本号时的默认值"""

RESOURCE_PACKS: tuple["ResourcePackMeta", ...]
"""资源包元信息列表，延迟定义见下方"""


class ResourcePackMeta:
    """资源包元信息

    描述一个可通过压缩包安装/更新的资源包。
    """

    def __init__(
        self,
        name: str,
        repo_url: str,
        json_file: str,
        target_path: Path,
        description: str,
    ) -> None:
        self.name = name
        """资源包名称"""
        self.repo_url = repo_url
        """资源包索引仓库地址"""
        self.json_file = json_file
        """索引 json 文件名（仓库根目录下）"""
        self.target_path = target_path
        """解压安装目标目录"""
        self.description = description
        """资源包说明"""


RESOURCE_PACKS = (
    ResourcePackMeta(
        name="resources",
        repo_url="https://gitee.com/shiranranran/liuying-resources/tree/master",
        json_file="resource.json",
        target_path=RESOURCES_PATH,
        description="机器人静态资源包（图片/字体/主题/模板等）",
    ),
    ResourcePackMeta(
        name="web_ui",
        repo_url="https://gitee.com/shiranranran/liuying-webui/tree/master",
        json_file="web_ui.json",
        target_path=WEB_UI_PATH,
        description="WebUI 前端静态资源包",
    ),
)
