"""MCPClient — MCP 서버와의 연결을 관리하는 런타임 클라이언트."""
from __future__ import annotations

import asyncio
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

    async with 블록 대신 백그라운드 Task에서 context manager를 유지하여
    anyio cancel scope 문제를 회피한다.
    """

    def __init__(self, server: MCPServerStdio | MCPServerHTTP) -> None:
        self._server = server
        self._session: Any | None = None
        self._tools: list[dict] = []
        self._tool_names: set[str] = set()
        self._ready = asyncio.Event()
        self._shutdown = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._error: Exception | None = None

    async def connect(self) -> None:
        """MCP 서버에 연결하고 사용 가능한 도구 목록을 가져온다."""
        if not _HAS_MCP:
            raise AgentError(
                "MCP 서버를 사용하려면 pip install clawops[mcp] 를 실행하세요."
            )

        self._task = asyncio.create_task(self._run())
        await self._ready.wait()

        if self._error:
            raise self._error

    async def _run(self) -> None:
        """백그라운드 Task: async with로 context manager를 유지한다."""
        try:
            if isinstance(self._server, MCPServerStdio):
                log.debug("MCP connecting (stdio): %s %s", self._server.command, self._server.args)
                await self._run_stdio()
            else:
                log.debug("MCP connecting (http): %s", self._server.url)
                await self._run_http()
        except Exception as e:
            self._error = AgentError(f"MCP 서버 연결 실패: {e}")
            self._ready.set()

    async def _run_stdio(self) -> None:
        params = StdioServerParameters(
            command=self._server.command,
            args=self._server.args,
            env=self._server.env if self._server.env else None,
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                await self._on_connected(session)
                await self._shutdown.wait()

    async def _run_http(self) -> None:
        async with streamable_http_client(
            self._server.url,
            headers=self._server.headers if self._server.headers else None,
        ) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                await self._on_connected(session)
                await self._shutdown.wait()

    async def _on_connected(self, session: Any) -> None:
        self._session = session
        result = await session.list_tools()
        self._tools = [_mcp_tool_to_openai(t) for t in result.tools]
        self._tool_names = {t.name for t in result.tools}
        log.info("MCP 서버 연결 완료: %d개 도구 발견", len(self._tools))
        log.debug("MCP tools: %s", list(self._tool_names))
        self._ready.set()

    async def close(self) -> None:
        """연결을 종료하고 리소스를 정리한다."""
        log.debug("MCP closing: %s", self._server)
        self._shutdown.set()
        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, Exception):
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
        self._session = None
        self._tools = []
        self._tool_names = set()

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
