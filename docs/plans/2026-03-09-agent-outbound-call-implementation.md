# Agent Outbound Call Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Agent SDK에 `agent.call(to)` 발신 기능을 추가하고, 서버에서 Agent 모드 발신을 지원한다.

**Architecture:** REST API로 발신 요청(Url 없이) → 서버가 Agent 모드 감지 → ARI originate → 상대방 수신 시 media WS 생성 → Control WS로 agent에게 mediaUrl 전달 → 기존 RealtimeSession 재사용.

**Tech Stack:** Python (aiohttp), Node.js (Express + ARI), Asterisk PJSIP

---

### Task 1: 서버 — REST API Agent 모드 분기

`POST /calls`에서 Url 없이 호출 시 Agent 모드로 분기한다. From 번호에 agent가 연결되어 있지 않으면 409 에러.

**Files:**
- Modify: `/Users/ghyeok/Developments/clawops/app/src/voice-api-server.js:107-180`

**Step 1: Url 필수 검증 제거 + Agent 모드 분기**

현재 코드 (L112):
```javascript
if (!To || !From || !Url) {
  return res.status(400).json({ error: 'To, From, Url은 필수입니다' });
}
```

변경:
```javascript
if (!To || !From) {
  return res.status(400).json({ error: 'To, From은 필수입니다' });
}

// Agent 모드: Url 없이 호출 시 From 번호에 연결된 agent 필요
const isAgentMode = !Url;
if (isAgentMode) {
  if (!agentRegistry || !agentRegistry.has(From)) {
    return res.status(409).json({ error: 'From 번호에 연결된 Agent가 없습니다' });
  }
}
```

**Step 2: Agent 모드 메타데이터 저장**

`saveCallLog` 호출 시 `voiceUrl` 대신 agent 모드 표시. 기존 L138-145 수정:
```javascript
await db.saveCallLog({
  callId, accountId,
  fromNumber: From, toNumber: To,
  direction: 'outbound', status: 'queued',
  voiceUrl: Url || '__agent__',  // Agent 모드 표시
  statusCallback: StatusCallback || null,
  statusCallbackEvents: StatusCallbackEvent || 'initiated ringing answered completed',
});
```

**Step 3: initiateOutboundCall에 Agent 모드 전달**

기존 L158-164 수정:
```javascript
await initiateOutboundCall({
  callId, to: To, from: From,
  voiceUrl: Url || '__agent__',
  statusCallback: StatusCallback,
  statusCallbackEvents: StatusCallbackEvent,
  accountId, signingKey,
  timeout: parseInt(req.body.Timeout) || 60,
});
```

**Step 4: 테스트**

서버를 로컬에서 실행 후:
```bash
# Agent 모드 — agent 미연결 시 409
curl -X POST http://localhost:3000/v1/accounts/AC.../calls \
  -H "Authorization: Bearer ..." \
  -H "Content-Type: application/json" \
  -d '{"To":"01012345678","From":"07012345678"}'
# Expected: 409 {"error":"From 번호에 연결된 Agent가 없습니다"}

# 기존 모드 — Url 있으면 기존대로 동작
curl -X POST http://localhost:3000/v1/accounts/AC.../calls \
  -H "Authorization: Bearer ..." \
  -H "Content-Type: application/json" \
  -d '{"To":"01012345678","From":"07012345678","Url":"https://example.com/voiceml"}'
# Expected: 201
```

**Step 5: Commit**

```bash
git add app/src/voice-api-server.js
git commit -m "feat: add agent mode branching for POST /calls (Url optional)"
```

---

### Task 2: 서버 — ARI에서 Agent 모드 발신 처리

상대방이 수신하면 webhook 대신 media WS를 생성하고 Control WS로 agent에게 알린다. 또한 ringing/failed 상태를 Control WS로 전달한다.

**Files:**
- Modify: `/Users/ghyeok/Developments/clawops/app/src/ari-handler.js:9,19-70,78-92,123-155`
- Modify: `/Users/ghyeok/Developments/clawops/app/src/call-handler.js:598-661`

**Step 1: outboundRegistry에 agent 관련 파라미터 추가**

