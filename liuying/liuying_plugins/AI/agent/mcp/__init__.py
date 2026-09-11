"""MCP 桥接子包

通过子进程桥接 MCP（Model Context Protocol）服务器，
自动发现并注册远程工具到 Agent 工具注册表。
"""

from .bridge import McpBridge, McpServerConfig, McpStdioClient, mcp_bridge

__all__ = [
    "McpBridge",
    "McpServerConfig",
    "McpStdioClient",
    "mcp_bridge",
]
