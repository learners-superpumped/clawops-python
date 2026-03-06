"""MCPClient — MCP 서버와의 연결을 관리하는 런타임 클라이언트."""
from __future__ import annotations

import logging
from typing import Any

from ._http import MCPServerHTTP
from ._stdio import MCPServerStdio
from ..._exceptions import AgentError

log = logging.getLogger("clawops.agent")

try:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from mcp.client.streamable_http import streamable_http_client

    _HAS_MCP = True
except ImportError:
    _HAS_MCP = False


async def _connect_stdio(server: MCPServerStdio) -> tuple[Any, list[Any]]:
    """Stdio 기반 MCP 서버에 연결하고 (session, cleanup_list)를 반환한다."""
    params = StdioServerParameters(
        command=server.command,
        args=server.args,
        env=server.env if server.env else None,
    )

    cm_stdio = stdio_client(params)
    read_write = await cm_stdio.__aenter__()
    read_stream, write_stream = read_write

    cm_session = ClientSession(read_stream, write_stream)
    session = await cm_session.__aenter__()
    await session.initialize()

    # cleanup_list: 역순으로 __aexit__ 호출해야 함
    return session, [cm_session, cm_stdio]


async def _connect_http(server: MCPServerHTTP) -> tuple[Any, list[Any]]:
    """HTTP/SSE 기반 MCP 서버에 연결하고 (session, cleanup_list)를 반환한다."""
    cm_http = streamable_http_client(server.url, headers=server.headers)
    read_write = await cm_http.__aenter__()
    read_stream, write_stream, _ = read_write

    cm_session = ClientSession(read_stream, write_stream)
    session = await cm_session.__aenter__()
    await session.initialize()

    return session, [cm_session, cm_http]


def _mcp_tool_to_openai(tool: Any) -> dict:
    """MCP tool 스키마를 OpenAI Realtime function tool 형식으로 변환한다."""
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description or "",
        "parameters": tool.inputSchema or {"type": "object", "properties": {}},
    }


class MCPClient:
    """MCP 서버와의 연결을 관리하는 런타임 클라이언트.

    사용 예시::

        client = MCPClient(MCPServerStdio("npx", args=["@mcp/server"]))
        await client.connect()
        tools = client.tools        # OpenAI function tool 형식
        result = await client.call_tool("get_weather", {"city": "Seoul"})
        await client.close()
    """

    def __init__(self, server: MCPServerStdio | MCPServerHTTP) -> None:
        self._server = server
        self._session: Any | None = None
        self._tools: list[dict] = []
        self._tool_names: set[str] = set()
        self._cleanup_list: list[Any] = []

    async def connect(self) -> None:
        """MCP 서버에 연결하고 사용 가능한 도구 목록을 가져온다."""
        if not _HAS_MCP:
            raise AgentError(
                "MCP 서버를 사용하려면 pip install clawops[mcp] 를 실행하세요."
            )

        if isinstance(self._server, MCPServerStdio):
            log.debug("MCP connecting (stdio): %s %s", self._server.command, self._server.args)
            session, cleanup = await _connect_stdio(self._server)
        else:
            log.debug("MCP connecting (http): %s", self._server.url)
            session, cleanup = await _connect_http(self._server)

        self._session = session
        self._cleanup_list = cleanup

        result = await self._session.list_tools()
        self._tools = [_mcp_tool_to_openai(t) for t in result.tools]
        self._tool_names = {t.name for t in result.tools}

        log.info("MCP 서버 연결 완료: %d개 도구 발견", len(self._tools))
        log.debug("MCP tools: %s", list(self._tool_names))

    async def close(self) -> None:
        """연결을 종료하고 리소스를 정리한다."""
        log.debug("MCP closing: %s", self._server)
        for cm in self._cleanup_list:
            try:
                await cm.__aexit__(None, None, None)
            except Exception:
                log.debug("MCP cleanup 중 예외 발생", exc_info=True)

        self._session = None
        self._tools = []
        self._tool_names = set()
        self._cleanup_list = []

    @property
    def tools(self) -> list[dict]:
        """OpenAI function tool 형식의 도구 목록."""
        return list(self._tools)

    def has_tool(self, name: str) -> bool:
        """주어진 이름의 도구가 있는지 확인한다."""
        return name in self._tool_names

    async def call_tool(self, name: str, arguments: dict) -> str:
        """MCP 도구를 호출하고 결과를 문자열로 반환한다."""
        assert self._session is not None, "connect()를 먼저 호출하세요."
        log.debug("MCP call_tool: %s(%s)", name, arguments)

        result = await self._session.call_tool(name, arguments=arguments)
        texts = [
            block.text for block in result.content if block.type == "text"
        ]
        output = "\n".join(texts)

        if result.isError:
            return f"MCP Error: {output}"
        return output