`ari-handler.js` L148-152에서 `timeout` 저장:
```javascript
outboundRegistry.set(channel.id, {
  callId, to, from, voiceUrl, statusCallback,
  statusCallbackEvents, accountId, signingKey,
  ringingSent: false,
  timeout: opts.timeout || 60,
});
```

`initiateOutboundCall` 함수 시그니처에 `timeout` 추가 (L123):
```javascript
async function initiateOutboundCall({ callId, to, from, voiceUrl, statusCallback,
                                      statusCallbackEvents, accountId, signingKey, timeout }) {
```

**Step 2: ChannelStateChange에서 Agent에 ringing 알림**

`ari-handler.js` L19-39, ringing 감지 후 agent에게도 알림:
```javascript
client.on('ChannelStateChange', async (event, channel) => {
  try {
    const meta = outboundRegistry.get(channel.id);
    if (!meta) return;

    if ((channel.state === 'Ring' || channel.state === 'Ringing') && !meta.ringingSent) {
      meta.ringingSent = true;
      await sendStatusCallback({
        statusCallback: meta.statusCallback,
        statusCallbackEvents: meta.statusCallbackEvents,
        callId: meta.callId, accountId: meta.accountId,
        callStatus: 'ringing', direction: 'outbound',
        signingKey: meta.signingKey,
      });
      await db.updateCallStatus({ callId: meta.callId, status: 'ringing' });

      // Agent 모드면 Control WS로 ringing 알림
      if (meta.voiceUrl === '__agent__' && agentRegistry && agentRegistry.has(meta.from)) {
        const agentEntry = agentRegistry.get(meta.from);
        try {
          agentEntry.ws.send(JSON.stringify({
            event: 'call.ringing', callId: meta.callId,
          }));
        } catch (err) {
          console.error(`[Agent] call.ringing 전송 실패: ${err.message}`);
        }
      }
    }
  } catch (err) {
    console.error(`[ARI] ChannelStateChange 처리 오류: ${err.message}`);
  }
});
```

**Step 3: ChannelDestroyed에서 Agent에 failed 알림**

`ari-handler.js` L42-70, 기존 코드 끝에 agent 알림 추가:
```javascript
// 기존 sendStatusCallback 후에 추가:
// Agent 모드면 Control WS로 실패 알림
if (meta.voiceUrl === '__agent__' && agentRegistry && agentRegistry.has(meta.from)) {
  const agentEntry = agentRegistry.get(meta.from);
  try {
    agentEntry.ws.send(JSON.stringify({
      event: 'call.failed', callId: meta.callId, reason: status,
    }));
  } catch (err) {
    console.error(`[Agent] call.failed 전송 실패: ${err.message}`);
  }
}
```

**Step 4: StasisStart에서 Agent 모드 분기**

`ari-handler.js` L78-92, outbound StasisStart 핸들러 수정:
```javascript
if (args[0] === 'outbound') {
  const meta = outboundRegistry.get(channel.id);
  if (meta) {
    outboundRegistry.delete(channel.id);
    try {
      if (meta.voiceUrl === '__agent__') {
        // Agent 모드 — media WS 생성 + Control WS 알림
        await handleOutboundAgentCall({
          channel, client, db, audioSocketServer,
          agentRegistry, agentMediaTokens, waitForAgentMediaWs,
          ...meta,
        });
      } else {
        // 기존 모드 — VoiceML webhook
        await handleOutboundCall({ channel, client, db, audioSocketServer, ...meta });
      }
    } catch (err) {
      console.error(`[ARI] 발신 통화 처리 오류: ${err.message}`);
      channel.hangup().catch(() => {});
    }
  } else {
    channel.hangup().catch(() => {});
  }
  return;
}
```

**Step 5: handleOutboundAgentCall 함수 추가**

`call-handler.js`에 새 함수 추가 (handleInboundCall의 agent 처리 로직을 재사용). L661 직전에 추가:

