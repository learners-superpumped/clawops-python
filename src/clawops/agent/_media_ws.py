"""Media WebSocket: per-call 오디오 스트림.

ClawOps VoiceML Stream 프로토콜을 구현한다:
connected -> start -> media (PCM16 8kHz base64) -> mark -> stop
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any, Callable, Awaitable

import aiohttp

log = logging.getLogger("clawops.agent")


def parse_start_event(data: dict[str, Any]) -> dict[str, Any]:
    start = data["start"]
    fmt = start.get("mediaFormat", {})
    return {
        "stream_id": start["streamId"],
        "call_id": start["callId"],
        "account_id": start.get("accountId", ""),
        "sample_rate": fmt.get("sampleRate", 8000),
    }


def parse_media_event(data: dict[str, Any]) -> dict[str, Any]:
    media = data["media"]
    return {
        "pcm16": base64.b64decode(media["payload"]),
        "timestamp": int(media.get("timestamp", 0)),
    }


def build_media_response(pcm16: bytes) -> dict[str, Any]:
    return {
        "event": "media",
        "media": {
            "payload": base64.b64encode(pcm16).decode(),
        },
    }


class MediaWebSocket:
    def __init__(
        self,
        *,
        url: str,
        api_key: str,
        on_audio: Callable[[bytes, int], Awaitable[None]],
        on_start: Callable[[dict[str, Any]], Awaitable[None]],
        on_stop: Callable[[], Awaitable[None]],
        on_mark: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._on_audio = on_audio
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_mark = on_mark
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._send_task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(
            self._url,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        log.info(f"Media WS connected: {self._url}")
        self._send_task = asyncio.create_task(self._send_loop())

        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    event = data.get("event")

                    if event == "start":
                        await self._on_start(parse_start_event(data))
                    elif event == "media":
                        parsed = parse_media_event(data)
                        await self._on_audio(parsed["pcm16"], parsed["timestamp"])
                    elif event == "stop":
                        await self._on_stop()
                        break
                    elif event == "mark":
                        if self._on_mark and "mark" in data:
                            await self._on_mark(data["mark"].get("name", ""))
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                    break
        finally:
            await self.close()

    async def send_audio(self, pcm16: bytes) -> None:
        self._audio_queue.put_nowait(pcm16)

    async def send_clear(self) -> None:
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        if self._ws and not self._ws.closed:
            await self._ws.send_str(json.dumps({"event": "clear"}))

    async def send_mark(self, name: str) -> None:
        if self._ws and not self._ws.closed:
            await self._ws.send_str(json.dumps({
                "event": "mark",
                "mark": {"name": name},
            }))

    async def _send_loop(self) -> None:
        """오디오 청크를 플랫폼으로 전송 (pacing은 플랫폼이 처리)."""
        try:
            while True:
                chunk = await self._audio_queue.get()
                if chunk is None:
                    break
                if self._ws and not self._ws.closed:
                    msg = build_media_response(chunk)
                    await self._ws.send_str(json.dumps(msg))
        except asyncio.CancelledError:
            pass

    async def close(self) -> None:
        self._audio_queue.put_nowait(None)
        if self._send_task and not self._send_task.done():
            self._send_task.cancel()
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session:
            await self._session.close()
