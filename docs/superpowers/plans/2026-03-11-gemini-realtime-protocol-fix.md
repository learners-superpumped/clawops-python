# Gemini Realtime Protocol Fix Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix Gemini Realtime setup message to include missing VAD tuning, transcription, and context compression settings so Korean speech recognition works properly.

**Architecture:** Single-file change to `_gemini_realtime.py` — modify the setup message dict in `start()` to add 3 missing protocol settings.

**Tech Stack:** Python, aiohttp WebSocket, Gemini Live API

**Spec:** `docs/superpowers/specs/2026-03-11-gemini-realtime-protocol-fix-design.md`

---

## Chunk 1: Setup Message Protocol Fix

### Task 1: Add test for setup message structure

**Files:**
- Modify: `tests/agent/test_gemini_realtime.py`

- [ ] **Step 1: Write test that verifies the setup message contains all required fields**

Add to `tests/agent/test_gemini_realtime.py`:

```python
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from clawops.agent.pipeline._gemini_realtime import GeminiRealtime


@pytest.mark.asyncio
async def test_gemini_setup_message_structure():
    """Setup 메시지에 VAD, transcription, compression 설정이 포함되는지 검증."""
    session = GeminiRealtime(
        api_key="AIza-test",
        system_prompt="Test prompt",
        voice="Kore",
    )

    # Mock WebSocket and HTTP session
    mock_ws = AsyncMock()
    mock_ws.closed = False
    mock_ws.__aiter__ = AsyncMock(
        return_value=AsyncMock(
            __anext__=AsyncMock(
                side_effect=StopAsyncIteration
            )
        )
    )

    # Capture sent messages
    sent_messages = []

    async def capture_send(data):
        sent_messages.append(data)

    mock_ws.send_str = capture_send

    # Mock setupComplete response
    setup_complete_msg = MagicMock()
    setup_complete_msg.type = 1  # WSMsgType.TEXT
    setup_complete_msg.data = json.dumps({"setupComplete": {}})

    mock_ws.__aiter__ = MagicMock(return_value=iter([setup_complete_msg]))

    mock_http = AsyncMock()
    mock_http.ws_connect = AsyncMock(return_value=mock_ws)

    session._http = mock_http
    session._ws = mock_ws

    # Patch to avoid actual WS connection
    with patch.object(session, '_wait_setup_complete', new_callable=AsyncMock):
        with patch('aiohttp.ClientSession', return_value=mock_http):
            mock_call = MagicMock()
            mock_call._emit = AsyncMock()

            # Patch _receive_loop to not actually run
            with patch.object(session, '_receive_loop', new_callable=AsyncMock):
                await session.start(mock_call)

    # Find the setup message
    assert len(sent_messages) >= 1
    setup_msg = json.loads(sent_messages[0])
    setup = setup_msg["setup"]

    # 1. VAD settings
    vad = setup["realtimeInputConfig"]["automaticActivityDetection"]
    assert vad["disabled"] is False
    assert vad["startOfSpeechSensitivity"] == "START_SENSITIVITY_HIGH"
    assert vad["endOfSpeechSensitivity"] == "END_SENSITIVITY_LOW"
    assert vad["prefixPaddingMs"] == 100
    assert vad["silenceDurationMs"] == 500

    # 2. Transcription settings
    gen_config = setup["generationConfig"]
    assert "inputAudioTranscription" in gen_config
    assert "outputAudioTranscription" in gen_config

    # 3. Context window compression
    assert "contextWindowCompression" in setup
    assert "slidingWindow" in setup["contextWindowCompression"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/ghyeok/Developments/clawops-python && python -m pytest tests/agent/test_gemini_realtime.py::test_gemini_setup_message_structure -v`

Expected: FAIL — current setup message is missing these fields.

### Task 2: Fix the setup message

**Files:**
- Modify: `src/clawops/agent/pipeline/_gemini_realtime.py:204-221`

- [ ] **Step 3: Update setup message dict in `start()` method**

Replace the setup message block (lines 204-221) with:

```python
        setup_msg: dict[str, Any] = {
            "setup": {
                "model": f"models/{self._model}",
                "generationConfig": {
                    "responseModalities": ["AUDIO"],
                    "speechConfig": {
                        "voiceConfig": {
                            "prebuiltVoiceConfig": {"voiceName": self._voice},
                        },
                    },
                    "inputAudioTranscription": {},
                    "outputAudioTranscription": {},
                },
                "realtimeInputConfig": {
                    "automaticActivityDetection": {
                        "disabled": False,
                        "startOfSpeechSensitivity": "START_SENSITIVITY_HIGH",
                        "endOfSpeechSensitivity": "END_SENSITIVITY_LOW",
                        "prefixPaddingMs": 100,
                        "silenceDurationMs": 500,
                    },
                },
                "contextWindowCompression": {
                    "slidingWindow": {},
                },
            },
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/ghyeok/Developments/clawops-python && python -m pytest tests/agent/test_gemini_realtime.py -v`

Expected: ALL PASS

- [ ] **Step 5: Run full agent test suite**

Run: `cd /Users/ghyeok/Developments/clawops-python && python -m pytest tests/agent/ -v`

Expected: ALL PASS — no regressions

- [ ] **Step 6: Commit**

```bash
cd /Users/ghyeok/Developments/clawops-python
git add src/clawops/agent/pipeline/_gemini_realtime.py tests/agent/test_gemini_realtime.py
git commit -m "fix: add missing VAD, transcription, compression settings to Gemini setup"
```