```javascript
async function handleOutboundAgentCall({ channel, client, db, audioSocketServer,
                                          agentRegistry, agentMediaTokens, waitForAgentMediaWs,
                                          callId, from, to, accountId, signingKey,
                                          statusCallback, statusCallbackEvents }) {
  console.log(`[Call] 발신 응답 (Agent): ${from} → ${to} (${callId})`);
  const startTime = Date.now();

  const callbackOpts = { statusCallback, statusCallbackEvents, callId, accountId, direction: 'outbound', signingKey };
  await sendStatusCallback({ ...callbackOpts, callStatus: 'in-progress' });
  await db.updateCallStatus({ callId, status: 'in-progress' });

  // agentRegistry에서 agent 찾기 (from 번호)
  if (!agentRegistry || !agentRegistry.has(from)) {
    console.error(`[Agent] Agent 연결 없음: ${from}`);
    await channel.hangup().catch(() => {});
    await db.updateCallStatus({ callId, status: 'failed' });
    return;
  }
  const agentEntry = agentRegistry.get(from);

  // 미디어 토큰 생성
  const token = agentMediaTokens.create(callId);
  const host = process.env.API_HOST || 'api.claw-ops.com';
  const scheme = process.env.NODE_ENV === 'production' ? 'wss' : 'ws';
  const mediaUrl = `${scheme}://${host}/v1/agent/media/${callId}?token=${token}`;

  // Agent에 outbound_ready 알림
  try {
    agentEntry.ws.send(JSON.stringify({
      event: 'call.outbound_ready', callId, from, to, mediaUrl,
    }));
  } catch (err) {
    console.error(`[Agent] call.outbound_ready 전송 실패: ${err.message}`);
    await channel.hangup().catch(() => {});
    await db.updateCallStatus({ callId, status: 'failed' });
    return;
  }

  // AudioSocket 설정
  const hex = randomBytes(16).toString('hex');
  const audioUuid = `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;

  const extChannel = await client.channels.externalMedia({
    app: process.env.ASTERISK_APP || 'cpaas-app',
    app_args: 'external',
    external_host: `app:${process.env.AUDIOSOCKET_PORT || 8765}`,
    format: 'slin', encapsulation: 'audiosocket',
    transport: 'tcp', connection_type: 'client', direction: 'both',
    data: audioUuid,
  });
  const mixBridge = await client.bridges.create({ type: 'mixing' });
  await mixBridge.addChannel({ channel: [channel.id, extChannel.id] });

  // Media WS 연결 대기
  let agentMediaWs;
  try {
    agentMediaWs = await waitForAgentMediaWs(callId);
  } catch (err) {
    console.error(`[Agent] Media WS 연결 타임아웃: ${callId}`);
    extChannel.hangup().catch(() => {});
    mixBridge.destroy().catch(() => {});
    await channel.hangup().catch(() => {});
    await db.updateCallStatus({ callId, status: 'failed' });
    return;
  }

  const streamId = 'MZ' + randomBytes(16).toString('hex');
  let seqNum = 0;
  let chunkNum = 0;
  const streamStartTime = Date.now();

  // connected + start 전송
  agentMediaWs.send(JSON.stringify({ event: 'connected', protocol: 'Call', version: '1.0.0' }));
  agentMediaWs.send(JSON.stringify({
    event: 'start',
    sequenceNumber: String(++seqNum),
    start: {
      streamId, callId, accountId,
      tracks: ['inbound'],
      mediaFormat: { encoding: 'audio/x-l16', sampleRate: 8000, channels: 1 },
    },
  }));

  // Agent Media WS → AudioSocket (응답 오디오)
  agentMediaWs.on('message', (raw) => {
    try {
      const msg = JSON.parse(raw.toString());
      if (msg.event === 'media' && msg.media && msg.media.payload) {
        audioSocketServer.sendAudio(audioUuid, Buffer.from(msg.media.payload, 'base64'));
      } else if (msg.event === 'clear') {
        const flushedMarks = audioSocketServer.flushAudio(audioUuid);
        for (const name of flushedMarks) {
          if (agentMediaWs.readyState === 1) {
            agentMediaWs.send(JSON.stringify({
              event: 'mark', sequenceNumber: String(++seqNum), mark: { name },
            }));
          }
        }
      } else if (msg.event === 'mark' && msg.mark && msg.mark.name) {
        audioSocketServer.sendMark(audioUuid, msg.mark.name);
      }
    } catch {}
  });

  // AudioSocket → Agent Media WS (수신 오디오)
  audioSocketServer.addHandler(audioUuid, {
    onAudio: (pcm16) => {
      if (agentMediaWs.readyState !== 1) return;
      chunkNum++;
      agentMediaWs.send(JSON.stringify({
        event: 'media', sequenceNumber: String(++seqNum),
        media: {
          track: 'inbound', chunk: String(chunkNum),
          timestamp: String(Date.now() - streamStartTime),
          payload: pcm16.toString('base64'),
        },
      }));
    },
    onHangup: () => { channel.hangup().catch(() => {}); },
    onMark: (name) => {
      if (agentMediaWs.readyState === 1) {
        agentMediaWs.send(JSON.stringify({
          event: 'mark', sequenceNumber: String(++seqNum), mark: { name },
        }));
      }
    },
  });

  // Cleanup
  let cleaned = false;
  const cleanup = async () => {
    if (cleaned) return;
    cleaned = true;
    if (agentMediaWs.readyState === 1) {
      agentMediaWs.send(JSON.stringify({
        event: 'stop', sequenceNumber: String(++seqNum),
        stop: { accountId, callId },
      }));
      agentMediaWs.close();
    }
    extChannel.hangup().catch(() => {});
    mixBridge.destroy().catch(() => {});
    audioSocketServer.removeHandler(audioUuid);
    const duration = Math.round((Date.now() - startTime) / 1000);
    await db.updateCallStatus({ callId, status: 'completed', duration });
    await sendStatusCallback({ ...callbackOpts, callStatus: 'completed', duration });
    try {
      agentEntry.ws.send(JSON.stringify({ event: 'call.ended', callId, duration }));
    } catch {}
    console.log(`[Agent] 발신 종료: ${callId} (${duration}초)`);
  };

  channel.on('ChannelHangupRequest', cleanup);
  channel.on('ChannelDestroyed', cleanup);
  agentMediaWs.on('close', () => { channel.hangup().catch(() => {}); });
}
```

