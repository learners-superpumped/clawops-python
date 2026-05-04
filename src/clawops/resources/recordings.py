from __future__ import annotations

import re
from urllib.parse import unquote

import httpx

from .._resource import AsyncAPIResource, SyncAPIResource
from ..types.recording import RecordingDownload


_FILENAME_STAR_RE = re.compile(r"filename\*=(?:[\w-]+'[^']*')?([^;]+)", re.IGNORECASE)
_FILENAME_QUOTED_RE = re.compile(r'filename="([^"]+)"', re.IGNORECASE)
_FILENAME_BARE_RE = re.compile(r"filename=([^;]+)", re.IGNORECASE)


def _parse_filename(disposition: str | None) -> str | None:
    """RFC 6266 Content-Disposition 파싱. filename*= 가 있으면 우선."""
    if not disposition:
        return None
    m = _FILENAME_STAR_RE.search(disposition)
    if m:
        try:
            return unquote(m.group(1).strip())
        except Exception:
            pass
    m = _FILENAME_QUOTED_RE.search(disposition)
    if m:
        return m.group(1).strip()
    m = _FILENAME_BARE_RE.search(disposition)
    return m.group(1).strip() if m else None


def _to_download(response: httpx.Response) -> RecordingDownload:
    return RecordingDownload(
        data=response.content,
        content_type=response.headers.get("content-type", "audio/wav"),
        filename=_parse_filename(response.headers.get("content-disposition")),
    )


class Recordings(SyncAPIResource):
    """통화 녹음(Recordings) 리소스.

    콘솔과 동일한 서버측 MixMonitor 원본(WAV PCM 16bit mono 8kHz) 다운로드.
    """

    def download(
        self,
        call_id: str,
        *,
        extra_headers: dict[str, str] | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> RecordingDownload:
        """통화 녹음을 다운로드합니다.

        Args:
            call_id: 통화 ID (예: 'CAabcdef1234567890').

        Returns:
            RecordingDownload — data(bytes), content_type, filename.

        Raises:
            NotFoundError (404): 통화 없음 또는 녹음 없음(``recording_url`` null).
            PermissionDeniedError (403): accountId 불일치.
        """
        response = self._client._get_raw(
            f"{self._base_path}/recordings/{call_id}",
            extra_headers=extra_headers,
            timeout=timeout,
        )
        return _to_download(response)


class AsyncRecordings(AsyncAPIResource):
    async def download(
        self,
        call_id: str,
        *,
        extra_headers: dict[str, str] | None = None,
        timeout: float | httpx.Timeout | None = None,
    ) -> RecordingDownload:
        response = await self._client._get_raw(
            f"{self._base_path}/recordings/{call_id}",
            extra_headers=extra_headers,
            timeout=timeout,
        )
        return _to_download(response)
