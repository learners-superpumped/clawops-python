# Gemini Realtime Protocol Fix Design

## Problem

Gemini Realtime 세션에서 사용자의 음성을 제대로 이해하지 못하고, 맥락에 맞지 않는 응답을 반환한다. 동일한 system prompt와 시나리오에서 OpenAI Realtime은 정상 동작한다.

## Root Cause Analysis

`_gemini_realtime.py`의 setup 메시지를 공식 Gemini Live API 프로토콜과 비교한 결과, 4가지 설정이 누락되어 있다.

### 1. VAD (Voice Activity Detection) 세부 설정 부재

**현재:**
```json
{
  "automaticActivityDetection": {
    "disabled": false
  }
}
```

**문제:** 기본 `silenceDurationMs`가 100ms로, 한국어 발화 패턴에서 너무 공격적으로 발화를 끊는다. 짧은 발화("네", "아니요")나 문장 중간 포즈가 턴 종료로 인식될 수 있다.

### 2. inputAudioTranscription / outputAudioTranscription 미설정

**현재:** setup 메시지에 transcription 설정이 없음

**문제:**
- `_handle_event()`에서 `inputTranscription`/`outputTranscription` 이벤트를 처리하는 코드가 있지만, setup에서 활성화하지 않아 이벤트가 도착하지 않음
- 디버깅 불가 (Gemini가 실제로 무엇을 듣고 있는지 확인 불가)

### 3. contextWindowCompression 미설정

**현재:** 설정 없음

**문제:** 압축 없이는 오디오 전용 세션이 ~15분으로 제한됨. 장시간 통화 시 세션이 강제 종료될 수 있다.

### 4. language 설정 (해당 없음)

`gemini-2.5-flash-native-audio-preview` 모델은 언어를 자동 감지하며, `languageCode` 필드를 지원하지 않는다. 따라서 추가하지 않는 것이 올바르다.

## Design

### 수정 대상 파일

`src/clawops/agent/pipeline/_gemini_realtime.py`

### 변경 1: VAD 세부 파라미터 추가

Setup 메시지의 `realtimeInputConfig.automaticActivityDetection`에 세부 파라미터를 추가한다.

```python
"realtimeInputConfig": {
    "automaticActivityDetection": {
        "disabled": False,
        "startOfSpeechSensitivity": "START_SENSITIVITY_HIGH",
        "endOfSpeechSensitivity": "END_SENSITIVITY_LOW",
        "prefixPaddingMs": 100,
        "silenceDurationMs": 500,
    },
},
```

- `startOfSpeechSensitivity: HIGH` - 작은 소리에도 발화 시작을 감지
- `endOfSpeechSensitivity: LOW` - 짧은 침묵으로 발화를 끊지 않음
- `prefixPaddingMs: 100` - 발화 시작 전 100ms 패딩 보존
- `silenceDurationMs: 500` - 500ms 침묵 후 턴 종료 (기본 100ms 대비 여유)

### 변경 2: Transcription 활성화

Setup 메시지의 `generationConfig`에 transcription 설정을 추가한다.

```python
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
```

주의: `gemini-2.5-flash-native-audio-preview` 모델에서 transcription이 불안정할 수 있다는 보고가 있음 (googleapis/js-genai#1212). 오류 발생 시 설정을 제거할 수 있도록 한다.

### 변경 3: Context Window Compression 추가

Setup 메시지 최상위(`setup` 내부)에 compression 설정을 추가한다.

```python
"contextWindowCompression": {
    "slidingWindow": {},
},
```

기본값을 사용하여 서버가 자동으로 오래된 턴을 압축한다.

### 최종 Setup 메시지 구조

```python
setup_msg = {
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
        "systemInstruction": {"parts": [{"text": "..."}]},  # 조건부
        "tools": [{"functionDeclarations": [...]}],          # 조건부
    },
}
```

## Scope

- `_gemini_realtime.py`의 `start()` 메서드 내 setup 메시지 수정
- 기존 코드 구조 유지, 설정 값만 추가
- 오디오 변환 로직 변경 없음
- 테스트: 실제 전화 통화로 한국어 인식 품질 확인

## Risks

- `inputAudioTranscription`이 native audio 모델에서 불안정할 수 있음 — 오류 시 제거
- VAD 파라미터 값은 튜닝이 필요할 수 있음 (500ms가 너무 길 경우 조정)