**Step 6: module.exports 업데이트**

`call-handler.js` L661:
```javascript
module.exports = { handleInboundCall, handleOutboundCall, handleOutboundAgentCall, sendStatusCallback };
```

`ari-handler.js` L2:
```javascript
const { handleInboundCall, handleOutboundCall, handleOutboundAgentCall, sendStatusCallback } = require('./call-handler');
```

`startAriHandler` 함수에 `agentMediaTokens`, `waitForAgentMediaWs` 파라미터 전달 확인 (이미 있음, L9).

**Step 7: Commit**

```bash
git add app/src/ari-handler.js app/src/call-handler.js
git commit -m "feat: add handleOutboundAgentCall for agent mode outbound calls"
```

---

### Task 3: 서버 — Swagger 문서 업데이트

**Files:**
- Modify: `/Users/ghyeok/Developments/clawops/app/src/swagger/voice-spec.js:116-169`

**Step 1: POST /calls 스키마 수정**

L133-134에서 `required`를 `['To', 'From']`으로 변경 (Url 제거):
```javascript
required: ['To', 'From'],
```

L137의 Url 설명 수정:
```javascript
Url: { type: 'string', example: 'https://my-app.com/voiceml', description: '통화 연결 시 VoiceML을 반환할 URL. 생략 시 From 번호에 연결된 Agent로 통화가 연결됩니다 (Agent 모드).' },
```

Timeout 파라미터 추가 (L139 뒤):
```javascript
Timeout: { type: 'integer', example: 60, description: '발신 타임아웃 (초). Agent 모드에서 상대방이 응답하지 않을 때 대기 시간. 기본값: 60' },
```

`application/x-www-form-urlencoded` 스키마도 동일하게 수정 (L146의 required, Url 설명, Timeout 추가).

**Step 2: 409 에러 응답 추가**

L166 뒤에:
```javascript
409: { description: 'From 번호에 연결된 Agent가 없습니다 (Url 미지정 시)', content: { 'application/json': { schema: { $ref: '#/components/schemas/Error' } } } },
```

**Step 3: description 업데이트**

