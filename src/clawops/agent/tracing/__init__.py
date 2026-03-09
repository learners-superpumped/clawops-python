"""ClawOps Agent OpenTelemetry tracing."""

from ._config import TracingConfig
from ._spans import setup_tracing

__all__ = ["TracingConfig", "setup_tracing"]
