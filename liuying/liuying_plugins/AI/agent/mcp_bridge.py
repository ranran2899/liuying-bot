"""MCP（Model Context Protocol）桥接

实现 JSON-RPC 2.0 over stdio 协议客户端，支持通过子进程调用 MCP 服务器。
从 JSON 配置加载 MCP 服务器定义，自动发现并注册远程工具。

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

    async def __aenter__(self) -> Self:
        """启动MCP服务器子进程"""
        self._proc = await asyncio.create_subprocess_exec(
            self._command,
            *self._args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._env,
        )
        await self.initialize()
        return self

    async def __aexit__(
        self, *exc: object
    ) -> None:
        """终止MCP服务器子进程"""
        if self._proc is None:
            return
        self._proc.kill()
        await self._proc.wait()
        self._proc = None

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

        参数:
            method: 方法名
            params: 参数

        返回:
            dict: 响应结果
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
        response = await self._read_message()
        data = json.loads(response)
        if data.get("id") != req_id:
            raise RuntimeError(
                f"MCP响应ID不匹配: 期望{req_id}, 得到{data.get('id')}"
            )
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
    """

    def __init__(self) -> None:
        """初始化MCP桥接管理器"""
        self._servers: dict[str, McpServerConfig] = {}

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

        参数:
            data: 配置字典

        返回:
            McpServerConfig | None: 服务器配置
        """
        transport = str(data.get("transport", "stdio")).strip()
        if transport != "stdio":
            return None
        name = str(data.get("name", "")).strip()
        command = str(data.get("command", "")).strip()
        if not name or not command:
            return None
        return McpServerConfig(
            name=name,
            command=command,
            args=list(data.get("args", [])),
            env=dict(data.get("env", {})),
            tools=list(data.get("tools", [])),
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

        参数:
            server: 服务器配置
            registry: 工具注册表

        返回:
            int: 注册的工具数
        """
        async with McpStdioClient(
            command=server.command,
            args=server.args,
            env=server.env,
        ) as client:
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
                _server: McpServerConfig = server,
                _tool: str = tool_name,
                **kwargs: Any,
            ) -> str:
                """MCP工具调用handler"""
                return await mcp_bridge.call_tool(
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

    async def call_tool(
        self,
        server: McpServerConfig,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        """调用MCP远程工具

        参数:
            server: 服务器配置
            tool_name: 工具名
            arguments: 工具参数

        返回:
            str: 工具执行结果
        """
        async with McpStdioClient(
            command=server.command,
            args=server.args,
            env=server.env,
        ) as client:
            return await asyncio.wait_for(
                client.call_tool(tool_name, arguments),
                timeout=server.timeout,
            )


mcp_bridge = McpBridge()
"""MCP桥接管理器单例"""
