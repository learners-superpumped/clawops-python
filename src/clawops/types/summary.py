from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Literal, Optional

from .._models import BaseModel


class SummaryStatus(BaseModel):
    """통화 요약 상태. 모든 필드는 status 에 따라 채워지는 것이 다름.

    - status="completed": call_id, result_json, provider, model, prompt_version,
                          schema_version, updated_at 채워짐
    - status="pending":   이외 필드 비어있음
    - status="failed":    failed_reason 채워짐
    - status="not_requested": 통화는 있지만 요약 row 가 아직 없음
    """

    status: Literal["completed", "pending", "failed", "not_requested"]
    call_id: Optional[str] = None
    result_json: Optional[Dict[str, Any]] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    schema_version: Optional[str] = None
    failed_reason: Optional[str] = None
    updated_at: Optional[datetime] = None
