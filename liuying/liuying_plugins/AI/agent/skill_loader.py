"""技能包扩展加载器

在基础 skill_runtime 之上提供远程skill加载、技能隔离执行、
技能安全审查、运行时技能覆盖等扩展能力。
"""

import asyncio
import io
from pathlib import Path
import re
from typing import Any
import zipfile

from liuying.utils.http.http_utils import AsyncHttpx
from liuying.utils.log import logger

from ..config import get_config

_REMOTE_CACHE_DIR = "remote_skills"
"""远程skill缓存目录名"""

_MAX_SKILL_SIZE_BYTES = 5 * 1024 * 1024
"""单个skill包最大字节数"""

_UNSAFE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bos\.system\s*\("),
    re.compile(r"\bsubprocess\.\w+\s*\("),
    re.compile(r"\beval\s*\("),
    re.compile(r"\bexec\s*\("),
    re.compile(r"\b__import__\s*\("),
    re.compile(r"\bopen\s*\(\s*['\"](/etc|/proc|/sys)"),
    re.compile(r"socket\.socket\s*\("),
    re.compile(r"ctypes\.\w+"),
)
"""不安全代码模式正则元组"""

_DANGEROUS_IMPORTS: frozenset[str] = frozenset({
    "os", "subprocess", "sys", "ctypes", "socket",
    "shutil", "pathlib",
})
"""需审查的危险模块集合"""

_GITHUB_BLOB_PATTERN = re.compile(
    r"^https?://github\.com/[\w.-]+/[\w.-]+/blob/"
)
"""GitHub blob URL正则"""

_GITHUB_RAW_PREFIX = "https://raw.githubusercontent.com/"
"""GitHub raw URL前缀"""


