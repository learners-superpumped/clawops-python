# 빠른 시작

## 설치

```bash
# 기본 (OpenAI Realtime 모드)
pip install clawops[agent]

# 파이프라인 모드 (특정 프로바이더)
pip install clawops[agent,deepgram,elevenlabs,openai-llm]

# MCP 서버 지원 포함
pip install clawops[agent,mcp]

# 전체 설치
pip install clawops[agent-all]
```

## 환경변수

```bash
export CLAWOPS_API_KEY="sk_..."
export CLAWOPS_ACCOUNT_ID="AC..."
export OPENAI_API_KEY="sk-..."           # OpenAI Realtime
export GOOGLE_API_KEY="..."              # Gemini Realtime
export DEEPGRAM_API_KEY="..."            # Pipeline: DeepgramSTT
export ELEVENLABS_API_KEY="..."          # Pipeline: ElevenLabsTTS
```

## 최소 예제

```python
from clawops.agent import ClawOpsAgent, OpenAIRealtime
import asyncio

agent = ClawOpsAgent(
    from_="07012341234",
    session=OpenAIRealtime(
        system_prompt="친절한 고객센터 상담원입니다.",
    ),
)

asyncio.run(agent.serve())  # Ctrl+C로 종료
```

이것만으로 `07012341234` 번호로 걸려오는 전화를 AI가 처리합니다.

## 설정 옵션

```python
from clawops.agent import ClawOpsAgent, OpenAIRealtime

agent = ClawOpsAgent(
    # 필수
    from_="07012341234",
    session=OpenAIRealtime(
        system_prompt="상담원입니다.",
        voice="marin",                    # marin, ash, ballad, coral, sage, verse
        model="gpt-realtime-1.5",
        language="ko",
        eagerness="high",                 # low, medium, high, auto
        greeting=True,
    ),

    # 인증 (환경변수 대체 가능)
    api_key="sk_...",
    account_id="AC...",

    # 녹음
    recording=True,
    recording_path="./recordings",
)
```

### Gemini Realtime 사용 시

```python
from clawops.agent import ClawOpsAgent, GeminiRealtime

agent = ClawOpsAgent(
    from_="07012341234",
    session=GeminiRealtime(
        system_prompt="상담원입니다.",
        voice="Kore",
        language="ko",
    ),
)
```

### 음성 옵션

| 음성 | 특징 |
|------|------|
| `marin` | 기본값, 자연스러운 여성 음성 |
| `ash` | 자연스러운 남성 음성 |
| `ballad` | 부드러운 남성 음성 |
| `coral` | 밝은 여성 음성 |
| `sage` | 차분한 여성 음성 |
| `verse` | 중성적 음성 |

## 발신 (Outbound Call)

```python
async def main():
    agent = ClawOpsAgent(
        from_="07012345678",
        session=OpenAIRealtime(
            system_prompt="예약 확인 도우미입니다.",
        ),
    )

    # 발신만 하는 경우 — 자동으로 connect() 수행
    session = await agent.call("01012345678", timeout=30)
    print(session.call_id)     # 즉시 사용 가능
    print(session.direction)   # "outbound"
    await session.wait()       # 통화 종료까지 대기
    await agent.disconnect()

    # 수신도 같이 하는 경우 (혼합 모드)
    await agent.connect()
    session = await agent.call("01012345678")
    # agent는 인바운드 수신도 계속 처리

asyncio.run(main())
```

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `to` | `str` | 필수 | 수신 전화번호 |
| `timeout` | `int` | `60` | 무응답 대기 시간 (초) |

## 에러 처리

```python
from clawops.agent import ClawOpsAgent, OpenAIRealtime
from clawops._exceptions import AgentError, AgentConnectionError
import asyncio

agent = ClawOpsAgent(
    from_="07012341234",
    session=OpenAIRealtime(
        system_prompt="상담원입니다.",
    ),
)

async def main():
    try:
        await agent.serve()
    except AgentConnectionError as e:
        print(f"서버 연결 실패: {e}")
    except AgentError as e:
        print(f"에이전트 에러: {e}")

asyncio.run(main())
```

| 에러 | 설명 |
|------|------|
| `AgentError` | Agent 관련 에러의 베이스 클래스 |
| `AgentConnectionError` | WebSocket 연결 실패 |

## 디버그 로깅

```python
import logging
logging.getLogger("clawops.agent").setLevel(logging.DEBUG)
```
