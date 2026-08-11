import asyncio
import subprocess
from pathlib import Path
from typing import ClassVar

from liuying.configs.config import Config
from liuying.utils.log import logger

LOG_COMMAND = "VirtualEnvPackageManager"

Config.add_plugin_config(
    "virtualenv",
    "python_path",
    None,
    help="虚拟环境python路径，为空时使用系统环境的uv",
)


class VirtualEnvPackageManager:
    """虚拟环境包管理器

    提供虚拟环境下的依赖包安装、卸载、列表等功能。
    """
    DEFAULT_COMMAND: ClassVar[list[str]] = ["uv", "pip"]

    @classmethod
    def __get_command(cls) -> list[str]:
        if path := Config.get_config("virtualenv", "python_path"):
            return [path, "-m", "pip"]
        return cls.DEFAULT_COMMAND.copy()

    @classmethod
    async def _run_pip(
        cls,
        subcommand: str,
        packages: list[str] | str,
        extra_args: list[str] | None = None,
    ) -> str:
        """执行pip命令的通用方法

        参数:
            subcommand: pip子命令 (install/uninstall/list)
            packages: 包名称或列表
            extra_args: 额外参数

        返回:
            str: 命令执行结果
        """
        if isinstance(packages, str):
            packages = [packages]
        try:
            command = cls.__get_command()
            command.append(subcommand)
            if extra_args:
                command.extend(extra_args)
            if packages:
                command.extend(packages)
            logger.info(f"执行虚拟环境{subcommand}包指令: {command}", LOG_COMMAND)
            result = await asyncio.to_thread(
                subprocess.run,
                command,
                check=True,
                capture_output=True,
                text=True,
            )
            logger.debug(
                f"虚拟环境{subcommand}包指令执行完成: {result.stdout}",
                LOG_COMMAND,
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            logger.error(
                f"虚拟环境{subcommand}包指令执行失败: {e.stderr}.",
                LOG_COMMAND,
            )
            return e.stderr

    @classmethod
    async def install(cls, package: list[str] | str):
        """安装依赖包

        参数:
            package: 安装依赖包名称或列表
        """
        await cls._run_pip("install", package)

    @classmethod
    async def uninstall(cls, package: list[str] | str):
        """卸载依赖包

        参数:
            package: 卸载依赖包名称或列表
        """
        await cls._run_pip("uninstall", package, ["-y"])

    @classmethod
    async def update(cls, package: list[str] | str):
        """更新依赖包

        参数:
            package: 更新依赖包名称或列表
        """
        await cls._run_pip("install", package, ["--upgrade"])

    @classmethod
    async def install_requirement(cls, requirement_file: Path):
        """安装依赖文件

        参数:
            requirement_file: requirement文件路径

        异常:
            FileNotFoundError: 文件不存在
        """
        if not await asyncio.to_thread(requirement_file.exists):
            raise FileNotFoundError(f"依赖文件 {requirement_file} 不存在")
        abs_path = requirement_file.absolute()
        return await cls._run_pip("install", [], ["-r", str(abs_path)])

    @classmethod
    async def list(cls) -> str:
        """列出已安装的依赖包"""
        return await cls._run_pip("list", [])
