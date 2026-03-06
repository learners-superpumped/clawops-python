from __future__ import annotations

import pydantic
from pydantic import ConfigDict

from ._utils import to_camel_case


class BaseModel(pydantic.BaseModel):
    """ClawOps SDK의 모든 응답 모델의 베이스 클래스.

    - snake_case 필드 -> camelCase JSON alias 자동 생성
    - extra="allow"로 미래 API 필드 호환
    - populate_by_name=True로 snake_case/camelCase 양방향 접근
    """

    model_config = ConfigDict(
        extra="allow",
        alias_generator=to_camel_case,
        populate_by_name=True,
    )
