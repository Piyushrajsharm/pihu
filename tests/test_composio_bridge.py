from tools.composio_bridge import ComposioBridge


class FakeMessage:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class FakeChoice:
    def __init__(self, message=None, delta=None):
        self.message = message
        self.delta = delta


class FakeResponse:
    def __init__(self, message):
        self.choices = [FakeChoice(message=message)]


class FakeDelta:
    def __init__(self, content):
        self.content = content


class FakeChunk:
    def __init__(self, content):
        self.choices = [FakeChoice(delta=FakeDelta(content))]


class FakeCompletions:
    def __init__(self, planning_response, final_stream):
        self.planning_response = planning_response
        self.final_stream = final_stream
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return self.planning_response
        return self.final_stream


class FakeOpenAIClient:
    def __init__(self, completions):
        self.chat = type("Chat", (), {"completions": completions})()


class FakeTools:
    def __init__(self):
        self.requests = []

    def get(self, **kwargs):
        self.requests.append(kwargs)
        return [{"type": "function", "function": {"name": "GITHUB_LIST_ISSUES"}}]


class FakeComposio:
    def __init__(self):
        self.tools = FakeTools()


class FakeProvider:
    def __init__(self):
        self.calls = []

    def handle_tool_calls(self, **kwargs):
        self.calls.append(kwargs)
        return [{"ok": True}]


def make_modern_bridge(planning_response):
    bridge = ComposioBridge.__new__(ComposioBridge)
    bridge._is_available = True
    bridge._backend = "modern"
    bridge._unavailable_reason = ""
    bridge.user_id = "test_user"
    bridge.model_name = "test-model"
    bridge.composio = FakeComposio()
    bridge.provider = FakeProvider()
    completions = FakeCompletions(planning_response, [FakeChunk("summary ok")])
    bridge.openai_client = FakeOpenAIClient(completions)
    return bridge, completions


def test_composio_bridge_selects_current_sdk_toolkits_from_prompt():
    bridge = ComposioBridge.__new__(ComposioBridge)

    assert bridge._select_toolkits("check github issues", None) == ["github"]
    assert bridge._select_toolkits("send an email invite", None) == ["gmail"]
    assert bridge._select_toolkits("check my calendar", None) == ["googlecalendar"]
    assert bridge._select_toolkits("do something elsewhere", None) == bridge.DEFAULT_TOOLKITS
    assert bridge._select_toolkits("ignored", ["Slack", "Notion"]) == ["slack", "notion"]


def test_composio_bridge_modern_execute_gets_tools_and_handles_tool_calls():
    planning_response = FakeResponse(FakeMessage(tool_calls=["call_1"]))
    bridge, completions = make_modern_bridge(planning_response)

    output = "".join(bridge.execute("check github issues"))

    assert "summary ok" in output
    assert bridge.composio.tools.requests == [
        {"user_id": "test_user", "toolkits": ["github"], "limit": 20}
    ]
    assert bridge.provider.calls[0]["user_id"] == "test_user"
    assert bridge.provider.calls[0]["response"] is planning_response
    assert completions.calls[0]["tools"][0]["function"]["name"] == "GITHUB_LIST_ISSUES"


def test_composio_bridge_returns_model_content_when_no_tool_call_is_needed():
    bridge, _ = make_modern_bridge(FakeResponse(FakeMessage(content="plain answer")))

    output = "".join(bridge.execute("say hello"))

    assert "plain answer" in output
    assert bridge.provider.calls == []
