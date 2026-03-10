# 커스텀 제공자 구현 가이드

STT, LLM, TTS 제공자를 직접 구현하여 파이프라인 모드에서 사용할 수 있습니다. 각 제공자는 Python Protocol을 따르면 되므로, 상속이나 특정 베이스 클래스가 필요하지 않습니다.

## Protocol 정의

```python
from clawops.agent.pipeline import STT, LLM, TTS, SpeechEvent
```

### SpeechEvent

STT가 반환하는 이벤트 타입입니다.

```python
@dataclass(frozen=True, slots=True)
class SpeechEvent:
    type: Literal["interim", "final"]
    transcript: str
```

| 타입 | 용도 | transcript |
|------|------|-----------|
| `interim` | Barge-in 트리거 (AI 오디오 중단) | 빈 문자열 또는 부분 텍스트 |
| `final` | 확정 텍스트로 응답 생성 | 완성된 발화 텍스트 |

---

## STT 구현

```python
class STT(Protocol):
    async def transcribe(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[SpeechEvent]:
        ...
```

### 입력

- `audio_stream`: PCM16 signed 16-bit LE, **16kHz**, mono
- 파이프라인이 전화 오디오(G.711 μ-law 8kHz)를 자동으로 변환하여 전달합니다

### 출력

- `SpeechEvent` 비동기 이터레이터
- `interim` 이벤트: 사용자가 말하기 시작했음을 알림 (barge-in용)
- `final` 이벤트: 발화가 완료된 확정 텍스트

### 예시: Whisper 기반 STT

```python
import asyncio
from typing import AsyncIterator
from clawops.agent.pipeline import SpeechEvent

class WhisperSTT:
    def __init__(self, model: str = "whisper-1"):
        self._model = model

    async def transcribe(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[SpeechEvent]:
        buffer = bytearray()
        CHUNK_SIZE = 16000 * 2 * 2  # 2초 분량 (16kHz, 16bit)

        async for chunk in audio_stream:
            buffer.extend(chunk)

            if len(buffer) >= CHUNK_SIZE:
                # 버퍼가 충분하면 인식 시도
                text = await self._recognize(bytes(buffer))
                buffer.clear()

                if text:
                    # VAD 기반 barge-in이 없으므로 interim+final 동시 발송
                    yield SpeechEvent(type="interim", transcript=text)
                    yield SpeechEvent(type="final", transcript=text)

        # 남은 버퍼 처리
        if buffer:
            text = await self._recognize(bytes(buffer))
            if text:
                yield SpeechEvent(type="final", transcript=text)

    async def _recognize(self, pcm16: bytes) -> str:
        import openai
        # PCM16을 WAV로 변환 후 Whisper API 호출
        wav = self._pcm16_to_wav(pcm16)
        client = openai.AsyncOpenAI()
        result = await client.audio.transcriptions.create(
            model=self._model,
            file=("audio.wav", wav, "audio/wav"),
        )
        await client.close()
        return result.text

    def _pcm16_to_wav(self, pcm: bytes) -> bytes:
        import struct
        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF", 36 + len(pcm), b"WAVE",
            b"fmt ", 16, 1, 1, 16000, 32000, 2, 16,
            b"data", len(pcm),
        )
        return header + pcm
```

### Barge-in을 위한 권장사항

빠른 barge-in을 위해 다음을 권장합니다:

1. **VAD 이벤트 활용** — STT 서비스가 음성 시작 이벤트(예: Deepgram `SpeechStarted`)를 제공하면 즉시 `interim` 이벤트를 발생시키세요
2. **Interim 결과 활용** — 부분 인식 결과가 나오면 `interim` 이벤트로 보내세요
3. **로컬 VAD** — STT 서비스에 VAD가 없다면 Silero VAD 등을 앞단에 추가하세요

