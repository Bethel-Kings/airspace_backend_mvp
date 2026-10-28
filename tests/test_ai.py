import asyncio
from types import SimpleNamespace

from app import ai


class FakeClient:
    def __init__(self, text="hi there", fail=False):
        self.calls = {}
        self.fail = fail
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._chat))
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self._tx))

    async def _chat(self, **kw):
        if self.fail:
            raise RuntimeError("boom with secret text")
        self.calls["chat"] = kw
        msg = SimpleNamespace(content="  a reply  ")
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    async def _tx(self, **kw):
        if self.fail:
            raise RuntimeError("boom")
        self.calls["tx"] = kw
        return SimpleNamespace(text="  spoken words ")


def run(coro):
    return asyncio.run(coro)


def test_chat_reply_builds_prompt_and_keeps_history(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(ai.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(ai, "_client", lambda: fake)
    history = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}, {"role": "user", "content": "c"}]
    result = run(ai.generate_chat_reply(history, "practical"))
    assert (result.text, result.status) == ("a reply", "success")
    sent = fake.calls["chat"]["messages"]
    assert sent[0]["role"] == "system" and "not a therapist" in sent[0]["content"]
    assert "ongoing conversation" in sent[0]["content"] and "small, optional next steps" in sent[0]["content"]
    assert sent[1:] == history


def test_provider_failure_returns_generic_fallback_without_leaking(monkeypatch):
    monkeypatch.setattr(ai.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(ai, "_client", lambda: FakeClient(fail=True))
    result = run(ai.generate_chat_reply([{"role": "user", "content": "x"}], "gentle"))
    assert result.status == "fallback" and "boom" not in result.text
    assert run(ai.transcribe_audio(b"1", "webm", "audio/webm", None)).status == "fallback"


def test_transcribe_uses_safe_filename_and_language(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(ai.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(ai, "_client", lambda: fake)
    out = run(ai.transcribe_audio(b"abc", "m4a", "audio/mp4", "ig"))
    assert out.text == "spoken words" and out.status == "success"
    call = fake.calls["tx"]
    assert call["file"][0] == "audio.m4a" and call["language"] == "ig"
    assert call["model"] == ai.settings.openai_transcribe_model
    run(ai.transcribe_audio(b"abc", "webm", None, None))
    assert "language" not in fake.calls["tx"]
