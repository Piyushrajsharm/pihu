import config
from llm.groq_llm import GroqLLM


class FakeResponse:
    def __init__(self, payload=None, lines=None, error=None):
        self.payload = payload or {}
        self.lines = lines or []
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error
        return None

    def json(self):
        return self.payload

    def iter_lines(self):
        return iter(self.lines)


class FakeSession:
    def __init__(self, post_error=None):
        self.post_error = post_error
        self.posts = []
        self.gets = []

    def get(self, url, **kwargs):
        self.gets.append({"url": url, **kwargs})
        return FakeResponse({"data": [{"id": "llama-3.1-8b-instant"}]})

    def post(self, url, **kwargs):
        self.posts.append({"url": url, **kwargs})
        if kwargs.get("stream"):
            return FakeResponse(
                lines=[
                    b'data: {"choices":[{"delta":{"content":"namaste"}}]}',
                    b"data: [DONE]",
                ]
            )
        return FakeResponse({"choices": [{"message": {"content": "batch ok"}}]}, error=self.post_error)


def test_groq_llm_is_unavailable_without_key(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "")

    llm = GroqLLM()

    assert llm.is_available is False
    assert llm.health_check()["available"] is False
    assert llm.generate("hello", stream=False) is None


def test_groq_llm_batch_uses_openai_compatible_chat_endpoint(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(config, "GROQ_MODEL", "llama-3.1-8b-instant")
    llm = GroqLLM()
    llm._session = FakeSession()

    result = llm.generate("hello", system_prompt="system", stream=False)

    assert result == "batch ok"
    request = llm._session.posts[0]
    assert request["url"].endswith("/chat/completions")
    assert request["headers"]["Authorization"] == "Bearer test-key"
    assert request["json"]["model"] == "llama-3.1-8b-instant"
    assert request["json"]["messages"][0] == {"role": "system", "content": "system"}
    assert request["json"]["messages"][-1] == {"role": "user", "content": "hello"}


def test_groq_llm_stream_parses_sse_chunks(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "test-key")
    llm = GroqLLM()
    llm._session = FakeSession()

    text = "".join(llm.generate("hello", stream=True))

    assert text == "namaste"
    assert llm._session.posts[0]["json"]["stream"] is True


def test_groq_llm_marks_chat_auth_failure_unavailable(monkeypatch):
    import requests

    monkeypatch.setattr(config, "GROQ_API_KEY", "bad-key")
    llm = GroqLLM()
    llm._session = FakeSession(
        post_error=requests.exceptions.HTTPError("401 Client Error: Unauthorized")
    )

    assert llm.generate("hello", stream=False) is None
    assert llm.is_available is False
