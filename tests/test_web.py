import asyncio
import json

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TaskNotificationMessage,
    TaskStartedMessage,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from fakes import FakeClient, FakeSpeaker, FakeSpeech

from lila import web
from lila.agent import VoiceAgent
from lila.config import Settings
from lila.web import Feed, Hud


def started(task_id):
    return TaskStartedMessage(
        subtype="task_started", data={}, task_id=task_id, description="research flights",
        uuid="u", session_id="s", tool_use_id="agent-1", task_type="local_agent",
    )  # fmt: skip


def done(task_id):
    return TaskNotificationMessage(
        subtype="task_notification", data={}, task_id=task_id, status="completed",
        output_file="", summary="Found three", uuid="u", session_id="s",
        usage={"total_tokens": 900, "tool_uses": 4, "duration_ms": 5000},
    )  # fmt: skip


def result(cost, output):
    return ResultMessage(
        subtype="success", duration_ms=1200, duration_api_ms=900, is_error=False, num_turns=1,
        session_id="s", total_cost_usd=cost,
        model_usage={"opus": {"outputTokens": output, "webSearchRequests": 0}},
    )  # fmt: skip


def test_tasks_tools_and_session_totals():
    feed = Feed()
    feed.message(started("a1"))
    feed.message(
        AssistantMessage(
            content=[ToolUseBlock(id="t1", name="Grep", input={"pattern": "TODO"})],
            model="m",
            parent_tool_use_id="agent-1",
        )
    )
    feed.message(UserMessage(content=[ToolResultBlock(tool_use_id="t1", is_error=True)]))
    feed.message(done("a1"))

    task = feed.sticky["task:a1"]
    assert task["description"] == "research flights" and task["status"] == "completed"
    assert task["tokens"] == 900 and task["tool_uses"] == 4 and task["summary"] == "Found three"
    tool, tool_done = [e for e in feed.history if e["type"].startswith("tool")]
    assert tool["summary"] == "TODO" and tool["parent"] == "agent-1"
    assert tool_done == {**tool_done, "id": "t1", "error": True}

    # Claude Code reports running totals per process; a reconnect starts them over.
    feed.message(result(0.10, 100))
    feed.message(result(0.25, 300))
    feed.message(result(0.05, 50))
    stats = feed.sticky["stats"]
    assert round(stats["cost"], 2) == 0.30 and stats["output"] == 350
    assert stats["replies"] == 3 and stats["tools"] == 1


def test_finished_tasks_are_forgotten_after_a_while():
    feed = Feed()
    for n in range(web.KEEP_DONE + 2):
        feed.message(started(f"a{n}"))
        feed.message(done(f"a{n}"))
    tasks = [k for k in feed.sticky if k.startswith("task:")]
    assert tasks == [f"task:a{n}" for n in range(2, web.KEEP_DONE + 2)]


async def test_page_and_events_for_this_machine_only():
    feed = Feed()
    feed.emit("you", text="hello")
    hud = Hud(feed, lambda: {"state": "listening", "mic": 0, "voice": 0})
    url = await hud.start(port=0)

    async def get(path, host):
        reader, writer = await asyncio.open_connection("127.0.0.1", hud.port)
        writer.write(f"GET {path} HTTP/1.1\r\nHost: {host}\r\n\r\n".encode())
        return reader, writer

    try:
        reader, writer = await get("/", f"127.0.0.1:{hud.port}")
        assert (await reader.readline()).startswith(b"HTTP/1.1 200")
        assert b"<html" in await reader.read()
        writer.close()

        reader, writer = await get("/saira.woff2", f"127.0.0.1:{hud.port}")
        assert (await reader.readline()).startswith(b"HTTP/1.1 200")
        assert b"Content-Type: font/woff2" in await reader.read()
        writer.close()

        reader, writer = await get("/events", "evil.example:80")
        assert (await reader.readline()).startswith(b"HTTP/1.1 403")
        writer.close()

        reader, writer = await get("/events", f"localhost:{hud.port}")
        await reader.readuntil(b"retry: 2000\n\n")
        events = [json.loads((await reader.readuntil(b"\n\n"))[6:]) for _ in range(3)]
        assert [e["type"] for e in events] == ["hello", "you", "tick"]
        writer.close()
    finally:
        await hud.close()
    assert url == f"http://127.0.0.1:{hud.port}/"


async def test_state_follows_the_conversation():
    speaker = FakeSpeaker()
    agent = VoiceAgent(FakeClient(), FakeSpeech(), speaker, Settings())
    assert agent.state == "listening"
    agent.on_user_speech()
    assert agent.state == "hearing"
    agent._quiet.set()
    agent._start_turn()
    assert agent.state == "thinking"
    speaker.is_playing = True
    assert agent.state == "speaking"
    agent._permission = asyncio.get_running_loop().create_future()
    assert agent.state == "asking"
