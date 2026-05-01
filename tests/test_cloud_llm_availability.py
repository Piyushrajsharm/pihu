import requests

import config
from llm.cloud_llm import CloudLLM


class FakeResponse:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {}
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, health_error=None, post_error=None):
        self.health_error = health_error
        self.post_error = post_error
        self.gets = []
        self.posts = []

    def get(self, url, **kwargs):
        self.gets.append({"url": url, **kwargs})
        return FakeResponse({"data": []}, error=self.health_error)

    def post(self, url, **kwargs):
        self.posts.append({"url": url, **kwargs})
        return FakeResponse(
            {"choices": [{"message": {"content": "nim ok"}}]},
            error=self.post_error,
        )


def test_cloud_llm_unavailable_without_key(monkeypatch):
    monkeypatch.setattr(config, "NVIDIA_NIM_API_KEY", "")

    llm = CloudLLM()

    assert llm.is_available is False
    assert llm.health_check()["available"] is False
    assert llm.generate("hello", stream=False) is None


def test_cloud_llm_marks_unauthorized_key_unavailable(monkeypatch):
    monkeypatch.setattr(config, "NVIDIA_NIM_API_KEY", "bad-key")
    llm = CloudLLM()
    llm._session = FakeSession(
        health_error=requests.exceptions.HTTPError("401 Client Error: Unauthorized")
    )

    assert llm.is_available is False
    assert llm.generate("hello", stream=False) is None
    assert len(llm._session.gets) == 1
    assert llm._session.posts == []


def test_cloud_llm_batch_runs_after_successful_health_check(monkeypatch):
    monkeypatch.setattr(config, "NVIDIA_NIM_API_KEY", "test-key")
    llm = CloudLLM()
    llm._session = FakeSession()

    result = llm.generate("hello", system_prompt="system", stream=False)

    assert result == "nim ok"
    assert len(llm._session.gets) == 1
    assert len(llm._session.posts) == 1
    request = llm._session.posts[0]
    assert request["url"].endswith("/chat/completions")
    assert request["headers"]["Authorization"] == "Bearer test-key"


def test_cloud_llm_marks_chat_auth_failure_unavailable(monkeypatch):
    monkeypatch.setattr(config, "NVIDIA_NIM_API_KEY", "bad-key")
    llm = CloudLLM()
    llm._session = FakeSession(
        post_error=requests.exceptions.HTTPError("401 Client Error: Unauthorized")
    )

    assert llm.generate("hello", stream=False) is None
    assert llm.is_available is False