L120-122의 description에 Agent 모드 설명 추가:
```javascript
description: '아웃바운드 전화를 발신합니다. From 번호는 계정에 등록된 번호여야 합니다.\n\n'
  + '**PSTN 발신**: To에 전화번호를 입력하면 통신사 트렁크를 통해 일반 전화로 발신됩니다.\n'
  + '- 예: `"To": "01012345678"`\n\n'
  + '**Agent 모드**: Url을 생략하면 From 번호에 연결된 Agent SDK로 통화가 연결됩니다.\n'
  + '- Agent가 연결되어 있지 않으면 409 에러를 반환합니다.',
```

**Step 4: Commit**

```bash
git add app/src/swagger/voice-spec.js
git commit -m "docs: update swagger spec for agent mode outbound calls"
```

---

### Task 4: Python SDK — CallSession에 direction, status 추가

**Files:**
- Modify: `/Users/ghyeok/Developments/clawops-python/src/clawops/agent/_session.py:9-23`

**Step 1: direction, status 필드 추가**

```python
class CallSession:
    def __init__(
        self,
        *,
        call_id: str,
        from_number: str,
        to_number: str,
        account_id: str,
        direction: str = "inbound",
    ) -> None:
        self.call_id = call_id
        self.from_number = from_number
        self.to_number = to_number
        self.account_id = account_id
        self.direction = direction
        self.status: str = "queued" if direction == "outbound" else "ringing"
        self.start_time = datetime.now()
        self.metadata: dict[str, Any] = {}
        # ... 나머지 동일
```

**Step 2: 기존 테스트 확인**

```bash
cd /Users/ghyeok/Developments/clawops-python && python -m pytest tests/agent/test_session.py -v
```

**Step 3: Commit**

```bash
git add src/clawops/agent/_session.py
git commit -m "feat: add direction and status fields to CallSession"
```

---

### Task 5: Python SDK — ControlWebSocket에 발신 이벤트 핸들링 추가

**Files:**
- Modify: `/Users/ghyeok/Developments/clawops-python/src/clawops/agent/_control_ws.py:28-98`

**Step 1: 콜백 파라미터 추가**

`__init__`에 새 콜백 추가 (L36-37 뒤):
```python
class ControlWebSocket:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        account_id: str,
        number: str,
        on_call_incoming: Callable[[dict[str, Any]], Awaitable[None]],
        on_call_ended: Callable[[dict[str, Any]], Awaitable[None]],
        on_call_outbound_ready: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        on_call_ringing: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        on_call_failed: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        self._url = build_control_ws_url(base_url=base_url, account_id=account_id, number=number)
        self._api_key = api_key
        self._on_call_incoming = on_call_incoming
        self._on_call_ended = on_call_ended
        self._on_call_outbound_ready = on_call_outbound_ready
        self._on_call_ringing = on_call_ringing
        self._on_call_failed = on_call_failed
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._running = False
```

**Step 2: 이벤트 핸들링 추가**

`connect()` 메서드의 메시지 루프 (L62-71) 수정:
```python
async for msg in self._ws:
    if msg.type == aiohttp.WSMsgType.TEXT:
        data = json.loads(msg.data)
        event = data.get("event")
        if event == "call.incoming":
            await self._on_call_incoming(data)
        elif event == "call.ended":
            await self._on_call_ended(data)
        elif event == "call.outbound_ready" and self._on_call_outbound_ready:
            await self._on_call_outbound_ready(data)
        elif event == "call.ringing" and self._on_call_ringing:
            await self._on_call_ringing(data)
        elif event == "call.failed" and self._on_call_failed:
            await self._on_call_failed(data)
    elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
        break
```

**Step 3: 기존 테스트 확인**

```bash
cd /Users/ghyeok/Developments/clawops-python && python -m pytest tests/agent/test_control_ws.py -v
```

**Step 4: Commit**

```bash
git add src/clawops/agent/_control_ws.py
git commit -m "feat: add outbound call event handlers to ControlWebSocket"
```

---

### Task 6: Python SDK — ClawOpsAgent에 start/stop/call 추가

