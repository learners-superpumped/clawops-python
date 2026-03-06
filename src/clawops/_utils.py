from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def to_camel_case(snake: str) -> str:
    """snake_case를 camelCase로 변환합니다.

    trailing underscore(Python 예약어 회피용)는 제거합니다.
    예: 'from_' -> 'from', 'account_id' -> 'accountId'
    """
    if snake.endswith("_"):
        snake = snake[:-1]
    parts = snake.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


def strip_not_given(data: dict[str, Any]) -> dict[str, Any]:
    """None인 값을 제거하여 API에 불필요한 필드를 보내지 않습니다."""
    return {k: v for k, v in data.items() if v is not None}


@dataclass
class PropertyInfo:
    """TypedDict 필드에 alias 정보를 부여하기 위한 메타데이터."""
    alias: str
