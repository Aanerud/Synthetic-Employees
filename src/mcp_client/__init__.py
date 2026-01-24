"""MCP Client module for Synthetic Employees.

Provides two client implementations:

- MCPStdioClient: Stdio-based client (RECOMMENDED)
  Uses the same transport as Claude Desktop for 1:1 parity.
  Spawns mcp-adapter.cjs and communicates via stdin/stdout.

- MCPClient: HTTP-based client (legacy)
  Direct HTTP communication with the MCP server.
  Kept for backwards compatibility.
"""

from .client import MCPClient, MCPClientError, MCPAuthenticationError, MCPServerError
from .stdio_client import (
    MCPStdioClient,
    MCPStdioError,
    MCPStdioAuthenticationError,
    MCPStdioServerError,
    MCPStdioConnectionError,
)

__all__ = [
    # Stdio client (recommended)
    "MCPStdioClient",
    "MCPStdioError",
    "MCPStdioAuthenticationError",
    "MCPStdioServerError",
    "MCPStdioConnectionError",
    # HTTP client (legacy)
    "MCPClient",
    "MCPClientError",
    "MCPAuthenticationError",
    "MCPServerError",
]
