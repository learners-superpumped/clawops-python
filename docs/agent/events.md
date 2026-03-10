# 이벤트 & CallSession

## 이벤트 핸들러

`@agent.on()` 데코레이터로 통화 이벤트를 수신합니다.

```python
@agent.on("call_start")
async def on_call_start(call):
    print(f"통화 시작: {call.from_number} -> {call.to_number}")
    print(f"통화 ID: {call.call_id}")

@agent.on("call_end")
async def on_call_end(call):
    print(f"통화 종료: {call.call_id} (총 {call.duration:.1f}초)")

@agent.on("transcript")
async def on_transcript(call, role, text):
    print(f"[{role}] {text}")
    # role: "user" (고객 음성 인식) 또는 "assistant" (AI 응답)

@agent.on("call_failed")
async def on_failed(call, reason):
    print(f"발신 실패: {reason}")
```

### 이벤트 목록

| 이벤트 | 파라미터 | 설명 |
|--------|----------|------|
| `call_start` | `(call)` | 통화 시작 |
| `call_end` | `(call)` | 통화 종료 |
| `call_failed` | `(call, reason)` | 발신 실패 |
| `transcript` | `(call, role, text)` | 음성 텍스트 생성 |

## CallSession

개별 통화의 상태를 관리합니다. 이벤트 핸들러의 `call` 파라미터로 전달됩니다.

### 속성

| 속성 | 타입 | 설명 |
|------|------|------|
| `call_id` | `str` | 통화 ID |
| `from_number` | `str` | 발신 번호 |
| `to_number` | `str` | 수신 번호 |
| `account_id` | `str` | 계정 ID |
| `direction` | `str` | `"inbound"` 또는 `"outbound"` |
| `status` | `str` | `queued`, `ringing`, `in-progress`, `completed`, `failed`, `no-answer`, `busy` |
| `start_time` | `datetime` | 통화 시작 시간 |
| `duration` | `float` | 통화 경과 시간 (초) |
| `metadata` | `dict` | 사용자 정의 메타데이터 |

### 메서드

```python
@agent.on("call_start")
async def on_start(call):
    call.metadata["customer_id"] = "CUST_123"

    await call.send_audio(pcm16_bytes)   # 오디오 전송
    await call.clear_audio()             # 오디오 큐 초기화 (인터럽트 시)
    await call.hangup()                  # 통화 종료
    await call.wait()                    # 통화 종료까지 대기 (아웃바운드 시 유용)
```

> `await call.wait()`는 통화가 종료되어 `status`가 `completed`로 변경될 때까지 대기합니다. 주로 아웃바운드 단건 발신 시 통화 완료를 기다리는 데 사용합니다.
