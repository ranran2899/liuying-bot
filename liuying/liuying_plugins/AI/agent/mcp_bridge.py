"""MCP（Model Context Protocol）桥接

实现 JSON-RPC 2.0 over stdio 协议客户端，支持通过子进程调用 MCP 服务器。
从 JSON 配置加载 MCP 服务器定义，自动发现并注册远程工具。
客户端连接按 server 名池化为长连接，调用异常时自动重建重试。

配置格式（JSON数组）:
    [
        {
            "name": "filesystem",
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem"],
            "env": {},
            "tools": [],
            "timeout": 30
        }
    ]
"""

import asyncio
from dataclasses import dataclass, field
import json
from typing import Any, Self

from liuying.utils.log import logger

from .tools import AgentTool, ToolRegistry

__all__ = [
    "McpBridge",
    "McpServerConfig",
    "McpStdioClient",
    "mcp_bridge",
]

_MCP_PROTOCOL_VERSION = "2024-11-05"
"""MCP协议版本"""

_MCP_CLIENT_NAME = "liuying-ai-mcp"
"""MCP客户端名称"""

_DEFAULT_TIMEOUT = 30
"""默认超时时间（秒）"""

_PROCESS_GRACE = 2.0
"""子进程优雅退出宽限期（秒）"""


@dataclass(slots=True)
class McpServerConfig:
    """MCP服务器配置

    Attributes:
        name: 服务器名称
        command: 启动命令
        args: 命令参数
        env: 环境变量
        tools: 工具白名单（空列表表示全部注册）
        timeout: 超时时间
    """

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    tools: list[str] = field(default_factory=list)
    timeout: int = _DEFAULT_TIMEOUT


class McpStdioClient:
    """MCP stdio 客户端

    通过子进程与 MCP 服务器通信，使用 JSON-RPC 2.0 协议。
    帧格式: Content-Length: {len}\\r\\n\\r\\n{json_body}
    """

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        """初始化MCP客户端

        参数:
            command: 启动命令
            args: 命令参数
            env: 环境变量
        """
        self._command = command
        self._args = args or []
        self._env = env or None
        self._proc: asyncio.subprocess.Process | None = None
        self._request_id = 0

    @property
    def alive(self) -> bool:
        """子进程是否存活"""
        return self._proc is not None and self._proc.returncode is None

    async def start(self) -> Self:
        """启动子进程并完成MCP握手初始化

        返回:
            Self: 客户端自身
        """
        self._proc = await asyncio.create_subprocess_exec(
            self._command,
            *self._args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            # 丢弃 stderr 但不阻塞：MCP 服务器向 stderr 写满
            # 缓冲区后会整体卡死，必须重定向而非留空管道
            stderr=asyncio.subprocess.DEVNULL,
            env=self._env,
        )
        await self.initialize()
        return self

    async def close(self) -> None:
        """优雅关闭子进程

        先 terminate 并等待宽限期，超时仍未退出再 kill。
        """
        proc = self._proc
        self._proc = None
        if proc is None or proc.returncode is not None:
            return
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=_PROCESS_GRACE)
        except TimeoutError:
            proc.kill()
            await proc.wait()

    async def __aenter__(self) -> Self:
        """启动MCP服务器子进程"""
        return await self.start()

    async def __aexit__(
        self, *exc: object
    ) -> None:
        """关闭MCP服务器子进程"""
        await self.close()

    async def initialize(self) -> dict[str, Any]:
        """MCP握手初始化

        返回:
            dict: 服务器返回的初始化信息
        """
        return await self.request(
            "initialize",
            {
                "protocolVersion": _MCP_PROTOCOL_VERSION,
                "clientInfo": {"name": _MCP_CLIENT_NAME},
            },
        )

    async def list_tools(self) -> list[dict[str, Any]]:
        """列出远程工具

        返回:
            list[dict]: 工具定义列表
        """
        result = await self.request("tools/list", {})
        return list(result.get("tools", []))

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> str:
        """调用远程工具

        参数:
            name: 工具名
            arguments: 工具参数

        返回:
            str: 工具执行结果文本
        """
        result = await self.request(
            "tools/call", {"name": name, "arguments": arguments}
        )
        return self._extract_text_result(result)

    async def request(
        self, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """发送JSON-RPC请求并等待响应

        读循环中跳过服务器主动推送的 notification 消息
        （无 id 或 id 不匹配），仅返回与本次请求 id 匹配的响应。

        参数:
            method: 方法名
            params: 参数

        返回:
            dict: 响应结果

        异常:
            RuntimeError: 客户端未启动、连接已关闭或响应携带错误
        """
        if self._proc is None or self._proc.stdout is None:
            raise RuntimeError("MCP客户端未启动")
        self._request_id += 1
        req_id = self._request_id
        message = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
                "params": params,
            },
            ensure_ascii=False,
        )
        await self._write_message(message)
        while True:
            response = await self._read_message()
            if not response:
                raise RuntimeError("MCP连接已关闭")
            data = json.loads(response)
            if data.get("id") != req_id:
                # notification 推送或过期响应，跳过继续读
                continue
            if "error" in data:
                err = data["error"]
                raise RuntimeError(
                    f"MCP错误({err.get('code')}): {err.get('message')}"
                )
            return dict(data.get("result", {}))

    async def _write_message(self, body: str) -> None:
        """写入JSON-RPC消息（带Content-Length头）"""
        if self._proc is None or self._proc.stdin is None:
            return
        data = body.encode("utf-8")
        header = f"Content-Length: {len(data)}\r\n\r\n"
        self._proc.stdin.write(header.encode("utf-8") + data)
        await self._proc.stdin.drain()

    async def _read_message(self) -> str:
        """读取JSON-RPC消息（解析Content-Length头）"""
        if self._proc is None or self._proc.stdout is None:
            return ""
        headers: dict[str, str] = {}
        while True:
            line = await self._proc.stdout.readline()
            if not line or line == b"\r\n":
                break
            line_str = line.decode("utf-8", errors="replace").strip()
            if ":" in line_str:
                key, _, value = line_str.partition(":")
                headers[key.strip().lower()] = value.strip()
        length = int(headers.get("content-length", "0"))
        if length <= 0:
            return ""
        data = await self._proc.stdout.readexactly(length)
        return data.decode("utf-8", errors="replace")

    @staticmethod
    def _extract_text_result(result: dict[str, Any]) -> str:
        """从工具调用结果中提取文本

        优先取 content 数组中的 text 字段。

        参数:
            result: 工具调用结果

        返回:
            str: 结果文本
        """
        content = result.get("content", [])
        if isinstance(content, list):
            texts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = str(item.get("text", "")).strip()
                    if text:
                        texts.append(text)
            if texts:
                return "\n".join(texts)
        if "structuredContent" in result:
            return json.dumps(
                result["structuredContent"], ensure_ascii=False
            )
        return json.dumps(result, ensure_ascii=False)


