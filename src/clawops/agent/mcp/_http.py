"""HTTP/SSE 기반 MCP 서버 설정. 실제 프로토콜은 pip install clawops[mcp] 시 활성화."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MCPServerHTTP:
    url: str
    headers: dict[str, str] = field(default_factory=dict)