```python
# VAD 이벤트가 있는 STT 서비스 예시
async def transcribe(self, audio_stream):
    # 음성 시작 → 빈 interim (barge-in 트리거)
    yield SpeechEvent(type="interim", transcript="")

    # 부분 인식 결과는 무시 (이미 interim 발송)

    # 발화 완료 → final
    yield SpeechEvent(type="final", transcript="안녕하세요")
```

---

## LLM 구현

```python
class LLM(Protocol):
    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        ...
```

### 입력

- `messages`: OpenAI Chat Completions 포맷의 메시지 리스트
  ```python
  [
      {"role": "system", "content": "시스템 프롬프트"},
      {"role": "user", "content": "사용자 발화"},
      {"role": "assistant", "content": "AI 응답"},
      {"role": "assistant", "content": None, "tool_calls": [...]},
      {"role": "tool", "tool_call_id": "...", "content": "도구 결과"},
  ]
  ```
- `tools`: OpenAI Chat Completions 포맷의 도구 스키마 (선택)
  ```python
  [
      {
          "type": "function",
          "function": {
              "name": "check_order",
              "description": "주문 상태를 확인합니다.",
              "parameters": {
                  "type": "object",
                  "properties": {
                      "order_id": {"type": "string"}
                  },
                  "required": ["order_id"]
              }
          }
      }
  ]
  ```

### 출력

- 텍스트 토큰을 스트리밍으로 yield
- Tool call이 필요한 경우 다음 JSON 문자열을 yield:
  ```json
  {
    "type": "tool_calls",
    "tool_calls": [
      {
        "id": "call_abc123",
        "function": {
          "name": "check_order",
          "arguments": "{\"order_id\": \"ORD-001\"}"
        }
      }
    ]
  }
  ```

### 예시: Anthropic Claude LLM

```python
from typing import Any, AsyncIterator

class ClaudeLLM:
    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self._model = model

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        import anthropic

        client = anthropic.AsyncAnthropic()

        # OpenAI 포맷 → Anthropic 포맷 변환
        system = ""
        claude_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            elif msg["role"] == "tool":
                claude_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg["tool_call_id"],
                        "content": msg["content"],
                    }],
                })
            elif msg["role"] == "assistant" and msg.get("tool_calls"):
                content = []
                if msg.get("content"):
                    content.append({"type": "text", "text": msg["content"]})
                for tc in msg["tool_calls"]:
                    content.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": json.loads(tc["function"]["arguments"]),
                    })
                claude_messages.append({"role": "assistant", "content": content})
            else:
                claude_messages.append(msg)

        # Tool 포맷 변환
        claude_tools = None
        if tools:
            claude_tools = []
            for t in tools:
                func = t["function"]
                claude_tools.append({
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
                })

        kwargs = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": claude_messages,
        }
        if system:
            kwargs["system"] = system
        if claude_tools:
            kwargs["tools"] = claude_tools

        try:
            tool_uses = []
            async with client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    if event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            yield event.delta.text
                        elif event.delta.type == "input_json_delta":
                            # tool input 누적은 stream 종료 후 처리
                            pass
                    elif event.type == "content_block_stop":
                        pass

                # 스트림 종료 후 tool_use 확인
                response = await stream.get_final_message()
                for block in response.content:
                    if block.type == "tool_use":
                        tool_uses.append({
                            "id": block.id,
                            "function": {
                                "name": block.name,
                                "arguments": json.dumps(block.input),
                            },
                        })

            if tool_uses:
                import json as _json
                yield _json.dumps({
                    "type": "tool_calls",
                    "tool_calls": tool_uses,
                })
        finally:
            await client.close()
```

### Tool Call 처리 규칙

1. 텍스트와 tool call을 동시에 반환하지 마세요. 텍스트 스트리밍이 끝난 후 tool call JSON을 yield합니다.
2. `tool_calls[].id`는 고유해야 합니다. 파이프라인이 이 ID로 결과를 매칭합니다.
3. Tool 실행 후 파이프라인이 결과를 messages에 추가하고 `generate()`를 다시 호출합니다.