**Files:**
- Modify: `/Users/ghyeok/Developments/clawops-python/src/clawops/agent/_agent.py:27-224`

**Step 1: listen() 제거, start()/stop() 추가**

기존 `listen()` (L106-111) 제거. 대신:
```python
async def start(self) -> None:
    """비블로킹 — Control WS 연결 + 수신 대기 시작."""
    if self._control_ws is not None:
        return  # 이미 연결됨
    await self._ensure_control_ws()
    log.info(f"ClawOpsAgent started on {self._from_number}")

async def stop(self) -> None:
    """Control WS 닫기 + 활성 세션 정리."""
    if self._control_ws:
        await self._control_ws.close()
        self._control_ws = None
    self._active_sessions.clear()
    log.info("ClawOpsAgent stopped")
```

**Step 2: _ensure_control_ws() 헬퍼**

Control WS가 없으면 자동 연결하는 헬퍼:
```python
async def _ensure_control_ws(self) -> None:
    """Control WS가 없으면 연결한다."""
    if self._control_ws is not None:
        return
    self._control_ws = ControlWebSocket(
        base_url=self._base_url,
        api_key=self._api_key,
        account_id=self._account_id,
        number=self._from_number,
        on_call_incoming=self._handle_incoming,
        on_call_ended=self._handle_ended,
        on_call_outbound_ready=self._handle_outbound_ready,
        on_call_ringing=self._handle_ringing,
        on_call_failed=self._handle_failed,
    )
    self._control_ws_task = asyncio.create_task(self._control_ws.connect())
```

**Step 3: call() 메서드 추가**

```python
async def call(self, to: str, *, timeout: int = 60) -> CallSession:
    """발신 전화를 건다. CallSession을 즉시 리턴 (queued 상태)."""
    await self._ensure_control_ws()

    # REST API로 발신 요청
    import aiohttp as _aiohttp
    url = f"{self._base_url}/v1/accounts/{self._account_id}/calls"
    body = {"To": to, "From": self._from_number, "Timeout": timeout}
    headers = {
        "Authorization": f"Bearer {self._api_key}",
        "Content-Type": "application/json",
    }
    async with _aiohttp.ClientSession() as session:
        async with session.post(url, json=body, headers=headers) as resp:
            if resp.status != 201:
                error = await resp.json()
                raise AgentError(f"발신 실패 ({resp.status}): {error.get('error', '')}")
            data = await resp.json()

    call = CallSession(
        call_id=data["callId"],
        from_number=self._from_number,
        to_number=to,
        account_id=self._account_id,
        direction="outbound",
    )

    for event, handlers in self._event_handlers.items():
        for handler in handlers:
            call.on(event, handler)

    self._active_sessions[call.call_id] = call
    log.info(f"Outbound call initiated: {self._from_number} -> {to} ({call.call_id})")
    return call
```

**Step 4: 발신 이벤트 핸들러 추가**

```python
async def _handle_outbound_ready(self, data: dict[str, Any]) -> None:
    """상대방이 수신 — media WS 연결 + RealtimeSession 시작."""
    call_id = data["callId"]
    media_url = data.get("mediaUrl", "")

    call = self._active_sessions.get(call_id)
    if not call:
        log.warning(f"Unknown outbound call: {call_id}")
        return

    call.status = "in-progress"
    log.info(f"Outbound call answered: {call.from_number} -> {call.to_number} ({call_id})")
    asyncio.create_task(self._start_call_session(call, media_url))

async def _handle_ringing(self, data: dict[str, Any]) -> None:
    call_id = data.get("callId", "")
    call = self._active_sessions.get(call_id)
    if call:
        call.status = "ringing"
        log.info(f"Outbound call ringing: {call_id}")

async def _handle_failed(self, data: dict[str, Any]) -> None:
    call_id = data.get("callId", "")
    reason = data.get("reason", "failed")
    call = self._active_sessions.get(call_id)
    if call:
        call.status = reason
        log.info(f"Outbound call failed: {call_id} ({reason})")
        await call._emit("call_failed", reason)
        self._active_sessions.pop(call_id, None)
```

**Step 5: _run() 메서드 제거**

기존 `_run()` (L113-122)은 `_ensure_control_ws()`로 대체되므로 제거.

