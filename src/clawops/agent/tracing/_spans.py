"""Span 생성 헬퍼.

opentelemetry-api 미설치 시 no-op context manager를 반환한다.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Generator, TYPE_CHECKING

from . import _attributes as attr

if TYPE_CHECKING:
    from ._config import TracingConfig

log = logging.getLogger("clawops.agent")

_enabled: bool = False
_tracer: Any | None = None

try:
    from opentelemetry import trace as _otel_trace
    _has_otel = True
except ImportError:
    _otel_trace = None  # type: ignore[assignment]
    _has_otel = False


def setup_tracing(config: TracingConfig) -> None:
    """TracingConfig를 기반으로 모듈 수준 tracing 상태를 설정한다."""
    global _enabled, _tracer

    if not config.enabled or not _has_otel:
        _enabled = False
        _tracer = None
        return

    _enabled = True
    if config.tracer_provider is not None:
        _tracer = config.tracer_provider.get_tracer("clawops.agent")
    else:
        _tracer = _otel_trace.get_tracer("clawops.agent")


@contextmanager
def call_span(
    call_id: str,
    *,
    from_number: str = "",
    to_number: str = "",
) -> Generator[Any, None, None]:
    if not _enabled or _tracer is None:
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
    if not _enabled or _tracer is None:
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
    system: str = "openai",
    voice: str = "",
) -> Generator[Any, None, None]:
    if not _enabled or _tracer is None:
        yield None
        return
    attributes: dict[str, Any] = {
        attr.GEN_AI_SYSTEM: system,
        attr.GEN_AI_REQUEST_MODEL: model,
    }
    if voice:
        attributes[attr.GEN_AI_REQUEST_VOICE] = voice
    with _tracer.start_as_current_span("llm.session", attributes=attributes) as span:
        yield span


@contextmanager
def llm_generation_span() -> Generator[Any, None, None]:
    if not _enabled or _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span("llm.generation") as span:
        yield span


@contextmanager
def tool_call_span(
    name: str,
    source: str,
) -> Generator[Any, None, None]:
    if not _enabled or _tracer is None:
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
    if not _enabled or _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(
        "mcp.call_tool",
        attributes={attr.MCP_TOOL_NAME: tool_name},
    ) as span:
        yield span
