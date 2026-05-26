"""staging 환경에서 prewarm A/B 측정.

사용법:
    python scripts/measure_prewarm_cost.py --runs 100 --variant prewarm_on
    python scripts/measure_prewarm_cost.py --runs 100 --variant prewarm_off

출력:
    - p50/p95 first-speech latency (PREWARM-T first-audio 로그 기준)
    - ARI 결과 분포 (answered / no_answer / busy / rejected)
    - 통화당 평균 prewarm 소요 시간 (variant=prewarm_on 만)

본 스크립트는 staging 환경에서 ClawOpsAgent.call() 을 N번 호출하고
로그를 파싱하여 통계를 산출한다. 실제 LLM 토큰 사용량은 OpenAI/Gemini
콘솔에서 별도 확인이 필요하다.

전제:
    - CLAWOPS_API_KEY, CLAWOPS_ACCOUNT_ID, OPENAI_API_KEY 환경변수 설정
    - --to 는 응답 가능한 staging 테스트 번호여야 함
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import statistics
import time
from typing import Any

# stdout 로그 캡처를 위한 핸들러
_log_records: list[str] = []


class _CaptureHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if "[PREWARM-T]" in msg:
            _log_records.append(f"{time.monotonic():.3f} {msg}")


def _setup_logging() -> None:
    handler = _CaptureHandler()
    handler.setLevel(logging.INFO)
    logging.getLogger("clawops.agent").addHandler(handler)
    logging.getLogger("clawops.agent").setLevel(logging.INFO)


async def _run_one_call(to: str, prewarm_enabled: bool, timeout: int = 60) -> dict[str, Any]:
    """한 통화 실행 → 결과 dict 리턴."""
    from clawops.agent import ClawOpsAgent
    from clawops.agent.pipeline.realtime._openai import OpenAIRealtime

    session = OpenAIRealtime(
        api_key=os.environ["OPENAI_API_KEY"],
        system_prompt="너는 친절한 테스트 도우미야. 짧게 인사하고 끝내라.",
        greeting=True,
    )
    agent = ClawOpsAgent(
        from_=os.environ["CLAWOPS_FROM_NUMBER"],
        session=session,
        prewarm_enabled=prewarm_enabled,
    )

    t_start = time.monotonic()
    call_id = None
    status = "unknown"
    try:
        call = await agent.call(to, timeout=timeout)
        call_id = call.call_id
        # 통화 종료 대기 (간단히 60초 sleep — staging 의 자동 hangup 가정)
        await asyncio.wait_for(_wait_for_end(call), timeout=timeout + 10)
        status = call.status
    except Exception as e:
        status = f"error:{type(e).__name__}"
    finally:
        await agent.disconnect()

    elapsed = time.monotonic() - t_start
    return {
        "call_id": call_id,
        "status": status,
        "elapsed_s": elapsed,
        "prewarm_enabled": prewarm_enabled,
    }


async def _wait_for_end(call: Any) -> None:
    while call.status not in ("ended", "failed", "no-answer", "busy", "rejected"):
        await asyncio.sleep(0.5)


def _parse_prewarm_latencies(call_id: str) -> dict[str, float]:
    """PREWARM-T 로그에서 한 call_id 의 timing 추출."""
    times: dict[str, float] = {}
    for line in _log_records:
        if call_id not in line:
            continue
        if " start " in line:
            times["start"] = float(line.split()[0])
        elif " done " in line:
            # elapsed_ms=NNN 파싱
            parts = line.split("elapsed_ms=")
            if len(parts) > 1:
                times["done_elapsed_ms"] = float(parts[1].split()[0])
        elif " attach " in line:
            times["attach"] = float(line.split()[0])
        elif " first-audio " in line:
            times["first_audio"] = float(line.split()[0])
    return times


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = int(round(pct / 100 * (len(sorted_vals) - 1)))
    return sorted_vals[k]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=100)
    ap.add_argument("--variant", choices=["prewarm_on", "prewarm_off"], required=True)
    ap.add_argument("--to", required=True, help="staging 테스트 수신 번호")
    ap.add_argument("--concurrency", type=int, default=1)
    args = ap.parse_args()

    _setup_logging()
    prewarm_enabled = args.variant == "prewarm_on"

    results: list[dict[str, Any]] = []
    sem = asyncio.Semaphore(args.concurrency)

    async def _bounded_call() -> None:
        async with sem:
            r = await _run_one_call(args.to, prewarm_enabled)
            results.append(r)

    await asyncio.gather(*[_bounded_call() for _ in range(args.runs)])

    # 집계
    status_counts: dict[str, int] = {}
    first_audio_latencies: list[float] = []
    prewarm_durations: list[float] = []
    for r in results:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
        if r.get("call_id"):
            times = _parse_prewarm_latencies(r["call_id"])
            if "start" in times and "first_audio" in times:
                first_audio_latencies.append((times["first_audio"] - times["start"]) * 1000)
            if "done_elapsed_ms" in times:
                prewarm_durations.append(times["done_elapsed_ms"])

    summary = {
        "variant": args.variant,
        "runs": args.runs,
        "status_distribution": status_counts,
        "first_audio_latency_ms": {
            "p50": _percentile(first_audio_latencies, 50),
            "p95": _percentile(first_audio_latencies, 95),
            "n": len(first_audio_latencies),
        },
        "prewarm_duration_ms": {
            "p50": _percentile(prewarm_durations, 50),
            "p95": _percentile(prewarm_durations, 95),
            "n": len(prewarm_durations),
        },
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