**Step 6: _handle_incoming 수정**

기존 `_handle_incoming`에서 CallSession 생성 시 direction 추가:
```python
call = CallSession(
    call_id=call_id,
    from_number=from_number,
    to_number=self._from_number,
    account_id=self._account_id,
    direction="inbound",
)
```

**Step 7: _control_ws_task 관리**

`__init__`에 추가:
```python
self._control_ws_task: asyncio.Task[Any] | None = None
```

`stop()`에서 task 취소:
```python
async def stop(self) -> None:
    if self._control_ws:
        await self._control_ws.close()
        self._control_ws = None
    if self._control_ws_task and not self._control_ws_task.done():
        self._control_ws_task.cancel()
        self._control_ws_task = None
    self._active_sessions.clear()
    log.info("ClawOpsAgent stopped")
```

**Step 8: 기존 테스트 확인**

```bash
cd /Users/ghyeok/Developments/clawops-python && python -m pytest tests/agent/ -v
```

**Step 9: Commit**

```bash
git add src/clawops/agent/_agent.py
git commit -m "feat: replace listen() with start/stop/call for outbound support"
```

---

### Task 7: Python SDK — 문서 업데이트

**Files:**
- Modify: `/Users/ghyeok/Developments/clawops-python/README.md:47,71`
- Modify: `/Users/ghyeok/Developments/clawops-python/docs/agent.md:50,423,510`

**Step 1: README.md 수정**

L47 `agent.listen()` → async 예제로 교체:
```python
async def main():
    await agent.start()
    # 수신 대기 중... (Ctrl+C로 종료)

import asyncio
asyncio.run(main())
```

L71 동일하게 수정.

**Step 2: docs/agent.md 수정**

L50 `agent.listen()` → `await agent.start()` 교체.
L423, L510도 동일.

발신 사용법 섹션 추가:
```markdown
## 발신 (Outbound Call)

`agent.call(to)`로 아웃바운드 전화를 걸 수 있습니다.

```python
async def main():
    agent = ClawOpsAgent(from_="07012345678", system_prompt="...", ...)

    @agent.on("call_start")
    async def on_start(call):
        print(f"통화 시작: {call.call_id} ({call.direction})")

    @agent.on("call_failed")
    async def on_failed(call, reason):
        print(f"발신 실패: {reason}")

    # 발신만 하는 경우 — start() 없이 가능
    call = await agent.call("01012345678", timeout=30)
    print(call.call_id)    # 즉시 사용 가능
    print(call.status)     # "queued"
    print(call.direction)  # "outbound"

    # 수신도 같이 하는 경우
    await agent.start()
    call = await agent.call("01012345678")
```

**Step 3: Commit**

```bash
git add README.md docs/agent.md
git commit -m "docs: update README and agent docs for start/stop/call API"
```

---

### Task 8: 전체 테스트 + 배포

**Step 1: Python SDK 전체 테스트**

```bash
cd /Users/ghyeok/Developments/clawops-python && python -m pytest tests/ -v
```

**Step 2: 서버 배포**

프로덕션 서버에 서버 코드 배포 후 재시작.

**Step 3: SDK 버전 범프**

`/Users/ghyeok/Developments/clawops-python/src/clawops/_version.py`:
```python
__version__ = "0.6.0"
```

**Step 4: End-to-end 테스트**

실제 발신 테스트:
```python
import asyncio
from clawops.agent import ClawOpsAgent

agent = ClawOpsAgent(
    from_="07012345678",
    system_prompt="안녕하세요, 테스트 전화입니다.",
)

@agent.on("call_start")
async def on_start(call):
    print(f"통화 시작: {call.direction}")

@agent.on("call_end")
async def on_end(call):
    print(f"통화 종료")

async def main():
    call = await agent.call("01012345678")
    print(f"발신 요청: {call.call_id} ({call.status})")
    await asyncio.sleep(60)  # 통화 대기
    await agent.stop()

asyncio.run(main())
```

**Step 5: Commit**

```bash
git add src/clawops/_version.py
git commit -m "chore: bump version to 0.6.0 for outbound call support"
```
