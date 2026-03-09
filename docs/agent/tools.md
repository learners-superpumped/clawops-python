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

## 내장 Tool: hang_up

`hang_up`은 자동으로 등록되는 내장 Tool입니다. AI가 대화가 끝났다고 판단하면 자동으로 전화를 종료합니다.
