# tests/agent/test_session_protocol.py
"""Session Protocol 구현 검증."""
from clawops.agent.pipeline._base import Session
from clawops.agent.pipeline._openai_realtime import OpenAIRealtime
from clawops.agent.pipeline._gemini_realtime import GeminiRealtime
from clawops.agent.pipeline._pipeline_session import PipelineSession


def test_openai_realtime_is_session():
    session = OpenAIRealtime(api_key="sk-test")
    assert isinstance(session, Session)


def test_gemini_realtime_is_session():
    session = GeminiRealtime(api_key="AIza-test")
    assert isinstance(session, Session)


def test_pipeline_session_is_session():
    """PipelineSession도 Session Protocol을 만족하는지 확인."""

    class FakeSTT:
        async def transcribe(self, audio_stream):
            yield  # pragma: no cover

    class FakeLLM:
        async def generate(self, messages, tools=None):
            yield  # pragma: no cover

    class FakeTTS:
        async def synthesize(self, text_stream):
            yield  # pragma: no cover

    session = PipelineSession(stt=FakeSTT(), llm=FakeLLM(), tts=FakeTTS())
    assert isinstance(session, Session)


def test_session_protocol_has_feed_dtmf():
    """Session 프로토콜에 feed_dtmf 메서드가 정의되어 있는지 확인."""
    from clawops.agent.pipeline._base import Session
    assert hasattr(Session, "feed_dtmf")
