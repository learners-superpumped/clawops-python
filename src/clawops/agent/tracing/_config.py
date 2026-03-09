"""TracingConfig — tracing 설정."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TracingConfig:
    enabled: bool = True
    service_name: str = "clawops-agent"
    tracer_provider: Any | None = None
