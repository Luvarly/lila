from claude_agent_sdk import SystemMessage
from fakes import FakeMic, FakeSpeaker, FakeSpeech

from lila import __main__ as main
from lila.config import Settings


class DroppingClient:
    """Connects, reports a session, then the connection drops."""

    made: list["DroppingClient"] = []

    def __init__(self, options):
        self.options = options
        DroppingClient.made.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def receive_messages(self):
        yield SystemMessage(subtype="init", data={"session_id": "sess-9"})


async def test_reconnects_into_the_same_session_then_gives_up(monkeypatch, capsys):
    monkeypatch.setattr(main, "ClaudeSDKClient", DroppingClient)
    monkeypatch.setattr(main, "Speaker", FakeSpeaker)
    monkeypatch.setattr(main, "Microphone", FakeMic)
    monkeypatch.setattr(main, "FishSpeech", lambda settings: FakeSpeech())
    monkeypatch.setattr(main, "RECONNECT_DELAY", 0)

    await main.run(Settings(greeting=False))

    resumes = [c.options.resume for c in DroppingClient.made]
    assert resumes == [None] + ["sess-9"] * main.MAX_RECONNECTS
    out = capsys.readouterr().out
    assert out.count("(reconnected)") == main.MAX_RECONNECTS
    assert "giving up" in out and "Session sess-9" in out
