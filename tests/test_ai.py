import asyncio

import httpx
from types import SimpleNamespace

from app import ai


class FakeClient:
    def __init__(self, text="  a reply  ", fail=False):
        self.calls = {}
        self.text = text
        self.fail = fail
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._chat))

    async def _chat(self, **kw):
        if self.fail:
            raise RuntimeError("boom with secret text")
        self.calls["chat"] = kw
        msg = SimpleNamespace(content=self.text)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def run(coro):
    return asyncio.run(coro)


def test_chat_reply_builds_prompt_and_keeps_history(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(ai.settings, "groq_api_key", "groq-test")
    monkeypatch.setattr(ai, "_groq_client", lambda: fake)
    history = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}, {"role": "user", "content": "c"}]
    result = run(ai.generate_chat_reply(history, "practical"))
    assert (result.text, result.status) == ("a reply", "success")
    sent = fake.calls["chat"]["messages"]
    assert sent[0]["role"] == "system" and "not a therapist" in sent[0]["content"]
    assert "ongoing conversation" in sent[0]["content"] and "small, optional next steps" in sent[0]["content"]
    assert sent[1:] == history
    assert fake.calls["chat"]["model"] == ai.settings.groq_model
    assert fake.calls["chat"]["reasoning_effort"] == "low"
    assert fake.calls["chat"]["include_reasoning"] is False
    assert "extra_body" not in fake.calls["chat"]


def test_empty_groq_reply_falls_back_with_reasoning_headroom(monkeypatch):
    fake = FakeClient(text="")
    monkeypatch.setattr(ai.settings, "groq_api_key", "groq-test")
    monkeypatch.setattr(ai, "_groq_client", lambda: fake)
    result = run(ai.generate_chat_reply([{"role": "user", "content": "x"}], "gentle"))
    assert result.status == "fallback" and result.text == ai.GENERIC_FALLBACK
    assert fake.calls["chat"]["max_completion_tokens"] == 1024


def test_provider_failure_returns_generic_fallback_without_leaking(monkeypatch):
    monkeypatch.setattr(ai.settings, "groq_api_key", "groq-test")
    monkeypatch.setattr(ai.settings, "elevenlabs_api_key", "xi-test")
    monkeypatch.setattr(ai, "_groq_client", lambda: FakeClient(fail=True))
    monkeypatch.setattr(ai, "_transcribe_client", lambda: _stt_client(lambda req: httpx.Response(500)))
    result = run(ai.generate_chat_reply([{"role": "user", "content": "x"}], "gentle"))
    assert result.status == "fallback" and "boom" not in result.text
    assert run(ai.transcribe_audio(b"1", "webm", "audio/webm", None)).status == "fallback"


def _stt_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.elevenlabs.io",
                             headers={"xi-api-key": "xi-test"})


def test_transcribe_sends_scribe_request_and_safe_filename(monkeypatch):
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        return httpx.Response(200, json={"text": "  spoken words ", "language_code": "eng"})

    monkeypatch.setattr(ai.settings, "elevenlabs_api_key", "xi-test")
    monkeypatch.setattr(ai, "_transcribe_client", lambda: _stt_client(handler))
    out = run(ai.transcribe_audio(b"abc", "m4a", "audio/mp4", "ig"))
    assert (out.text, out.status) == ("spoken words", "success")
    req = seen[0]
    body = req.content.decode("latin-1")
    assert req.url.path == "/v1/speech-to-text" and req.headers["xi-api-key"] == "xi-test"
    assert 'filename="audio.m4a"' in body and ai.settings.elevenlabs_stt_model in body
    assert 'name="language_code"' in body and "ig" in body and "tag_audio_events" in body


def test_transcribe_omits_language_when_not_given(monkeypatch):
    seen = []
    monkeypatch.setattr(ai.settings, "elevenlabs_api_key", "xi-test")
    monkeypatch.setattr(ai, "_transcribe_client", lambda: _stt_client(lambda r: (seen.append(r), httpx.Response(200, json={"text": "ok"}))[1]))
    run(ai.transcribe_audio(b"abc", "webm", None, None))
    assert "language_code" not in seen[0].content.decode("latin-1")


def test_transcribe_retries_without_language_hint_if_rejected(monkeypatch):
    seen = []

    def handler(req):
        seen.append(req.content.decode("latin-1"))
        return httpx.Response(422, json={}) if "language_code" in seen[-1] else httpx.Response(200, json={"text": "hello"})

    monkeypatch.setattr(ai.settings, "elevenlabs_api_key", "xi-test")
    monkeypatch.setattr(ai, "_transcribe_client", lambda: _stt_client(handler))
    out = run(ai.transcribe_audio(b"abc", "webm", None, "xx"))
    assert (out.text, out.status) == ("hello", "success") and len(seen) == 2


def test_clients_target_the_right_providers(monkeypatch):
    monkeypatch.setattr(ai.settings, "deepseek_api_key", "ds-key")
    monkeypatch.setattr(ai.settings, "groq_api_key", "groq-key")
    monkeypatch.setattr(ai.settings, "elevenlabs_api_key", "xi-key")
    ds, groq, el = ai._client(), ai._groq_client(), ai._transcribe_client()
    assert "deepseek.com" in str(ds.base_url) and ds.api_key == "ds-key"
    assert "api.groq.com/openai/v1" in str(groq.base_url) and groq.api_key == "groq-key"
    assert "elevenlabs.io" in str(el.base_url) and el.headers["xi-api-key"] == "xi-key"


def test_unavailable_without_keys(monkeypatch):
    monkeypatch.setattr(ai.settings, "deepseek_api_key", None)
    monkeypatch.setattr(ai.settings, "groq_api_key", None)
    monkeypatch.setattr(ai.settings, "elevenlabs_api_key", None)
    assert run(ai.generate_chat_reply([{"role": "user", "content": "x"}], "gentle")).status == "unavailable"
    assert run(ai.transcribe_audio(b"1", "webm", None, None)).status == "unavailable"
