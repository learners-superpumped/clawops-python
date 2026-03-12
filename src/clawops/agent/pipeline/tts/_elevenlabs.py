"""ElevenLabs WebSocket 스트리밍 TTS."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from typing import AsyncIterator

import aiohttp

log = logging.getLogger("clawops.agent.pipeline")

ELEVENLABS_WS_URL = "wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input"


class ElevenLabsTTS:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        voice_id: str = "EXAVITQu4vr4xnSDxMaL",  # Rachel
        model: str = "eleven_flash_v2_5",
        output_format: str = "pcm_24000",
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        language_code: str = "ko",
    ) -> None:
        if api_key is None:
            api_key = os.environ.get("ELEVENLABS_API_KEY", "")
        self._api_key = api_key
        self._voice_id = voice_id
        self._model = model
        self._output_format = output_format
        self._stability = stability
        self._similarity_boost = similarity_boost
        self._language_code = language_code

    @property
    def sample_rate(self) -> int:
        """output_format에서 sample rate 추출."""
        parts = self._output_format.split("_")
        if len(parts) >= 2 and parts[-1].isdigit():
            return int(parts[-1])
        return 24000

    async def synthesize(self, text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
        """텍스트 스트림 → PCM 오디오 스트림."""
        url = ELEVENLABS_WS_URL.format(voice_id=self._voice_id)
        params = f"model_id={self._model}&output_format={self._output_format}"
        full_url = f"{url}?{params}"

        session = aiohttp.ClientSession()
        try:
            ws = await session.ws_connect(
                full_url,
                headers={"xi-api-key": self._api_key},
            )
            log.info("ElevenLabs TTS connected")

            audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()

            # BOS (Beginning of Stream)
            await ws.send_str(json.dumps({
                "text": " ",
                "voice_settings": {
                    "stability": self._stability,
                    "similarity_boost": self._similarity_boost,
                },
                "generation_config": {
                    "chunk_length_schedule": [120, 160, 250, 290],
                },
                "xi_api_key": self._api_key,
            }))

            async def send_text() -> None:
                try:
                    async for text in text_stream:
                        if ws.closed:
                            log.warning("ElevenLabs WS closed before sending text")
                            break
                        log.info(f"ElevenLabs sending text: {text[:60]}")
                        await ws.send_str(json.dumps({"text": text}))
                except Exception as e:
                    log.error(f"ElevenLabs send error: {e}")
                finally:
                    if not ws.closed:
                        log.info("ElevenLabs sending EOS")
                        await ws.send_str(json.dumps({"text": ""}))
                    log.info("ElevenLabs send_text done")

            async def recv_audio() -> None:
                try:
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            if "audio" in data and data["audio"]:
                                audio = base64.b64decode(data["audio"])
                                log.info(f"ElevenLabs recv audio: {len(audio)} bytes")
                                await audio_queue.put(audio)
                            else:
                                log.debug(f"ElevenLabs msg (no audio): {str(data)[:120]}")
                        elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                            log.info(f"ElevenLabs WS closed/error: {msg.type}")
                            break
                except Exception as e:
                    log.error(f"ElevenLabs recv error: {e}")
                finally:
                    log.info("ElevenLabs recv_audio done")
                    await audio_queue.put(None)

            send_task = asyncio.create_task(send_text())
            recv_task = asyncio.create_task(recv_audio())

            try:
                while True:
                    audio = await audio_queue.get()
                    if audio is None:
                        break
                    yield audio
            finally:
                send_task.cancel()
                recv_task.cancel()
                if not ws.closed:
                    await ws.close()
        finally:
            await session.close()
