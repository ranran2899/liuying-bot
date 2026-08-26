import asyncio
from pathlib import Path
import shutil
import zipfile

import orjson as json

from liuying.configs.path_config import TEMP_PATH
from liuying.utils.http.http_utils import AsyncHttpx
from liuying.utils.log import logger
from liuying.utils.repo_utils import repo_file_manager
from liuying.utils.utils import win_on_rm_error

from .config import DEFAULT_VERSION, LOG_COMMAND, RESOURCE_PACKS, ResourcePackMeta
from .exceptions import ResourcePackException
from .models import ResourcePackInfo

_VERSION_FILE = "version.json"
"""目标目录内记录已安装版本号的文件名"""


class ResourcePackManager:
    """资源包管理器

    负责从远程仓库拉取索引 json，下载压缩包并解压安装到目标目录，
    支持版本比对与批量更新。
    """

    @classmethod
    async def get_remote_info(cls, meta: ResourcePackMeta) -> ResourcePackInfo:
        """获取远程资源包索引信息

        参数:
            meta: 资源包元信息

        返回:
            ResourcePackInfo: 远程资源包信息
        """
        content = await repo_file_manager.get_file_content(
            meta.repo_url, meta.json_file
        )
        return ResourcePackInfo(**json.loads(content))

    @classmethod
    def is_installed(cls, meta: ResourcePackMeta) -> bool:
        """判断资源包是否已安装

        以目标目录内的版本记录文件是否存在为准，避免目标目录
        被 path_config 预创建导致 exists() 误判。

        参数:
            meta: 资源包元信息

        返回:
            bool: 是否已安装
        """
        return (meta.target_path / _VERSION_FILE).exists()

    @classmethod
    def get_local_version(cls, meta: ResourcePackMeta) -> str:
        """获取本地已安装版本号

        参数:
            meta: 资源包元信息

        返回:
            str: 本地版本号，未安装返回默认版本
        """
        version_file = meta.target_path / _VERSION_FILE
        if not version_file.exists():
            return DEFAULT_VERSION
        data = json.loads(version_file.read_text(encoding="utf8"))
        return data.get("version", DEFAULT_VERSION)

    @classmethod
    def write_local_version(cls, meta: ResourcePackMeta, version: str) -> None:
        """写入本地已安装版本号

        参数:
            meta: 资源包元信息
            version: 版本号
        """
        version_file = meta.target_path / _VERSION_FILE
        version_file.write_text(
            json.dumps({"name": meta.name, "version": version}).decode("utf-8"),
            encoding="utf8",
        )

    @classmethod
    async def check_update(cls, meta: ResourcePackMeta) -> bool:
        """检查资源包是否有更新

        参数:
            meta: 资源包元信息

        返回:
            bool: 远程版本是否高于本地版本
        """
        remote = await cls.get_remote_info(meta)
        return remote.version != cls.get_local_version(meta)

    @classmethod
    async def _download_archive(cls, info: ResourcePackInfo) -> Path:
        """下载资源包压缩包到临时目录

        参数:
            info: 资源包信息

        返回:
            Path: 压缩包本地路径
        """
        temp_dir = TEMP_PATH / "resource_pack"
        temp_dir.mkdir(parents=True, exist_ok=True)
        archive_path = temp_dir / f"{info.name}.zip"
        result = await AsyncHttpx.download_file(
            info.download_url, archive_path, stream=True
        )
        if not result:
            raise ResourcePackException(f"资源包 {info.name} 压缩包下载失败")
        return archive_path

    @classmethod
    def _top_level_dir(cls, zf: zipfile.ZipFile) -> str | None:
        """识别压缩包内是否存在单一顶层目录

        若压缩包内所有条目共享同一个顶层目录前缀，则返回该目录名，
        用于解压时剥掉这层包裹目录；否则返回 None。

        参数:
            zf: 已打开的压缩包对象

        返回:
            str | None: 顶层目录名，无单一顶层目录时返回 None
        """
        top_dirs = set()
        for name in zf.namelist():
            # 跳过根目录条目与 macOS 元数据
            stripped = name.lstrip("/")
            if not stripped or stripped == "__MACOSX" or "__MACOSX/" in stripped:
                continue
            parts = stripped.split("/")
            if len(parts) > 1:
                top_dirs.add(parts[0])
            else:
                # 存在根目录下的独立文件，说明无包裹目录
                return None
        return top_dirs.pop() if len(top_dirs) == 1 else None

    @classmethod
    def _extract_archive(cls, archive_path: Path, target_path: Path) -> None:
        """解压压缩包到目标目录

        若压缩包内存在单一顶层包裹目录，自动剥掉该层，使解压结果
        直接落在目标目录下，避免出现 target/web_ui/ 这样的嵌套结构。

        参数:
            archive_path: 压缩包路径
            target_path: 目标目录
        """
        target_path.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path) as zf:
            top_dir = cls._top_level_dir(zf)
            if top_dir:
                prefix = f"{top_dir}/"
                for member in zf.namelist():
                    stripped = member.lstrip("/")
                    if not stripped.startswith(prefix) or stripped == prefix:
                        continue
                    rel = stripped[len(prefix):]
                    if not rel:
                        continue
                    dest = target_path / rel
                    if member.endswith("/"):
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member) as src, dest.open("wb") as out:
                            shutil.copyfileobj(src, out)
            else:
                zf.extractall(target_path)

    @classmethod
    async def install(cls, meta: ResourcePackMeta, force: bool = False) -> str:
        """安装或更新资源包

        参数:
            meta: 资源包元信息
            force: 是否强制覆盖安装，忽略版本比对

        返回:
            str: 安装结果描述
        """
        logger.info(f"开始安装资源包 {meta.name}...", LOG_COMMAND)
        info = await cls.get_remote_info(meta)
        local_version = cls.get_local_version(meta)
        if not force and info.version == local_version:
            return f"资源包 {meta.name} 已是最新版本 {info.version}"
        archive_path = await cls._download_archive(info)
        await asyncio.to_thread(cls._extract_archive, archive_path, meta.target_path)
        cls.write_local_version(meta, info.version)
        archive_path.unlink(missing_ok=True)
        logger.info(
            f"资源包 {meta.name} 安装成功: {local_version} -> {info.version}",
            LOG_COMMAND,
        )
        return f"资源包 {meta.name} 安装成功: {info.version}"

    @classmethod
    async def get_packs_info(cls) -> list[str]:
        """获取所有资源包的安装状态信息

        返回:
            list[str]: 各资源包状态描述
        """
        result = []
        for meta in RESOURCE_PACKS:
            try:
                remote = await cls.get_remote_info(meta)
                local = cls.get_local_version(meta)
                status = "已安装" if remote.version == local else "可更新"
                result.append(
                    f"{meta.name}: 本地 {local} / 远程 {remote.version} [{status}]"
                )
            except Exception as e:
                logger.warning(
                    f"获取资源包 {meta.name} 信息失败: {e}", LOG_COMMAND
                )
                result.append(f"{meta.name}: 获取信息失败")
        return result

    @classmethod
    async def update_all(cls, force: bool = False) -> str:
        """更新全部资源包

        参数:
            force: 是否强制覆盖安装，忽略版本比对

        返回:
            str: 更新结果汇总
        """
        success = []
        failed = []
        for meta in RESOURCE_PACKS:
            try:
                result = await cls.install(meta, force=force)
                success.append(result)
            except Exception as e:
                logger.error(f"更新资源包 {meta.name} 失败", LOG_COMMAND, e=e)
                failed.append(f"{meta.name}: {e}")
        lines = []
        if success:
            lines.append("\n".join(success))
        if failed:
            lines.append("失败:\n" + "\n".join(failed))
        return "\n".join(lines) if lines else "没有资源包需要更新"

    @classmethod
    async def cleanup_temp(cls) -> None:
        """清理资源包临时目录"""
        temp_dir = TEMP_PATH / "resource_pack"
        if temp_dir.exists():
            shutil.rmtree(temp_dir, onexc=win_on_rm_error)
