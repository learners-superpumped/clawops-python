# 파이프라인 모드

Realtime API 대신 STT, LLM, TTS 제공자를 직접 조합하는 모드입니다. `PipelineSession`을 사용합니다.

## 기본 사용법

```python
from clawops.agent import ClawOpsAgent
from clawops.agent.pipeline import PipelineSession, DeepgramSTT, OpenAILLM, ElevenLabsTTS

agent = ClawOpsAgent(
    from_="07012341234",
    session=PipelineSession(
        system_prompt="친절한 상담원입니다.",
        stt=DeepgramSTT(),
        llm=OpenAILLM(model="gpt-4o-mini"),
        tts=ElevenLabsTTS(),
    ),
)
```

## 오디오 처리 흐름

```
전화 오디오 (G.711 μ-law 8kHz)
    │
    ▼
PCM16 8kHz → PCM16 16kHz ──► STT ──► SpeechEvent
                                          │
                    ┌─────────────────────┘
                    ▼
               LLM (텍스트 스트림)
                    │
                    ▼
               TTS (PCM16 오디오)
                    │
                    ▼
         PCM16 → 8kHz → G.711 μ-law → 전화
```

## 내장 제공자

### DeepgramSTT

Deepgram Nova 모델을 사용한 실시간 음성 인식.

```python
from clawops.agent.pipeline import DeepgramSTT

stt = DeepgramSTT(
    model="nova-3",          # Deepgram 모델
    language="ko",           # 언어 코드
    endpointing=300,         # 발화 종료 감지 (ms)
    utterance_end_ms=1000,   # 발화 종료 대기 (ms)
)
```

환경변수: `DEEPGRAM_API_KEY`

**특징:**
- WebSocket 스트리밍 방식
- `SpeechStarted` VAD 이벤트로 빠른 barge-in 감지
- Interim/Final 결과 분리

### OpenAILLM

OpenAI Chat Completions 스트리밍.

```python
from clawops.agent.pipeline import OpenAILLM

llm = OpenAILLM(
    model="gpt-4o-mini",     # 모델명
    temperature=0.8,
    max_tokens=4096,
)
```

환경변수: `OPENAI_API_KEY`

**특징:**
- 스트리밍 텍스트 생성
- Tool call 자동 처리 (Chat Completions 포맷)

### AnthropicLLM

Anthropic Claude Messages 스트리밍.

```python
from clawops.agent.pipeline import AnthropicLLM

llm = AnthropicLLM(
    model="claude-sonnet-4-6",  # 모델명
    temperature=0.8,
    max_tokens=4096,
)
```

환경변수: `ANTHROPIC_API_KEY`

**특징:**
- 스트리밍 텍스트 생성
- Tool call 자동 처리 (OpenAI 메시지 포맷을 Anthropic 포맷으로 자동 변환)

### GeminiLLM

Google Gemini 스트리밍.

```python
from clawops.agent.pipeline import GeminiLLM

llm = GeminiLLM(
    model="gemini-2.5-flash",  # 모델명
    temperature=0.8,
    max_tokens=4096,
)
```

환경변수: `GOOGLE_API_KEY`

**특징:**
- 스트리밍 텍스트 생성
- Tool call 자동 처리 (OpenAI 메시지 포맷을 Gemini 포맷으로 자동 변환)

### OllamaLLM

Ollama 로컬 모델 스트리밍 (OpenAI 호환 API).

```python
from clawops.agent.pipeline import OllamaLLM

llm = OllamaLLM(
    model="llama3.2",           # Ollama 모델명
    base_url="http://localhost:11434/v1",  # 기본값
    temperature=0.8,
    max_tokens=4096,
)
```

환경변수: `OLLAMA_BASE_URL` (기본 `http://localhost:11434/v1`)

**특징:**
- OpenAI 호환 API 사용 (별도 SDK 불필요, `openai` 패키지 사용)
- 스트리밍 텍스트 생성
- Tool call 지원 (모델이 지원하는 경우)

### ElevenLabsTTS

ElevenLabs WebSocket 스트리밍 음성 합성.

```python
from clawops.agent.pipeline import ElevenLabsTTS

tts = ElevenLabsTTS(
    voice_id="EXAVITQu4vr4xnSDxMaL",  # 음성 ID
    model="eleven_flash_v2_5",          # 모델
    output_format="pcm_24000",          # 출력 포맷
    language_code="ko",
    stability=0.5,
    similarity_boost=0.75,
)
```

환경변수: `ELEVENLABS_API_KEY`

**특징:**
- WebSocket 스트리밍 (낮은 지연)
- `sample_rate` 속성 자동 추출 (`pcm_24000` → 24000)

## Barge-in (끼어들기)

사용자가 말하면 AI 오디오를 즉시 중단합니다.

1. **SpeechStarted** — Deepgram VAD가 음성 감지 → Twilio 오디오 버퍼 클리어
2. **Interim transcript** — 부분 인식 결과 (이미 VAD로 처리된 경우 무시)
3. **Final transcript** — 확정 텍스트 → 새 응답 생성

## Debounce

AI가 아직 말하기 전에 사용자가 추가 발화하면, 0.5초 대기 후 한 번에 응답합니다. 빠르게 연속 발화해도 불필요한 응답 생성을 방지합니다.

## 세션 타입 비교

| | OpenAI Realtime | Gemini Realtime | Pipeline |
|---|-----------------|-----------------|----------|
| 제공자 | OpenAI | Google | 자유 조합 |
| 지연 | 낮음 (단일 API) | 낮음 (단일 API) | 중간 (STT+LLM+TTS) |
| Barge-in | 내장 VAD | 내장 VAD | Deepgram VAD + clear_audio |
| 비용 | Realtime API 요금 | Gemini API 요금 | 각 제공자 개별 요금 |
| 음성 | OpenAI 음성 | Google 음성 | ElevenLabs 등 자유 선택 |

## 커스텀 제공자

내장 제공자 대신 직접 구현할 수 있습니다. 자세한 가이드는 [커스텀 제공자](custom-providers.md)를 참고하세요.
