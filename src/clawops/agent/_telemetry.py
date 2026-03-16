"""Call telemetry: SDK info and per-call metrics."""

from __future__ import annotations

import platform
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from clawops._version import __version__

MAX_ERRORS = 20
MAX_ERROR_MESSAGE_LENGTH = 200


def get_sdk_info() -> dict[str, str]:
    return {
        "name": "clawops-python",
        "version": __version__,
        "runtime": f"python/{sys.version.split()[0]}",
        "os": f"{sys.platform}/{platform.machine()}",
    }


@dataclass
class CallMetrics:
    first_response_ms: int | None = None
    turn_count: int = 0
    tool_call_count: int = 0
    tool_error_count: int = 0
    barge_in_count: int = 0
    end_reason: str | None = None
    errors: list[dict[str, str]] = field(default_factory=list)

    _first_response_sent: bool = field(default=False, repr=False)
    _start_time_ms: float = field(default=0, repr=False)

    def record_first_response(self) -> None:
        if not self._first_response_sent:
            self._first_response_sent = True
            self.first_response_ms = int(time.time() * 1000 - self._start_time_ms)

    def record_turn(self) -> None:
        self.turn_count += 1

    def record_tool_call(self) -> None:
        self.tool_call_count += 1

    def record_tool_error(self, err: Exception) -> None:
        self.tool_error_count += 1
        if len(self.errors) < MAX_ERRORS:
            self.errors.append({
                "type": type(err).__name__,
                "message": str(err)[:MAX_ERROR_MESSAGE_LENGTH],
            })

    def record_barge_in(self) -> None:
        self.barge_in_count += 1

    def record_end_reason(self, reason: str) -> None:
        self.end_reason = reason

    def to_dict(self) -> dict[str, Any]:
        return {
            "firstResponseMs": self.first_response_ms,
            "turnCount": self.turn_count,
            "toolCallCount": self.tool_call_count,
            "toolErrorCount": self.tool_error_count,
            "bargeInCount": self.barge_in_count,
            "endReason": self.end_reason,
            "errors": self.errors,
        }
