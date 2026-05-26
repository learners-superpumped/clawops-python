"""prewarm → attach end-to-end 통합 smoke test."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clawops.agent.pipeline._buffering_call import _BufferingCall
from clawops.agent.pipeline.realtime._openai import OpenAIRealtime


def _make_mock_connection() -> MagicMock:
    conn = MagicMock()
    conn.session = MagicMock()
    conn.session.update = AsyncMock()
    conn.response = MagicMock()
    conn.response.create = AsyncMock()
    conn.close = AsyncMock()

    async def _aiter():
        if False:
            yield None
        return

    conn.__aiter__ = lambda self_: _aiter()
    return conn


@pytest.mark.asyncio
async def test_outbound_ready_to_attach_full_flow() -> None:
    """outbound_ready → prewarm 시작 → media WS 연결 → attach → audio flush."""
    mock_conn = _make_mock_connection()

    sess = OpenAIRealtime(api_key="sk-test", greeting=True)
    with patch.object(sess, "_open_connection", new=AsyncMock(return_value=mock_conn)):
        await sess.prewarm()
        # prewarm 직후 BufferingCall 상태
        assert isinstance(sess._call, _BufferingCall)
        # 가상 audio delta 시뮬레이션 (수동으로 BufferingCall 에 누적)
        await sess._call.send_audio(b"greeting1")
        await sess._call.send_audio(b"greeting2")

        real_call = MagicMock()
        real_call.send_audio = AsyncMock()
        real_call._emit = AsyncMock()
        real_call.metrics = MagicMock()
        await sess.attach(real_call)
        # 누적된 greeting 이 flush 되어야 함
        assert real_call.send_audio.await_count == 2
        real_call.send_audio.assert_any_await(b"greeting1")
        real_call.send_audio.assert_any_await(b"greeting2")
    await sess.stop()
