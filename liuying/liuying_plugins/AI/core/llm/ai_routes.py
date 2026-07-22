"""AI Provider 多CLI路由

支持通过命令行工具（如 gemini_cli/claude_code 等）调用AI，
作为 HTTP API provider 的补充降级路径。

当 provider_router 的所有 HTTP provider 均失败时，
按优先级尝试配置的 CLI 路由，通过子进程调用 CLI 工具。

配置格式（AI_CLI_ROUTES 为 JSON 字符串）：
[
  {
    "name": "gemini_cli",
    "command": ["gemini"],
    "args": ["--prompt"],
    "use_stdin": true,
    "timeout": 30,
    "priority": 1
  },
  {
    "name": "claude_code",
    "command": ["claude"],
    "args": ["--print"],
    "use_stdin": true,
    "timeout": 30,
    "priority": 2
  }
]

工作流程：
1. 从配置加载 CLI 路由列表，按 priority 排序
2. 依次尝试每个路由，通过子进程调用 CLI 工具
3. use_stdin=True 时通过 stdin 传递 prompt，否则追加到命令末尾
4. 读取 stdout 作为响应文本
5. 首个成功响应即返回，失败则尝试下一个路由
"""

import asyncio
from dataclasses import dataclass, field
import json

from liuying.utils.log import logger

from ...config import get_config

__all__ = [
    "AiCliRoute",
    "AiCliRouter",
    "ai_cli_router",
]

_DEFAULT_TIMEOUT = 30
"""默认CLI调用超时（秒）"""


@dataclass(slots=True)
class AiCliRoute:
    """CLI路由配置

    Attributes:
        name: 路由名称（如 gemini_cli/claude_code）
        command: CLI命令列表（如 ["gemini"]）
        args: 命令参数列表（如 ["--prompt"]）
        use_stdin: 是否通过stdin传递prompt
        timeout: 调用超时（秒）
        priority: 优先级（数字越小越优先）
    """

    name: str
    command: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)
    use_stdin: bool = True
    timeout: int = _DEFAULT_TIMEOUT
    priority: int = 100

    def build_cmd(self, prompt: str) -> list[str]:
        """构建完整命令

        参数:
            prompt: 用户prompt（use_stdin=False时追加到命令末尾）

        返回:
            list[str]: 完整命令列表
        """
        cmd = list(self.command) + list(self.args)
        if not self.use_stdin and prompt:
            cmd.append(prompt)
        return cmd


class AiCliRouter:
    """AI CLI路由器

    管理多个CLI路由，按优先级尝试调用。
    作为 provider_router 的降级路径，仅在 HTTP provider 全部失败时启用。
    """

    def __init__(self) -> None:
        """初始化CLI路由器"""
        self._routes_cache: list[AiCliRoute] | None = None
        self._config_hash: str = ""

    def _load_routes(self) -> list[AiCliRoute]:
        """从配置加载CLI路由列表

        返回:
            list[AiCliRoute]: 按priority排序的路由列表
        """
        raw = get_config("AI_CLI_ROUTES", "")
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                f"AI_CLI_ROUTES 配置解析失败: {raw[:100]}",
                command="AI",
            )
            return []
        if not isinstance(data, list):
            return []

        routes: list[AiCliRoute] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            command = item.get("command", [])
            if not name or not command:
                continue
            if isinstance(command, str):
                command = [command]
            args = item.get("args", [])
            if isinstance(args, str):
                args = [args]
            routes.append(
                AiCliRoute(
                    name=name,
                    command=[str(c) for c in command],
                    args=[str(a) for a in args],
                    use_stdin=bool(item.get("use_stdin", True)),
                    timeout=int(item.get("timeout", _DEFAULT_TIMEOUT)),
                    priority=int(item.get("priority", 100)),
                )
            )
        routes.sort(key=lambda r: r.priority)
        return routes

    def get_routes(self) -> list[AiCliRoute]:
        """获取CLI路由列表（带缓存）

        配置未变化时复用缓存，避免每次调用都解析JSON。

        返回:
            list[AiCliRoute]: 按priority排序的路由列表
        """
        raw = str(get_config("AI_CLI_ROUTES", "") or "")
        if raw == self._config_hash and self._routes_cache is not None:
            return self._routes_cache
        self._config_hash = raw
        self._routes_cache = self._load_routes()
        return self._routes_cache

    async def call(
        self,
        prompt: str,
        messages: list[dict[str, str]] | None = None,
    ) -> str | None:
        """通过CLI路由调用AI

        按优先级依次尝试每个路由，首个成功响应即返回。
        use_stdin=True 时将完整prompt通过stdin传递，
        否则将prompt追加到命令末尾。

        参数:
            prompt: 调用prompt（已格式化的完整文本）
            messages: 原始消息列表（备用，当前实现使用prompt）

        返回:
            str | None: 响应文本，全部失败返回None
        """
        if not get_config("AI_CLI_ENABLED", False):
            return None
        routes = self.get_routes()
        if not routes:
            return None

        # 构建完整prompt（messages优先，降级到prompt参数）
        full_prompt = prompt
        if messages:
            parts: list[str] = []
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                parts.append(f"[{role}] {content}")
            full_prompt = "\n".join(parts)

        for route in routes:
            try:
                result = await self._call_route(route, full_prompt)
                if result:
                    logger.info(
                        f"CLI路由调用成功: {route.name}",
                        command="AI",
                    )
                    return result
            except Exception as e:
                logger.warning(
                    f"CLI路由 {route.name} 调用失败: {e}",
                    command="AI",
                    e=e,
                )
        return None

    async def _call_route(
        self, route: AiCliRoute, prompt: str
    ) -> str:
        """调用单个CLI路由

        参数:
            route: CLI路由配置
            prompt: 完整prompt文本

        返回:
            str: CLI输出文本

        异常:
            asyncio.TimeoutError: 调用超时
            Exception: 子进程调用失败
        """
        cmd = route.build_cmd(prompt)
        logger.debug(
            f"CLI路由调用: {route.name} cmd={cmd}",
            command="AI",
        )
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdin_data = prompt.encode("utf-8") if route.use_stdin else None
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin_data),
                timeout=route.timeout,
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise

        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"CLI {route.name} 退出码 {proc.returncode}: {err_msg}"
            )
        return stdout.decode("utf-8", errors="replace").strip()


ai_cli_router = AiCliRouter()
"""AI CLI路由器单例"""
