# Realtime Session Prewarm + First-Audio Prebuffer

**Date:** 2026-05-24
**Status:** Draft (awaiting review)
**Scope:** clawops-python, clawops-node, clawops/call-engine

## 문제 정의

AMD off (또는 미사용) 인 outbound 통화에서 상대방이 응답한 직후부터 첫 음성(greeting) 이 들리기까지 1.2–3.2 초의 체감 지연이 있다.

지연 분해 (answer 직후 기준):

| # | 단계 | 위치 | 예상 |
|---|---|---|---|
| 1 | SIP 200 OK → StasisStart 진입 | dialplan | ~100ms |
| 2 | `setupAgentMediaSession` (externalMedia + mixing bridge) | `call-handler.js:230-245` | 200–300ms |
| 3 | Voice Agent SDK 호출 + media WS 연결 | call-engine ↔ SDK | 100–300ms |
| 4 | LLM Realtime `connect()` + `session.update()` | `_openai.py:162-200`, `openai-realtime.ts:22-160` | 300–500ms |
| 5 | `response.create()` → 첫 audio delta 수신 | OpenAI 추론 | 500–2000ms |
| 6 | RTP 송출 | rtpServer | ~20ms |

**관찰:** 4·5번은 미디어 채널과 본질적으로 무관하다 — LLM WebSocket 연결과 첫 audio delta 생성은 RTP 가 살아있을 필요가 없다. 강결합은 코드 구조 때문이지 프로토콜 때문이 아니다.

## 목표

- 4·5번 시간을 **answer 이전 시간으로 흡수**한다.
- 첫 음성은 **Realtime model 이 실제로 생성한 audio** 그대로 유지한다 (외부 TTS 캐싱 X — voice mismatch 회피).
- 체감 first-speech latency 1.2–3.2s → **~150ms (media bridge setup 만 남음)**.

## 비목표

- Early media (SIP 183), warm session pool, dialplan slim 은 본 spec 범위 외 (후속 검토).
- AMD 활성 경로의 변경 (AMD 가 활성이면 음성 검출 후 분기되므로 prewarm 효과 제한적).

## 설계 — P + B (Prewarm + First-Audio Prebuffer)

### 두 단계 분리

기존 `Session.start(callSession, tools)` 의 강결합을 두 단계로 분리한다 (양 SDK mirror).

**Stage 1 — `LLMConnection.connect(provider, prompt, tools, *, prebuffer_greeting=True)`**

- LLM WebSocket handshake + `session.update` 수행
- `prebuffer_greeting=True` 면 `response.create` 도 호출하고 도착하는 audio.delta 를 메모리 큐에 누적
- `CallSession` / media WS 없이도 호출 가능 (callId 만 ownership 식별용으로 보관)
- 반환 객체 `LLMConnection` 은 attach 전까지 audio 를 *consume 하지만 출력하지는 않는* 상태

**Stage 2 — `Session.attach(conn, callSession, mediaWs)`**

- prewarmed `LLMConnection` 을 활성 통화에 부착
- 메모리 큐의 audio delta 를 RTP timing (20ms/chunk) 으로 emit 시작
- 이후 delta 는 실시간 stream 그대로 통과

### call-engine 측 흐름

```
[ari-handler.initiateOutboundCall 직후]
const llmConn = voiceAgentClient.prewarm({
  callId, provider, systemPrompt, tools, prebufferGreeting: true,
});
// llmConn 은 백그라운드에서 LLM connect + first delta 누적

[StasisStart]
const channel = await stasisStart;
const mediaWs = await setupAgentMediaSession(channel);  // 기존 흐름
await voiceAgentClient.attach(llmConn, channel, mediaWs);
// 큐 flush 시작 → 사용자 첫 음성 들음
```

### Provider 별 동작

**OpenAI Realtime**

- `wss://api.openai.com/v1/realtime?model=gpt-realtime-2` 연결
- `session.update` 로 system prompt / tools / 오디오 포맷 (μ-law 8k) 설정
- `response.create` 호출 (input audio buffer 비어있어도 generate)
- `response.output_audio.delta` 이벤트들을 SDK 메모리 큐에 누적
- attach 후 큐 → RTP, 후속 delta 는 실시간 통과

**Gemini Live**

- `client.aio.live.connect()` (Python) / `client.live.connect()` (Node)
- `session.sendRealtimeInput({text: '인사해 주세요.'})` 로 greeting trigger
- audio 응답을 같은 방식으로 큐잉
- attach 시 flush

**PipelineSession (STT→LLM→TTS)**

- 동일 인터페이스 적용. LLM 텍스트 생성 + TTS 호출까지 prewarm 단계에서 진행. 큐는 TTS μ-law 출력 단위.

### Mirror 보장

[feedback_voiceml_agent_sdk_parity] 에 따라 clawops-python / clawops-node 양쪽에 동일 API / 동일 동작을 동시에 반영한다.

