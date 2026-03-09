# Agent Outbound Call Design

**Goal:** Agent SDK에 `agent.call(to)` 발신 기능을 추가하여, 수신과 동일한 AI 대화 파이프라인으로 아웃바운드 콜을 처리한다.

**Architecture:** REST API로 발신 요청 → 서버가 ARI originate → 상대방 수신 시 media WS 생성 → Control WS로 agent에게 mediaUrl 전달 → 기존 RealtimeSession 파이프라인 재사용.

**Tech Stack:** Python SDK (aiohttp), Node.js 서버 (Express + ARI), Asterisk PJSIP

---

## 1. 발신 흐름

```
개발자 코드                    SDK                         서버                        Asterisk
─────────                    ───                         ────                        ────────
agent.call("010...")  →  REST API POST /calls     →  CallLog 저장 (queued)
                            (from, to, Url 없음)       ARI originate           →  발신 시작
                                                                                    │
                     ←  CallSession 즉시 리턴                                        ↓
                         (status: queued)                                        상대방 전화 울림
                                                                                    │
                         Control WS 수신           ←  call.ringing                   ↓
                         (status → ringing)                                      상대방 수신
                                                                                    │
                         Control WS 수신           ←  call.outbound_ready        media WS 생성
                         (mediaUrl 포함)                                             │
                              │                                                     │
                         media WS 연결 ──────────────────────────────────────────────┘
                         RealtimeSession 시작
                         (기존 수신과 동일)
```

## 2. SDK API 디자인

### 사용 예시

```python
agent = ClawOpsAgent(
    from_="07012345678",
    system_prompt="당신은 예약 확인 도우미입니다.",
    voice="marin",
)

@agent.on("call_start")
async def on_start(call):
    print(f"통화 시작: {call.call_id} ({call.direction})")

@agent.on("transcript")
async def on_transcript(call, role, text):
    print(f"{role}: {text}")

@agent.on("call_end")
async def on_end(call):
    print(f"통화 종료: {call.call_id}")

@agent.on("call_failed")
async def on_failed(call, reason):
    print(f"발신 실패: {call.call_id} - {reason}")

async def main():
    # 발신만 하는 경우 — start() 없이 가능
    call = await agent.call("01012345678")  # Control WS 자동 연결
    print(call.call_id)    # 즉시 사용 가능
    print(call.status)     # "queued"
    print(call.direction)  # "outbound"

    # 수신도 같이 하는 경우
    await agent.start()  # 수신 대기 시작
    call = await agent.call("01012345678")  # 발신도 가능

asyncio.run(main())
```

### API 변경

- `listen()` 제거 → `start()` / `stop()` 으로 교체
- `start()`: 비블로킹, Control WS 연결 + 수신 대기
- `stop()`: Control WS 닫기, 활성 세션 정리
- `call(to, timeout=60)`: REST API로 발신 → CallSession 즉시 리턴
  - Control WS 미연결 시 자동 연결

### CallSession 확장

- `direction`: `"inbound"` / `"outbound"`
- `status`: `"queued"` → `"ringing"` → `"in-progress"` → `"completed"` / `"failed"` / `"no-answer"` / `"busy"`

## 3. 서버 변경

### REST API (`voice-api-server.js`)

`POST /v1/accounts/{id}/calls`:
- `Url`을 required → optional로 변경
- `Url` 없이 호출 시: `From` 번호에 agent가 연결되어 있는지 확인
  - 있으면 Agent 모드로 발신
  - 없으면 409 에러: "From 번호에 연결된 Agent가 없습니다"
- `Timeout` 파라미터 추가 (optional, 기본 60초)

### 발신 처리 분기 (`call-handler.js` / `ari-handler.js`)

StasisStart (상대방 수신 시):
- **Agent 모드**: webhook 호출 대신 → media WS 생성 → Control WS로 `call.outbound_ready` 전송
- **기존 모드**: VoiceML webhook 호출 (변경 없음)

### Control WS 신규 이벤트

| 방향 | 이벤트 | 데이터 | 시점 |
|------|--------|--------|------|
| 서버 → Agent | `call.ringing` | `{callId}` | 상대방 전화 울릴 때 |
| 서버 → Agent | `call.outbound_ready` | `{callId, from, to, mediaUrl}` | 상대방이 받았을 때 |
| 서버 → Agent | `call.failed` | `{callId, reason}` | 실패/무응답/통화중 |

### Swagger 문서 (`swagger/voice-spec.js`)

- `Url` optional로 변경, Agent 모드 설명 추가
- `Timeout` 파라미터 추가
- 409 에러 응답 추가: "From 번호에 연결된 Agent가 없습니다"

## 4. 에러 처리

| 시점 | 에러 | 처리 |
|------|------|------|
| API 호출 시 | Url 없음 + Agent 미등록 | 409 에러 즉시 리턴 |
| API 호출 시 | From 번호 미등록 | 400 에러 (기존) |
| 발신 중 | 상대방 통화중 | Control WS → `call.failed` (reason: busy) |
| 발신 중 | 상대방 무응답 (timeout) | Control WS → `call.failed` (reason: no-answer) |
| 발신 중 | 번호 오류/통신 실패 | Control WS → `call.failed` (reason: failed) |
| 통화 중 | Agent Control WS 끊김 | 서버가 통화 종료 처리 |
| 통화 중 | media WS 연결 실패 | 서버가 10초 타임아웃 후 통화 종료 |

## 5. 변경 범위

### 서버 (clawops)

| 파일 | 변경 내용 |
|------|----------|
| `voice-api-server.js` | POST /calls Agent 모드 분기, Timeout 파라미터 |
| `ari-handler.js` | StasisStart Agent 모드 → call.outbound_ready 이벤트 |
| `call-handler.js` | Agent 모드 발신 처리 (webhook 대신 media WS + Control WS 알림) |
| `swagger/voice-spec.js` | Url optional, Timeout 추가, 409 에러 문서화 |

### Python SDK (clawops-python)

| 파일 | 변경 내용 |
|------|----------|
| `_agent.py` | `listen()` 제거, `start()`/`stop()` 추가, `call()` 추가 |
| `_control_ws.py` | `call.outbound_ready`, `call.ringing`, `call.failed` 이벤트 핸들링 |
| `_session.py` | `direction`, `status` 필드 추가 |
| `README.md` | `listen()` → `start()` 예제 교체 (2곳) |
| `docs/agent.md` | `listen()` → `start()` 예제 교체 (3곳), 발신 사용법 문서 추가 |

### 변경 없음

| 항목 | 이유 |
|------|------|
| `_media_ws.py` | 수신과 동일한 media WS 프로토콜 |
| `_realtime_session.py` | 수신과 동일한 OpenAI 파이프라인 |
| `_tool.py` | 기존 ToolRegistry.fork() 재사용 |
