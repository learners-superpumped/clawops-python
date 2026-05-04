from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RecordingDownload:
    """녹음 다운로드 결과.

    Attributes:
        data: WAV 바이너리 데이터 (PCM 16bit mono 8kHz).
        content_type: 응답 Content-Type (예: 'audio/wav').
        filename: Content-Disposition 에서 파싱한 파일명. 없으면 None.
    """

    data: bytes
    content_type: str
    filename: str | None