- 인터페이스 시그니처 동일
- 큐잉 timing / flush 정책 동일
- 에러/timeout 동작 동일
- 단위 테스트 케이스 동일 (이름/시나리오 매칭)

## 미응답·실패 처리

prewarmed 리소스가 leak 되지 않도록 명시적 가드:

| 시나리오 | 동작 |
|---|---|
| ARI originate 실패 (즉시 에러) | `llmConn.cancel()` 즉시 호출, WebSocket close |
| SIP 미응답 (30s timeout) | originate timeout 콜백에서 `llmConn.cancel()` |
| 거절/busy (4xx) | hangup 이벤트 처리에서 `llmConn.cancel()` |
| attach 전 `llmConn` idle > N초 | SDK 측 자체 timeout (기본 30s) — auto close |
| attach 후 정상 종료 | 기존 hangup 경로 그대로 |

[call_engine_ari_hangup_no_timeout_guard] 함정 회피 — 모든 cancel 경로에 timeout 가드를 둔다.

## 비용 영향

매 originate 마다 LLM inference (greeting 분량, 보통 1–2초 audio) 가 선결제된다.

- 미응답률 R, greeting 비용 C 라면 ΔCost/통화 = R × C
- **검증 전제:** OpenAI Realtime / Gemini Live 의 "connect 만 하고 audio 안 받음" 상태 과금 정책 확인 (현재 미확정)
- 본 spec 의 작업 1번은 비용 실측. 실측 결과에 따라 `prebufferGreeting` 플래그를 통화 단위로 on/off 가능하게 둔다.

## 검증·테스트

**단위:**
- `LLMConnection.connect()` 가 미디어 인자 없이 동작
- 큐 누적 → `attach()` 시 ordered flush
- 모든 cancel 경로에서 WebSocket close 확인

**통합:**
- mock LLM provider 로 prewarm → attach → RTP 출력 검증
- 미응답/거절/timeout 3 시나리오 leak 검증

**프로덕션 측정:**
- 첫 audio delta 도착 시각 ↔ 첫 RTP egress 시각 logging
- A/B 비교 (prewarm on/off) latency P50/P95
- 비용: 매 통화 LLM 사용량 + ARI 결과 (응답/미응답/거절) 매트릭스

## 인터페이스 변경 요약

### clawops-python

```python
class LLMConnection:
    @classmethod
    async def connect(cls, provider, system_prompt, tools, *, prebuffer_greeting=True) -> "LLMConnection": ...
    async def cancel(self) -> None: ...

class Session:
    async def attach(self, conn: LLMConnection, call: CallSession, media_ws: MediaWebSocket) -> None: ...
    # 기존 start() 는 내부적으로 connect → attach 직렬 호출하는 thin wrapper 로 유지
```

### clawops-node

```ts
class LLMConnection {
  static async connect(provider, prompt, tools, opts?: { prebufferGreeting?: boolean }): Promise<LLMConnection>;
  async cancel(): Promise<void>;
}

interface Session {
  attach(conn: LLMConnection, call: CallSession, mediaWs: MediaWebSocket): Promise<void>;
}
```

### call-engine

- `voice-agent-client` 모듈에 `prewarm()`, `attach()` 두 메서드 추가
- `ari-handler.initiateOutboundCall` 에 prewarm hook 삽입
- `handleOutboundAgentCall` 에서 기존 직접 호출 대신 attach 사용

## 단계적 출시

1. SDK 양쪽 인터페이스 + 단위 테스트 (P 만, prebuffer=false)
2. 비용 실측: prebuffer=true 로 staging 통화 100건, idle 과금 + greeting inference 비용 측정
3. 결과에 따라 prod 트래픽의 일부 (10%) 에 P+B 활성, latency / 비용 A/B
4. 전면 활성

### 측정 절차 (Phase 4)

```bash
# variant A: prewarm on
python scripts/measure_prewarm_cost.py --runs 100 --variant prewarm_on --to +8210XXXXXXXX

# variant B: prewarm off (baseline)
python scripts/measure_prewarm_cost.py --runs 100 --variant prewarm_off --to +8210XXXXXXXX
```

스크립트는 `[PREWARM-T]` 로그를 파싱하여 다음을 출력한다:
- `first_audio_latency_ms` (p50/p95) — outbound_ready → first audio chunk emit
- `prewarm_duration_ms` (p50/p95) — prewarm WS handshake + session.update + (옵션) response.create
- `status_distribution` — answered / no_answer / busy / rejected

OpenAI / Gemini 토큰 사용량은 각 콘솔의 dashboard 에서 별도 확인.
`prewarm_enabled=False` 로 통화 단위 off 가능 (ClawOpsAgent 옵션).

## Open Questions

- OpenAI Realtime 의 idle 세션 (audio consume 0bytes) 분당 과금 정책 — Anthropic Discord/docs/sales 확인 필요
- Gemini Live 동일 정책
- greeting 길이 상한 (예: 2.5s) 을 두고 초과 시 큐잉 중단할지 — barge-in / 어색한 burst 회피