class McpBridge:
    """MCP桥接管理器

    从JSON配置加载MCP服务器，发现远程工具并注册到工具注册表。
    按 server 名池化长连接子进程，调用失败自动重建连接重试。
    """

    def __init__(self) -> None:
        """初始化MCP桥接管理器"""
        self._servers: dict[str, McpServerConfig] = {}
        self._clients: dict[str, McpStdioClient] = {}
        self._lock = asyncio.Lock()

    def load_config(self, config_json: str) -> int:
        """从JSON字符串加载MCP服务器配置

        参数:
            config_json: JSON配置字符串

        返回:
            int: 加载的服务器数
        """
        if not config_json.strip():
            return 0
        configs = json.loads(config_json)
        if not isinstance(configs, list):
            return 0
        for item in configs:
            if not isinstance(item, dict):
                continue
            server = self._parse_server_config(item)
            if server:
                self._servers[server.name] = server
        return len(self._servers)

    @staticmethod
    def _parse_server_config(
        data: dict[str, Any]
    ) -> McpServerConfig | None:
        """解析单个MCP服务器配置

        对 command / args / tools / env 做严格类型校验，
        不合法时记录 warning 并跳过该服务器。

        参数:
            data: 配置字典

        返回:
            McpServerConfig | None: 服务器配置，校验失败返回 None
        """
        transport = str(data.get("transport", "stdio")).strip()
        if transport != "stdio":
            return None
        name = str(data.get("name", "")).strip()
        if not name:
            return None

        command = data.get("command")
        if not isinstance(command, str) or not command.strip():
            logger.warning(
                f"MCP服务器 {name} 的 command 必须为非空字符串，跳过",
                command="AI",
            )
            return None

        args = data.get("args", [])
        if not isinstance(args, list) or not all(
            isinstance(arg, str) for arg in args
        ):
            logger.warning(
                f"MCP服务器 {name} 的 args 必须为字符串列表，跳过",
                command="AI",
            )
            return None

        tools = data.get("tools", [])
        if not isinstance(tools, list):
            logger.warning(
                f"MCP服务器 {name} 的 tools 必须为列表，跳过",
                command="AI",
            )
            return None

        env = data.get("env", {})
        if not isinstance(env, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in env.items()
        ):
            logger.warning(
                f"MCP服务器 {name} 的 env 必须为字符串字典，跳过",
                command="AI",
            )
            return None

        return McpServerConfig(
            name=name,
            command=command.strip(),
            args=list(args),
            env=dict(env),
            tools=list(tools),
            timeout=int(data.get("timeout", _DEFAULT_TIMEOUT)),
        )

    async def register_tools(
        self, registry: ToolRegistry
    ) -> int:
        """注册所有MCP服务器的工具到注册表

        参数:
            registry: 工具注册表

        返回:
            int: 注册的工具数
        """
        registered = 0
        for server in self._servers.values():
            try:
                registered += await self._register_server_tools(
                    server, registry
                )
            except Exception as e:
                logger.warning(
                    f"MCP服务器 {server.name} 注册失败: {e}",
                    command="AI",
                    e=e,
                )
        logger.info(
            f"MCP工具注册完成: {registered}个工具",
            command="AI",
        )
        return registered

    async def _register_server_tools(
        self,
        server: McpServerConfig,
        registry: ToolRegistry,
    ) -> int:
        """注册单个MCP服务器的工具

        通过连接池获取长连接列出工具，注册完成后连接保留复用。

        参数:
            server: 服务器配置
            registry: 工具注册表

        返回:
            int: 注册的工具数
        """
        client = await self._get_client(server.name)
        tools = await asyncio.wait_for(
            client.list_tools(), timeout=server.timeout
        )

        registered = 0
        for tool_def in tools:
            tool_name = str(tool_def.get("name", "")).strip()
            if not tool_name:
                continue
            if server.tools and tool_name not in server.tools:
                continue
            full_name = f"mcp_{server.name}_{tool_name}"
            description = str(tool_def.get("description", ""))
            parameters = tool_def.get("inputSchema", {})

            async def _handler(
                _bridge: McpBridge = self,
                _server: McpServerConfig = server,
                _tool: str = tool_name,
                **kwargs: Any,
            ) -> str:
                """MCP工具调用handler"""
                return await _bridge.call_tool(
                    _server, _tool, kwargs
                )

            registry.register(
                AgentTool(
                    name=full_name,
                    description=f"[MCP] {description}",
                    parameters=parameters,
                    func=_handler,
                )
            )
            registered += 1
        return registered

    async def _get_client(self, server_name: str) -> McpStdioClient:
        """获取指定服务器的客户端长连接

        缓存连接仍存活则复用，否则关闭失效连接并重新启动。

        参数:
            server_name: 服务器名称

        返回:
            McpStdioClient: 可用客户端

        异常:
            KeyError: 服务器配置不存在
        """
        server = self._servers[server_name]
        async with self._lock:
            client = self._clients.get(server_name)
            if client is not None and client.alive:
                return client
            if client is not None:
                await client.close()
            client = await McpStdioClient(
                command=server.command,
                args=server.args,
                env=server.env,
            ).start()
            self._clients[server_name] = client
            return client

    async def _discard_client(self, server_name: str) -> None:
        """关闭并移除缓存的客户端连接

        参数:
            server_name: 服务器名称
        """
        async with self._lock:
            client = self._clients.pop(server_name, None)
        if client is not None:
            await client.close()

    async def call_tool(
        self,
        server: McpServerConfig,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        """调用MCP远程工具

        复用长连接执行调用，连接异常时丢弃连接、
        重建后重试一次，二次失败按原有异常路径向上抛出。

        参数:
            server: 服务器配置
            tool_name: 工具名
            arguments: 工具参数

        返回:
            str: 工具执行结果
        """
        client = await self._get_client(server.name)
        try:
            return await asyncio.wait_for(
                client.call_tool(tool_name, arguments),
                timeout=server.timeout,
            )
        except Exception:
            # 连接可能已损坏（进程退出/协议错误/超时），
            # 丢弃后重建一次并重试，二次失败向上抛出。
            await self._discard_client(server.name)
            client = await self._get_client(server.name)
            return await asyncio.wait_for(
                client.call_tool(tool_name, arguments),
                timeout=server.timeout,
            )

    async def close(self) -> None:
        """关闭所有缓存的客户端连接

        供插件关闭钩子调用，释放全部MCP子进程。
        """
        async with self._lock:
            clients = list(self._clients.values())
            self._clients.clear()
        for client in clients:
            await client.close()


mcp_bridge = McpBridge()
"""MCP桥接管理器单例"""
