# Tool (함수 호출)

`@agent.tool` 데코레이터로 AI가 호출할 수 있는 함수를 등록합니다.

## 기본 사용법

```python
@agent.tool
async def check_order(order_id: str) -> str:
    """주문 상태를 확인합니다.

    고객이 주문 번호를 말하면 이 함수를 호출하세요.
    """
    order = await db.get_order(order_id)
    return f"주문 {order_id}는 {order.status} 상태입니다."
```

## 작성 규칙

- 함수는 반드시 `async`여야 합니다
- 반환 타입은 `str`이어야 합니다
- **docstring이 AI에게 함수 설명으로 전달됩니다** — 상세하게 작성하세요
- 파라미터 타입 힌트(`str`, `int`, `float`, `bool`)가 자동으로 JSON Schema로 변환됩니다
- 기본값이 있는 파라미터는 optional로 처리됩니다

```python
@agent.tool
async def search_products(
    query: str,            # required
    category: str = "",    # optional
    limit: int = 10,       # optional
) -> str:
    """상품을 검색합니다. 고객이 상품을 찾을 때 사용하세요."""
    results = await product_api.search(query, category, limit)
    return "\n".join(f"- {r.name}: {r.price}원" for r in results)
```

---

## 내장 Tool (Built-in Tools)

Agent는 통화 제어를 위한 내장 도구를 기본 제공합니다. `BuiltinTool`을 사용해 어떤 내장 도구를 활성화할지 제어할 수 있습니다.

### 내장 도구 목록

| 도구           | 상수                       | 설명                                                                           |
| :------------- | :------------------------- | :----------------------------------------------------------------------------- |
| `hang_up`      | `BuiltinTool.HANG_UP`      | 전화를 종료합니다. AI가 대화 완료를 판단하면 자동으로 호출합니다.              |
| `collect_dtmf` | `BuiltinTool.COLLECT_DTMF` | 사용자의 키패드(DTMF) 입력을 수집합니다. 본인 인증, 메뉴 선택 등에 사용합니다. |
| `send_dtmf`    | `BuiltinTool.SEND_DTMF`    | DTMF 신호를 전송합니다. ARS 메뉴 탐색, 내선번호 입력 등에 사용합니다.          |

### 선택 상수

| 상수               | 설명                               |
| :----------------- | :--------------------------------- |
| `BuiltinTool.ALL`  | 모든 내장 도구 활성화 **(기본값)** |
| `BuiltinTool.NONE` | 모든 내장 도구 비활성화            |

### 사용법

```python
from clawops.agent import ClawOpsAgent, BuiltinTool

# 기본: 모든 내장 도구 활성화
agent = ClawOpsAgent(
    from_="07012341234",
    session=session,
)

# 명시적으로 전부 활성화 (위와 동일)
agent = ClawOpsAgent(
    from_="07012341234",
    session=session,
    builtin_tools=BuiltinTool.ALL,
)

# 내장 도구 전부 비활성화 (커스텀 도구만 사용)
agent = ClawOpsAgent(
    from_="07012341234",
    session=session,
    builtin_tools=BuiltinTool.NONE,
)

# hang_up만 사용 (DTMF 도구 제외)
agent = ClawOpsAgent(
    from_="07012341234",
    session=session,
    builtin_tools=[BuiltinTool.HANG_UP],
)

# DTMF만 사용, hang_up 제외 (AI가 전화를 끊지 못하게)
agent = ClawOpsAgent(
    from_="07012341234",
    session=session,
    builtin_tools=[BuiltinTool.COLLECT_DTMF, BuiltinTool.SEND_DTMF],
)
```

### 활용 예시

**ARS 아웃바운드 봇** — 발신 후 ARS를 탐색해야 하므로 `SEND_DTMF`만 필요:

```python
agent = ClawOpsAgent(
    from_="07012341234",
    session=session,
    builtin_tools=[BuiltinTool.HANG_UP, BuiltinTool.SEND_DTMF],
)
```

**고객 인증 봇** — 고객이 주민번호 뒤 자리를 키패드로 입력:

```python
agent = ClawOpsAgent(
    from_="07012341234",
    session=session,
    builtin_tools=[BuiltinTool.HANG_UP, BuiltinTool.COLLECT_DTMF],
)
```

**단순 안내 봇** — 통화 종료만 가능하면 충분:

```python
agent = ClawOpsAgent(
    from_="07012341234",
    session=session,
    builtin_tools=[BuiltinTool.HANG_UP],
)
```
