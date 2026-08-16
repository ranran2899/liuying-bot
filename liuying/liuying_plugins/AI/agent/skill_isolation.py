"""技能隔离运行时

在子进程中安全执行非可信技能，通过环境变量白名单与
Python安全防护限制技能的访问范围。
通过stdin/stdout的JSON协议与子进程通信。
"""

import asyncio
import json
import os
from pathlib import Path
import sys
from typing import Any

from liuying.utils.log import logger

__all__ = [
    "SkillIsolationRunner",
    "skill_isolation_runner",
]

_SAFE_ENV_KEYS: frozenset[str] = frozenset(
    {
        "COMSPEC",
        "LANG",
        "LC_ALL",
        "PATH",
        "PATHEXT",
        "SystemRoot",
        "TEMP",
        "TMP",
        "TMPDIR",
        "WINDIR",
    }
)
"""环境变量安全白名单"""

_PYTHON_ENV_GUARDS: dict[str, str] = {
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONIOENCODING": "utf-8",
    "PYTHONNOUSERSITE": "1",
    "PYTHONSAFEPATH": "1",
    "PYTHONUTF8": "1",
}
"""Python安全防护环境变量"""

_DEFAULT_TIMEOUT = 30
"""默认子进程超时（秒）"""

_RUNNER_SCRIPT = Path(__file__).parent / "isolated_runner.py"
"""隔离运行器脚本路径"""


class SkillIsolationRunner:
    """技能隔离运行器

    在受限子进程中执行技能函数，防止非可信代码访问主进程资源。
    """

    @staticmethod
    def _build_env(inherit_env: bool) -> dict[str, str]:
        """构建子进程环境变量

        参数:
            inherit_env: 是否继承完整环境变量

        返回:
            dict: 环境变量字典
        """
        if inherit_env:
            env = dict(os.environ)
        else:
            env = {
                k: v
                for k, v in os.environ.items()
                if k in _SAFE_ENV_KEYS or k.upper() in _SAFE_ENV_KEYS
            }
        env.update(_PYTHON_ENV_GUARDS)
        return env

    @staticmethod
    def _build_payload(
        script_path: Path, function: str, kwargs: dict[str, Any] | None
    ) -> str:
        """构建子进程调用载荷

        路径解析放在同步函数内，避免异步函数体内
        执行文件系统访问（ASYNC240）。

        参数:
            script_path: 技能脚本路径
            function: 要调用的函数名
            kwargs: 函数参数

        返回:
            str: JSON载荷文本
        """
        return json.dumps(
            {
                "script_path": str(script_path.resolve()),
                "function": function,
                "kwargs": kwargs or {},
                "sys_paths": [
                    str(script_path.parent),
                    str(script_path.parent.parent),
                ],
            },
            ensure_ascii=False,
        )

    @classmethod
    async def run_in_subprocess(
        cls,
        script_path: Path,
        function: str = "run",
        kwargs: dict[str, Any] | None = None,
        timeout: int = _DEFAULT_TIMEOUT,
        inherit_env: bool = False,
    ) -> str:
        """在子进程中执行技能函数

        参数:
            script_path: 技能脚本路径
            function: 要调用的函数名
            kwargs: 函数参数
            timeout: 超时时间（秒）
            inherit_env: 是否继承完整环境变量

        返回:
            str: 执行结果文本

        异常:
            TimeoutError: 执行超时
            RuntimeError: 子进程执行失败
        """
        payload = cls._build_payload(script_path, function, kwargs)
        env = cls._build_env(inherit_env)
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(_RUNNER_SCRIPT),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=payload.encode("utf-8")),
                timeout=timeout,
            )
        except TimeoutError:
            # 超时分支同时排空 stderr，保留诊断信息（原实现会丢弃）
            try:
                _, stderr = await proc.communicate()
                err = stderr.decode("utf-8", errors="replace").strip()
                logger.warning(
                    f"技能隔离执行超时: {err}", command="AI"
                )
            except Exception:
                pass
            proc.kill()
            await proc.wait()
            raise

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"隔离执行失败(退出码{proc.returncode}): {err}"
            )

        result = json.loads(
            stdout.decode("utf-8", errors="replace").strip()
        )
        if not result.get("ok"):
            raise RuntimeError(
                f"隔离执行异常: {result.get('error', '未知错误')}"
            )
        ret = result.get("result", "")
        return ret if isinstance(ret, str) else str(ret)


skill_isolation_runner = SkillIsolationRunner
"""技能隔离运行器单例（类方法形式）"""