class SkillLoader:
    """技能包扩展加载器

    提供远程加载、隔离执行、安全审查、运行时覆盖能力。
    """

    def __init__(self) -> None:
        """初始化扩展加载器"""
        self._overrides: dict[str, Any] = {}
        self._base_dir = (
            Path(__file__).parent / "skillpacks"
        )

    def is_remote_enabled(self) -> bool:
        """检查远程skill加载是否启用

        返回:
            bool: 是否启用
        """
        return bool(get_config("SKILL_REMOTE_ENABLED", False))

    def get_override(self, skill_name: str) -> Any | None:
        """获取已覆盖的技能处理器

        参数:
            skill_name: 技能名

        返回:
            Any | None: 处理器或None
        """
        return self._overrides.get(skill_name)

    def has_override(self, skill_name: str) -> bool:
        """判断技能是否已被覆盖

        参数:
            skill_name: 技能名

        返回:
            bool: 是否已覆盖
        """
        return skill_name in self._overrides

    def override(
        self, skill_name: str, handler: Any
    ) -> None:
        """运行时覆盖默认技能

        将指定技能名映射到自定义处理器，优先于默认注册表。

        参数:
            skill_name: 技能名
            handler: 处理器（异步函数或可调用对象）
        """
        if not skill_name:
            return
        self._overrides[skill_name] = handler
        logger.info(
            f"技能覆盖已注册: {skill_name}",
            command="AI",
        )

    def clear_override(self, skill_name: str) -> None:
        """清除技能覆盖

        参数:
            skill_name: 技能名
        """
        if skill_name in self._overrides:
            del self._overrides[skill_name]
            logger.debug(
                f"技能覆盖已清除: {skill_name}",
                command="AI",
            )

    async def load_remote(self, url: str) -> bool:
        """加载远程skill

        支持GitHub blob URL自动转raw、ZIP压缩包URL下载解压。
        下载后进行大小校验与安全审查，通过后缓存到本地。

        参数:
            url: 远程skill URL（GitHub blob 或 ZIP直链）

        返回:
            bool: 是否加载成功
        """
        if not self.is_remote_enabled():
            logger.warning(
                "远程skill加载未启用",
                command="AI",
            )
            return False
        if not url or not url.strip():
            return False

        try:
            target_url = self._normalize_url(url)
            content = await self._download(target_url)
            if not content:
                return False
            if len(content) > _MAX_SKILL_SIZE_BYTES:
                logger.warning(
                    f"skill包过大: {len(content)} bytes",
                    command="AI",
                )
                return False

            skill_dir = await self._extract(content, url)
            if skill_dir is None:
                return False

            review = await self.review_skill(
                str(skill_dir)
            )
            if not review.get("safe", False):
                logger.warning(
                    f"skill安全审查未通过: {review}",
                    command="AI",
                )
                return False

            logger.info(
                f"远程skill加载成功: {skill_dir.name}",
                command="AI",
            )
            return True
        except Exception as e:
            logger.warning(
                f"加载远程skill失败: {e}",
                command="AI",
                e=e,
            )
            return False

    def _normalize_url(self, url: str) -> str:
        """规范化URL（GitHub blob转raw）

        参数:
            url: 原始URL

        返回:
            str: 规范化后的URL
        """
        if _GITHUB_BLOB_PATTERN.match(url):
            return url.replace(
                "github.com",
                "raw.githubusercontent.com",
            ).replace("/blob/", "/")
        return url

    async def _download(self, url: str) -> bytes:
        """下载远程内容

        参数:
            url: 下载URL

        返回:
            bytes: 内容字节
        """
        try:
            response = await AsyncHttpx.get(
                url, timeout=30.0, follow_redirects=True
            )
            return response.content or b""
        except Exception as e:
            logger.warning(
                f"下载skill失败: {e}",
                command="AI",
                e=e,
            )
            return b""

    async def _extract(
        self, content: bytes, url: str
    ) -> Path | None:
        """解压skill包到缓存目录

        参数:
            content: ZIP内容字节
            url: 原始URL（用于命名）

        返回:
            Path | None: 解压目录或None
        """
        cache_dir = self._base_dir.parent / _REMOTE_CACHE_DIR
        cache_dir.mkdir(parents=True, exist_ok=True)
        skill_name = self._derive_name(url)
        target = cache_dir / skill_name
        if target.exists():
            return target

        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                await asyncio.to_thread(
                    zf.extractall, target
                )
            return target
        except zipfile.BadZipFile as e:
            logger.warning(
                f"skill包解压失败（非ZIP）: {e}",
                command="AI",
                e=e,
            )
            return None

    def _derive_name(self, url: str) -> str:
        """从URL推导skill名

        参数:
            url: URL字符串

        返回:
            str: skill名
        """
        cleaned = url.rstrip("/").split("?")[0]
        last = cleaned.rsplit("/", 1)[-1]
        for ext in (".zip", ".py", ".git"):
            if last.endswith(ext):
                last = last[: -len(ext)]
        return last or "remote_skill"

    async def review_skill(
        self, skill_path: str
    ) -> dict[str, Any]:
        """安全审查skill

        扫描skill目录下所有.py文件，检测危险模式与可疑导入。
        返回审查报告字典。

        参数:
            skill_path: skill目录路径

        返回:
            dict: 审查报告，含 safe/issues/files 字段
        """
        result: dict[str, Any] = {
            "safe": True,
            "issues": [],
            "files": 0,
        }
        path = Path(skill_path)
        if not path.exists():
            result["safe"] = False
            result["issues"].append("路径不存在")
            return result

        py_files = list(path.rglob("*.py"))
        result["files"] = len(py_files)
        if not py_files:
            result["safe"] = False
            result["issues"].append("无Python文件")
            return result

        for py_file in py_files:
            try:
                content = await asyncio.to_thread(
                    py_file.read_text, "utf-8"
                )
            except Exception as e:
                result["issues"].append(
                    f"读取失败 {py_file.name}: {e}"
                )
                continue
            self._scan_content(
                content, py_file.name, result
            )

        result["safe"] = len(result["issues"]) == 0
        return result

    def _scan_content(
        self,
        content: str,
        filename: str,
        result: dict[str, Any],
    ) -> None:
        """扫描文件内容检测危险模式

        参数:
            content: 文件内容
            filename: 文件名
            result: 审查结果字典（原地修改）
        """
        for pattern in _UNSAFE_PATTERNS:
            match = pattern.search(content)
            if match:
                result["issues"].append(
                    f"{filename}: 危险模式 {match.group(0)}"
                )

        for module in _DANGEROUS_IMPORTS:
            import_pattern = re.compile(
                rf"^\s*(?:import\s+{module}\b"
                rf"|from\s+{module}\s+import)",
                re.MULTILINE,
            )
            if import_pattern.search(content):
                result["issues"].append(
                    f"{filename}: 可疑导入 {module}"
                )

    async def run_isolated(
        self,
        script_path: str,
        args: list[str] | None = None,
        timeout: float = 30.0,
    ) -> str:
        """子进程隔离执行不可信skill

        在独立子进程中执行skill脚本，限制超时与输出。

        参数:
            script_path: 脚本路径
            args: 参数列表
            timeout: 超时秒数

        返回:
            str: 子进程stdout输出
        """
        cmd = ["python", script_path]
        if args:
            cmd.extend(args)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            if proc.returncode != 0:
                err = stderr.decode(
                    "utf-8", errors="replace"
                )
                logger.warning(
                    f"隔离执行失败 rc={proc.returncode}: {err}",
                    command="AI",
                )
                return ""
            return stdout.decode("utf-8", errors="replace")
        except TimeoutError:
            logger.warning(
                f"隔离执行超时: {script_path}",
                command="AI",
            )
            return ""
        except Exception as e:
            logger.warning(
                f"隔离执行异常: {e}",
                command="AI",
                e=e,
            )
            return ""


skill_loader = SkillLoader()
"""技能包扩展加载器单例"""
