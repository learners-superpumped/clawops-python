from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from .._models import BaseModel


class TranscriptSegment(BaseModel):
    """전사 segment 한 덩어리 — 화자 분리와 타임스탬프 포함."""

    speaker: Literal["CUSTOMER", "AGENT"]
    start: float
    end: float
    text: str


class TranscriptStatus(BaseModel):
    """통화 전사 상태. 모든 필드는 status 에 따라 채워지는 것이 다름.

    - status="completed": call_id, segment_count, segments 채워짐
    - status="pending":   started_at 채워짐
    - status="failed":    stage, error 채워짐. stage="trigger" 는 시스템 레벨
                          실패로, POST 로 재시도 가능.
    - status="not_requested": 이외 필드 비어있음
    """

    status: Literal["completed", "pending", "failed", "not_requested"]
    call_id: Optional[str] = None
    segment_count: Optional[int] = None
    segments: Optional[List[TranscriptSegment]] = None
    started_at: Optional[datetime] = None
    stage: Optional[Literal["download", "runtime", "trigger"]] = None
    error: Optional[str] = None


class TranscriptRequestAccepted(BaseModel):
    """POST 요청이 accept 되어 Job 이 트리거된 상태 (202)."""

    status: Literal["pending"]
    call_id: str
