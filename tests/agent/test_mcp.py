# tests/agent/test_mcp.py
from clawops.agent.mcp import MCPServerHTTP, MCPServerStdio


def test_mcp_http_creation():
    server = MCPServerHTTP("https://my-mcp-server.com")
    assert server.url == "https://my-mcp-server.com"


def test_mcp_stdio_creation():
    server = MCPServerStdio("npx @modelcontextprotocol/server-google")
    assert server.command == "npx @modelcontextprotocol/server-google"
