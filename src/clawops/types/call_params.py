from __future__ import annotations

from typing import Annotated, Literal, Union

from typing_extensions import Required, TypedDict

from .._utils import PropertyInfo

# ── AI Completion 타입 ───────────────────────────────────────────────────────

AIProvider = Union[Literal["openai", "gemini"], str]
"""지원 AI 제공자. 자유 입력도 허용."""

OpenAIRealtimeModel = Union[Literal["gpt-realtime-1.5", "gpt-4o-mini-realtime"], str]
"""OpenAI Realtime 모델. 자유 입력도 허용."""

GeminiRealtimeModel = Union[Literal["gemini-2.5-flash-native-audio-preview"], str]
"""Gemini Realtime 모델. 자유 입력도 허용."""

AIVoice = Union[
    Literal[
        "alloy", "ash", "ballad", "coral", "echo",
        "fable", "marin", "sage", "shimmer", "verse",
    ],
    str,
]
"""AI 음성 ID. 자유 입력도 허용."""


class AIConfigParam(TypedDict, total=False):
    """AI Completion 모드 설정."""

    provider: Required[Annotated[AIProvider, PropertyInfo(alias="Provider")]]
    """AI 제공자. ``'openai'`` 또는 ``'gemini'``."""

    model: Required[Annotated[str, PropertyInfo(alias="Model")]]
    """사용할 AI 모델명. 예: ``'gpt-realtime-1.5'``, ``'gemini-2.5-flash-native-audio-preview'``."""

    api_key: Required[Annotated[str, PropertyInfo(alias="ApiKey")]]
    """AI 제공자의 API 키."""

    voice: Annotated[AIVoice, PropertyInfo(alias="Voice")]
    """음성 ID (기본값: ``'marin'``). alloy, ash, ballad, coral, echo, fable, marin, sage, shimmer, verse 등."""

    language: Annotated[str, PropertyInfo(alias="Language")]
    """언어 코드 (기본값: ``'ko'``)."""

    messages: Annotated[list[dict[str, str]], PropertyInfo(alias="Messages")]
    """초기 메시지 (system prompt 등). OpenAI Chat Completions 형식.

    예: ``[{"role": "system", "content": "당신은 예약 확인 AI입니다."}]``
    """

    tools: Annotated[list[dict], PropertyInfo(alias="Tools")]
    """Function calling 도구 정의. OpenAI 형식."""

    greeting: Annotated[bool, PropertyInfo(alias="Greeting")]
    """통화 시작 시 AI가 먼저 인사할지 여부 (기본값: ``True``)."""

    turn_detection: Annotated[dict, PropertyInfo(alias="TurnDetection")]
    """턴 감지 설정 (기본값: semantic_vad medium)."""


# ── Call API 파라미터 ────────────────────────────────────────────────────────

class CallCreateParams(TypedDict, total=False):
    """발신 전화 생성 요청 파라미터.

    **3가지 모드:**

    - **VoiceML 모드**: ``url``을 지정하면 VoiceML로 통화를 제어합니다.
    - **Agent 모드**: ``url``과 ``ai`` 모두 생략하면 Agent SDK로 통화가 연결됩니다.
    - **AI Completion 모드**: ``ai``를 지정하면 AI가 직접 통화를 처리합니다.
    """

    to: Required[Annotated[str, PropertyInfo(alias="To")]]
    """수신 대상. 전화번호(PSTN) 또는 sip: URI(내선)."""

    from_: Required[Annotated[str, PropertyInfo(alias="From")]]
    """발신 번호. 계정에 등록된 번호여야 합니다."""

    url: Annotated[str, PropertyInfo(alias="Url")]
    """통화 연결 시 VoiceML 명령을 반환할 URL. AI 모드와 동시 사용 불가."""

    ai: Annotated[AIConfigParam, PropertyInfo(alias="AI")]
    """AI Completion 모드 설정. 이 필드가 있으면 AI가 통화를 처리합니다."""

    status_callback: Annotated[str, PropertyInfo(alias="StatusCallback")]
    """통화 상태 변경 시 POST 요청을 받을 콜백 URL."""

    status_callback_event: Annotated[str, PropertyInfo(alias="StatusCallbackEvent")]
    """수신할 상태 이벤트 목록 (공백 구분)."""

    timeout: Annotated[int, PropertyInfo(alias="Timeout")]
    """발신 타임아웃 (초). 기본값: 60."""


class CallListParams(TypedDict, total=False):
    """통화 목록 조회 요청 파라미터."""

    status: Literal["queued", "ringing", "in-progress", "completed", "failed"]
    """통화 상태로 필터링."""

    page: int
    """페이지 번호 (0부터 시작)."""

    page_size: Annotated[int, PropertyInfo(alias="pageSize")]
    """페이지당 항목 수 (기본 20, 최대 100)."""


class CallUpdateParams(TypedDict, total=False):
    """통화 제어 (종료) 요청 파라미터."""

    status: Required[Annotated[Literal["completed"], PropertyInfo(alias="Status")]]
    """변경할 통화 상태. 현재 'completed'만 지원."""
