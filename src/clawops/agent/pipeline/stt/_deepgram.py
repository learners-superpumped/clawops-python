"""Deepgram WebSocket 스트리밍 STT."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import AsyncIterator

import aiohttp

from .._base import SpeechEvent

log = logging.getLogger("clawops.agent.pipeline")

DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"


class DeepgramSTT:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "nova-3",
        language: str = "ko",
        sample_rate: int = 16000,
        encoding: str = "linear16",
        punctuate: bool = True,
        interim_results: bool = True,
        endpointing: int = 300,
        utterance_end_ms: int = 1000,
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("DEEPGRAM_API_KEY", "")
        self._api_key = api_key
        self._model = model
        self._language = language
        self._sample_rate = sample_rate
        self._encoding = encoding
        self._punctuate = punctuate
        self._interim_results = interim_results
        self._endpointing = endpointing
        self._utterance_end_ms = utterance_end_ms

    async def transcribe(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[SpeechEvent]:
        """오디오 스트림(PCM16) → SpeechEvent 스트림."""
        params = (
            f"model={self._model}&language={self._language}"
            f"&sample_rate={self._sample_rate}&encoding={self._encoding}"
            f"&channels=1&punctuate={str(self._punctuate).lower()}"
            f"&interim_results={str(self._interim_results).lower()}"
            f"&endpointing={self._endpointing}"
            f"&utterance_end_ms={self._utterance_end_ms}"
        )
        url = f"{DEEPGRAM_WS_URL}?{params}"

        session = aiohttp.ClientSession()
        try:
            ws = await session.ws_connect(
                url,
                headers={"Authorization": f"Token {self._api_key}"},
            )
            log.info("Deepgram STT connected")

            event_queue: asyncio.Queue[SpeechEvent | None] = asyncio.Queue()
            speech_notified = False

            async def send_audio() -> None:
                try:
                    async for chunk in audio_stream:
                        if ws.closed:
                            break
                        await ws.send_bytes(chunk)
                except Exception as e:
                    log.error(f"Deepgram send error: {e}")
                finally:
                    if not ws.closed:
                        await ws.send_bytes(b"")

            async def recv_results() -> None:
                nonlocal speech_notified
                try:
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            msg_type = data.get("type", "")

                            if msg_type == "SpeechStarted":
                                if not speech_notified:
                                    speech_notified = True
                                    log.info("Speech started (VAD)")
                                    await event_queue.put(
                                        SpeechEvent(type="interim", transcript="")
                                    )
                                continue

                            if msg_type == "Results":
                                is_final = data.get("is_final", False)
                                speech_final = data.get("speech_final", False)
                                channel = data.get("channel", {})
                                alts = channel.get("alternatives", [])
                                transcript = alts[0].get("transcript", "") if alts else ""

                                # interim result → barge-in 이벤트 (발화 시작 시 1회)
                                if transcript and not is_final and not speech_notified:
                                    speech_notified = True
                                    log.info(f"Speech detected (interim): {transcript[:40]}")
                                    await event_queue.put(
                                        SpeechEvent(type="interim", transcript=transcript)
                                    )

                                # final result → 확정 transcript
                                if transcript and is_final and speech_final:
                                    speech_notified = False
                                    await event_queue.put(
                                        SpeechEvent(type="final", transcript=transcript)
                                    )

                        elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                            break
                except Exception as e:
                    log.error(f"Deepgram recv error: {e}")
                finally:
                    await event_queue.put(None)

            send_task = asyncio.create_task(send_audio())
            recv_task = asyncio.create_task(recv_results())

            try:
                while True:
                    event = await event_queue.get()
                    if event is None:
                        break
                    yield event
            finally:
                send_task.cancel()
                recv_task.cancel()
                if not ws.closed:
                    await ws.close()
        finally:
            await session.close()