---

## TTS 구현

```python
class TTS(Protocol):
    async def synthesize(self, text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
        ...
```

### 입력

- `text_stream`: 문장 단위로 분할된 텍스트 스트림
- 파이프라인이 LLM 출력을 문장 부호(`.!?。！？`) 기준으로 분할하여 전달합니다

### 출력

- PCM16 signed 16-bit LE 오디오 청크
- **sample rate**: 자유 (파이프라인이 8kHz로 리샘플링)
- `sample_rate` 속성(property)을 제공하면 파이프라인이 자동으로 리샘플링합니다. 없으면 24000Hz로 가정합니다.

### 예시: Google Cloud TTS

```python
from typing import AsyncIterator

class GoogleTTS:
    def __init__(self, voice: str = "ko-KR-Neural2-A"):
        self._voice = voice

    @property
    def sample_rate(self) -> int:
        return 24000

    async def synthesize(self, text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
        from google.cloud import texttospeech_v1 as tts

        client = tts.TextToSpeechAsyncClient()

        async for text in text_stream:
            if not text.strip():
                continue

            response = await client.synthesize_speech(
                input=tts.SynthesisInput(text=text),
                voice=tts.VoiceSelectionParams(
                    language_code="ko-KR",
                    name=self._voice,
                ),
                audio_config=tts.AudioConfig(
                    audio_encoding=tts.AudioEncoding.LINEAR16,
                    sample_rate_hertz=self.sample_rate,
                ),
            )

            # WAV 헤더(44바이트) 제거 → raw PCM16
            yield response.audio_content[44:]
```

### `sample_rate` 속성

파이프라인은 TTS 출력을 전화 오디오(8kHz)로 변환해야 합니다. `sample_rate` 속성으로 출력 sample rate를 알려주세요.

```python
@property
def sample_rate(self) -> int:
    return 24000  # 24kHz PCM16을 출력하는 경우
```

이 속성이 없으면 24000Hz로 가정합니다.

---

## 제공자 조합 예시

```python
from clawops.agent import ClawOpsAgent
from clawops.agent.pipeline import PipelineSession, DeepgramSTT

# Deepgram STT + Claude LLM + Google TTS
agent = ClawOpsAgent(
    from_="07012341234",
    session=PipelineSession(
        system_prompt="친절한 상담원입니다.",
        stt=DeepgramSTT(),
        llm=ClaudeLLM(model="claude-sonnet-4-20250514"),
        tts=GoogleTTS(voice="ko-KR-Neural2-A"),
    ),
)
```

세 제공자 모두 커스텀으로 교체하거나, 내장 제공자와 혼합할 수 있습니다.

---

## 체크리스트

커스텀 제공자 구현 시 확인할 항목:

### STT
- [ ] `transcribe()`가 `AsyncIterator[SpeechEvent]`를 반환하는가?
- [ ] `interim` 이벤트를 발생시키는가? (barge-in에 필요)
- [ ] `final` 이벤트의 transcript가 빈 문자열이 아닌가?
- [ ] 입력 오디오가 PCM16 16kHz임을 전제로 하는가?

### LLM
- [ ] `generate()`가 `AsyncIterator[str]`를 반환하는가?
- [ ] messages 포맷이 OpenAI Chat Completions 호환인가?
- [ ] Tool call 시 올바른 JSON 포맷(`{"type":"tool_calls",...}`)을 yield하는가?
- [ ] Tool call의 `id` 필드가 고유한가?

### TTS
- [ ] `synthesize()`가 `AsyncIterator[bytes]`를 반환하는가?
- [ ] 출력이 raw PCM16 (WAV 헤더 없음)인가?
- [ ] `sample_rate` 속성을 제공하는가?
- [ ] 빈 텍스트를 무시하는가?
