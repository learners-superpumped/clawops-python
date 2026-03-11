# Gemini Realtime SDK Refactor Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stage 3 config (VAD 세부 튜닝, context_window_compression)를 제거하여 Gemini Live API 연결 끊김(ConnectionClosedOK) 문제를 해결한다.

**Architecture:** 현재 SDK 기반 구현은 정상. v1beta 엔드포인트가 거부하는 Stage 3 config 필드들만 제거하고, 누락된 에러 핸들링을 추가한다.

**Tech Stack:** google-genai SDK (>=1.60.0), Python asyncio

---

## Chunk 1: Config 수정 및 에러 핸들링

### Task 1: Stage 3 config 제거 및 에러 핸들링 추가

**Files:**
- Modify: `src/clawops/agent/pipeline/_gemini_realtime.py:178-199` (config에서 Stage 3 제거)
- Modify: `src/clawops/agent/pipeline/_gemini_realtime.py:210-215` (start() 에러 핸들링)
- Modify: `src/clawops/agent/pipeline/_gemini_realtime.py:229-244` (feed_audio() 에러 핸들링)
- Modify: `src/clawops/agent/pipeline/_gemini_realtime.py:273-275` (model_turn text emit 제거)

- [ ] **Step 1: config에서 Stage 3 필드 제거**

`_gemini_realtime.py`의 `start()` 메서드에서 config dict를 다음으로 교체:

```python
config: dict[str, Any] = {
    "response_modalities": ["AUDIO"],
    "speech_config": {
        "voice_config": {
            "prebuilt_voice_config": {"voice_name": self._voice},
        },
    },
    "input_audio_transcription": {},
    "output_audio_transcription": {},
}
```

제거 항목:
- `context_window_compression` (전체 블록)
- `realtime_input_config.automatic_activity_detection`의 세부 파라미터 (`start_of_speech_sensitivity`, `end_of_speech_sensitivity`, `prefix_padding_ms`, `silence_duration_ms`). `realtime_input_config` 블록 전체 제거.

- [ ] **Step 2: model_turn text emit 제거**

`_handle_response()`에서 `model_turn.parts[].text`를 assistant transcript로 emit하는 코드 제거 (line 273-275). `output_audio_transcription` 이벤트가 별도로 오므로 중복 방지.

```python
# 이 블록을 제거:
#     text = getattr(part, "text", None)
#     if text:
#         await self._call._emit("transcript", "assistant", text)
```

- [ ] **Step 3: start() 연결 실패 에러 핸들링 추가**

SDK 연결 `__aenter__` 실패 시 tracing span 정리:

```python
try:
    self._session = await self._live_ctx.__aenter__()
except Exception:
    if self._llm_span_ctx:
        import sys
        self._llm_span_ctx.__exit__(*sys.exc_info())
        self._llm_span_ctx = None
    raise
```

- [ ] **Step 4: feed_audio() 전송 실패 에러 핸들링 추가**

세션 끊어진 상태에서 `send_realtime_input()` 예외를 로깅하고 무시:

```python
try:
    await self._session.send_realtime_input(
        audio=types.Blob(data=pcm16k, mime_type="audio/pcm;rate=16000"),
    )
except Exception as e:
    log.warning(f"Gemini audio send failed: {e}")
```

- [ ] **Step 5: 변경사항 확인**

Run: `cd /Users/ghyeok/Developments/clawops-python && python -c "from clawops.agent.pipeline._gemini_realtime import GeminiRealtime; print('import OK')"`
Expected: `import OK`

---

### Task 2: 테스트 업데이트

**Files:**
- Modify: `tests/agent/test_gemini_realtime.py:82-96` (Stage 3 assertion 제거)

- [ ] **Step 1: Stage 3 config assertion 제거**

`test_gemini_sdk_start_connects()`에서 다음 assertion 블록 제거:

```python
# 제거: VAD 세부 설정 assertion (line 82-88)
#     vad = config["realtime_input_config"]["automatic_activity_detection"]
#     assert vad["disabled"] is False
#     assert vad["start_of_speech_sensitivity"] == "START_SENSITIVITY_HIGH"
#     assert vad["end_of_speech_sensitivity"] == "END_SENSITIVITY_LOW"
#     assert vad["prefix_padding_ms"] == 100
#     assert vad["silence_duration_ms"] == 500

# 제거: Context window compression assertion (line 94-96)
#     assert "context_window_compression" in config
#     assert "sliding_window" in config["context_window_compression"]
```

Stage 3 대신 Stage 1+2만 확인하도록 변경:

```python
# Stage 3 필드가 포함되지 않았는지 확인
assert "context_window_compression" not in config
assert "realtime_input_config" not in config
```

- [ ] **Step 2: 테스트 실행**

Run: `cd /Users/ghyeok/Developments/clawops-python && python -m pytest tests/agent/test_gemini_realtime.py -v`
Expected: 5 tests PASS

- [ ] **Step 3: 전체 agent 테스트 실행**

Run: `cd /Users/ghyeok/Developments/clawops-python && python -m pytest tests/agent/ -v`
Expected: 전체 PASS (약 157개)

---

### Task 3: google-genai 의존성 버전 업그레이드

**Files:**
- Modify: `pyproject.toml:57` (google-genai 버전)

- [ ] **Step 1: pyproject.toml에서 google-genai 버전 상향**

```toml
# 변경 전:
gemini-llm = ["clawops[agent]", "google-genai>=1.0.0"]

# 변경 후:
gemini-llm = ["clawops[agent]", "google-genai>=1.60.0"]
```

- [ ] **Step 2: Commit**

```bash
git add src/clawops/agent/pipeline/_gemini_realtime.py tests/agent/test_gemini_realtime.py pyproject.toml
git commit -m "fix: remove Stage 3 config from Gemini Realtime to fix ConnectionClosedOK

- Remove context_window_compression and VAD sub-fields rejected by v1beta
- Add error handling for start() connection failure and feed_audio() send failure
- Remove duplicate model_turn text emit (output_audio_transcription handles it)
- Bump google-genai minimum to >=1.60.0
- Update tests to verify Stage 3 fields are excluded"
```
