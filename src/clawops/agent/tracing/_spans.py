"""Span 생성 헬퍼.

opentelemetry-api 미설치 시 no-op context manager를 반환한다.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Generator

from . import _attributes as attr

log = logging.getLogger("clawops.agent")

try:
    from opentelemetry import trace
    _tracer = trace.get_tracer("clawops.agent")
except ImportError:
    _tracer = None


@contextmanager
def call_span(
    call_id: str,
    *,
    from_number: str = "",
    to_number: str = "",
) -> Generator[Any, None, None]:
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(
        "call",
        attributes={
            attr.CALL_ID: call_id,
            attr.CALL_FROM: from_number,
            attr.CALL_TO: to_number,
        },
    ) as span:
        yield span


@contextmanager
def mcp_connect_span(
    server_type: str,
    *,
    command: str = "",
    url: str = "",
) -> Generator[Any, None, None]:
    if _tracer is None:
        yield None
        return
    attributes: dict[str, Any] = {attr.MCP_SERVER_TYPE: server_type}
    if command:
        attributes[attr.MCP_SERVER_COMMAND] = command
    if url:
        attributes[attr.MCP_SERVER_URL] = url
    with _tracer.start_as_current_span("mcp.connect", attributes=attributes) as span:
        yield span


@contextmanager
def llm_session_span(
    model: str,
    *,
    voice: str = "",
) -> Generator[Any, None, None]:
    if _tracer is None:
        yield None
        return
    attributes: dict[str, Any] = {
        attr.GEN_AI_SYSTEM: "openai",
        attr.GEN_AI_REQUEST_MODEL: model,
    }
    if voice:
        attributes[attr.GEN_AI_REQUEST_VOICE] = voice
    with _tracer.start_as_current_span("llm.session", attributes=attributes) as span:
        yield span


@contextmanager
def llm_generation_span() -> Generator[Any, None, None]:
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span("llm.generation") as span:
        yield span


@contextmanager
def tool_call_span(
    name: str,
    source: str,
) -> Generator[Any, None, None]:
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(
        "tool.call",
        attributes={
            attr.TOOL_NAME: name,
            attr.TOOL_SOURCE: source,
        },
    ) as span:
        yield span


@contextmanager
def mcp_call_tool_span(
    tool_name: str,
) -> Generator[Any, None, None]:
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(
        "mcp.call_tool",
        attributes={attr.MCP_TOOL_NAME: tool_name},
    ) as span:
        yield span
