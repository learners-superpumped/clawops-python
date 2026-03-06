"""Stdio 기반 MCP 서버 설정."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MCPServerStdio:
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
