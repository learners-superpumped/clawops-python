# tests/agent/test_pipeline_base.py
import pytest
from typing import AsyncIterator
from clawops.agent.pipeline._base import STT, TTS


@pytest.mark.asyncio
async def test_stt_protocol():
    class MySTT:
        async def transcribe(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[str]:
            async for chunk in audio_stream:
                yield f"text:{len(chunk)}"

    stt: STT = MySTT()

    async def audio_gen() -> AsyncIterator[bytes]:
        yield b"\x00" * 320
        yield b"\x01" * 320

    results = []
    async for text in stt.transcribe(audio_gen()):
        results.append(text)
    assert results == ["text:320", "text:320"]


@pytest.mark.asyncio
async def test_tts_protocol():
    class MyTTS:
        async def synthesize(self, text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
            async for text in text_stream:
                yield text.encode()

    tts: TTS = MyTTS()

    async def text_gen() -> AsyncIterator[str]:
        yield "hello"

    results = []
    async for chunk in tts.synthesize(text_gen()):
        results.append(chunk)
    assert results == [b"hello"]
