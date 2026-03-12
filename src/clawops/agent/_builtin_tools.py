"""Built-in tool 정의 및 선택 상수."""

from __future__ import annotations

from enum import StrEnum


class BuiltinTool(StrEnum):
    """Agent가 기본 제공하는 내장 도구.

    개별 도구를 리스트로 전달하거나, ALL / NONE 상수를 사용할 수 있습니다.
    """

    HANG_UP = "hang_up"
    COLLECT_DTMF = "collect_dtmf"
    SEND_DTMF = "send_dtmf"

    ALL = "all"
    NONE = "none"


def resolve_builtin_tools(
    value: BuiltinTool | list[BuiltinTool],
) -> set[BuiltinTool]:
    """사용자 입력을 실제 도구 set으로 변환."""
    if isinstance(value, BuiltinTool):
        if value == BuiltinTool.ALL:
            return {BuiltinTool.HANG_UP, BuiltinTool.COLLECT_DTMF, BuiltinTool.SEND_DTMF}
        if value == BuiltinTool.NONE:
            return set()
        return {value}
    return set(value) - {BuiltinTool.ALL, BuiltinTool.NONE}
