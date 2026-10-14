import asyncio
import contextlib

from claude_agent_sdk import (
    AssistantMessage,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    StreamEvent,
    ToolPermissionContext,
    ToolUseBlock,
)
from fakes import FakeClient, FakeSpeaker, FakeSpeech

from lila import agent as agent_module
from lila.agent import REPROMPT, SORRY, VoiceAgent, describe_tool, parse_yes_no
from lila.config import Settings

PCM = b"\x00" * 960


@contextlib.asynccontextmanager
async def running(**settings):
    client, speech = FakeClient(), FakeSpeech()
    agent = VoiceAgent(client, speech, FakeSpeaker(), Settings(**settings))
    tasks = [
        asyncio.create_task(agent.run_messages()),
        asyncio.create_task(agent.run_speech()),
        asyncio.create_task(agent.run_transcriber()),
    ]
    try:
        yield agent, client, speech
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def settle():
    for _ in range(30):
        await asyncio.sleep(0)


def user_says(agent, speech, text):
    """What the listen loop does for one confirmed utterance."""
    agent.on_user_speech()
    speech.transcripts.append(text)
    agent.on_utterance(PCM)


def event(data, parent=None):
    return StreamEvent(uuid="u", session_id="s", event=data, parent_tool_use_id=parent)


def text_block(*deltas, parent=None):
    start = {"type": "content_block_start", "index": 0, "content_block": {"type": "text"}}
    return [
        event(start, parent),
        *[
            event(
                {"type": "content_block_delta", "delta": {"type": "text_delta", "text": d}}, parent
            )
            for d in deltas
        ],
        event({"type": "content_block_stop", "index": 0}, parent),
    ]


def tool(id_, name, **tool_input):
    return AssistantMessage(content=[ToolUseBlock(id=id_, name=name, input=tool_input)], model="m")


def result(**kw):
    fields = dict(
        subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
        session_id="sess-1",
    )  # fmt: skip
    return ResultMessage(**{**fields, **kw})


def write_request(agent):
    return asyncio.create_task(
        agent.can_use_tool("Write", {"file_path": "/w/voice-check.txt"}, ToolPermissionContext())
    )


QUESTION = "I'd like to write the file voice-check.txt. Is that okay?"


async def test_answer_is_spoken_without_markdown():
    async with running() as (agent, client, speech):
        await agent.handle_text("hi")
        client.push(*text_block("## Hello\n**There** are `two` ", "files.\n- a_b.txt\n"), result())
        await settle()
        assert speech.spoken == ["Hello There are two files. a b.txt"]
        assert not agent.turn_active and agent.session_id == "sess-1"


async def test_subagent_text_is_not_spoken():
    async with running() as (agent, client, speech):
        await agent.handle_text("hi")
        client.push(*text_block("Secret helper text.", parent="tool-1"))
        client.push(*text_block("Main answer."), result())
        await settle()
        assert speech.spoken == ["Main answer."]


async def test_progress_phrase_rules_and_one_fish_connection_per_reply():
    async with running() as (agent, client, speech):
        await agent.handle_text("look around")
        client.push(tool("t1", "Read", file_path="a.py"), tool("t2", "Grep", pattern="x"))
        client.push(*text_block("Found it."), tool("t3", "WebSearch", query="q"))
        client.push(
            tool("t4", "WebFetch", url="https://x.y"), tool("t4", "WebFetch", url="https://x.y")
        )
        client.push(result())
        await settle()
        assert speech.spoken == ["Looking through the files.", "Found it.", "Reading a web page."]
        assert speech.calls == 1


async def test_looking_at_the_screen_has_a_phrase_and_clipboard_is_silent():
    async with running() as (agent, client, speech):
        await agent.handle_text("what am I looking at")
        client.push(tool("t1", "mcp__lila__screenshot"), tool("t2", "mcp__lila__clipboard"))
        client.push(result())
        await settle()
        assert speech.spoken == ["Taking a look."]


async def test_reply_socket_closes_when_idle_and_reopens(monkeypatch):
    monkeypatch.setattr(agent_module, "IDLE_CLOSE", 0.01)
    async with running() as (agent, client, speech):
        await agent.handle_text("look around")
        client.push(*text_block("First."))
        await asyncio.sleep(0.05)  # a long tool run
        client.push(*text_block("Second."), result())
        await settle()
        assert speech.spoken == ["First.", "Second."]
        assert speech.calls == 2


async def test_no_progress_phrase_for_a_tool_that_needs_approval():
    async with running(voice_approvals=False) as (agent, client, speech):
        await agent.handle_text("write it")
        client.push(tool("t1", "Write", file_path="/tmp/x.txt"), result())
        await settle()
        assert speech.spoken == []


async def test_barge_in_waits_for_words_then_interrupts_and_drops_late_output():
    async with running() as (agent, client, speech):
        await agent.handle_text("count to 300")
        start, *deltas, stop = text_block("One. Two. ", "Three. ", "Four.")
        client.push(start, deltas[0])
        await settle()
        agent.on_user_speech()
        assert agent.speaker.paused and client.interrupts == 0  # could still be a cough
        speech.transcripts.append("what time is it")
        agent.on_utterance(PCM)
        await settle()
        assert client.interrupts == 1 and agent.muted
        client.push(deltas[1], deltas[2], stop, result(terminal_reason="aborted_streaming"))
        await settle()
        assert client.queries == ["count to 300", "what time is it"] and agent.turn_active
        client.push(*text_block("Noon."), result())
        await settle()
        assert speech.spoken == ["Noon."]
        assert not agent.speaker.paused


async def test_a_cough_pauses_speech_and_resumes_without_interrupting():
    async with running() as (agent, client, speech):
        await agent.handle_text("tell me a story")
        client.push(*text_block("Once upon a time."))
        await settle()
        user_says(agent, speech, "")  # a cough: Fish hears no words
        assert agent.speaker.paused
        await settle()
        assert not agent.speaker.paused
        assert client.interrupts == 0 and agent.turn_active
        client.push(*text_block("The end."), result())
        await settle()
        assert speech.spoken == ["Once upon a time.", "The end."]


async def test_late_result_after_interrupt_timeout_does_not_end_the_next_turn(monkeypatch):
    monkeypatch.setattr(agent_module, "INTERRUPT_TIMEOUT", 0.01)
    async with running() as (agent, client, speech):
        await agent.handle_text("first")
        await agent.handle_text("second")  # Claude never confirms the interrupt in time
        assert client.queries == ["first", "second"] and agent.turn_active
        client.push(*text_block("Late first answer."), result(terminal_reason="aborted_streaming"))
        await settle()
        assert agent.turn_active and speech.spoken == []
        client.push(*text_block("Second answer."), result())
        await settle()
        assert not agent.turn_active and speech.spoken == ["Second answer."]


async def test_approval_yes_allows_without_a_new_turn():
    async with running() as (agent, client, speech):
        await agent.handle_text("create the file")
        decision = write_request(agent)
        await settle()
        assert agent.approval_pending
        user_says(agent, speech, "Yes, go ahead.")  # answering must not barge in
        await settle()
        assert isinstance(await decision, PermissionResultAllow)
        assert client.queries == ["create the file"] and client.interrupts == 0
        assert speech.spoken == [QUESTION]
        assert not agent.approval_pending


async def test_approval_no_denies_with_the_answer():
    async with running() as (agent, client, speech):
        await agent.handle_text("create the file")
        decision = write_request(agent)
        await settle()
        user_says(agent, speech, "No, don't.")
        await settle()
        decision = await decision
        assert isinstance(decision, PermissionResultDeny)
        assert '"No, don\'t."' in decision.message


async def test_unclear_answer_is_asked_again():
    async with running() as (agent, client, speech):
        decision = write_request(agent)
        await settle()
        user_says(agent, speech, "Hmm, let me think.")
        await settle()
        assert agent.approval_pending and speech.spoken == [QUESTION, REPROMPT]
        user_says(agent, speech, "Yes.")
        await settle()
        assert isinstance(await decision, PermissionResultAllow)


async def test_two_unclear_answers_deny():
    async with running() as (agent, client, speech):
        decision = write_request(agent)
        await settle()
        user_says(agent, speech, "Banana.")
        await settle()
        user_says(agent, speech, "Pineapple.")
        await settle()
        decision = await decision
        assert isinstance(decision, PermissionResultDeny)
        assert '"Pineapple."' in decision.message


async def test_approval_waits_until_the_user_stops_talking():
    async with running() as (agent, client, speech):
        agent.on_user_speech()  # words already on their way are not an answer
        decision = write_request(agent)
        await settle()
        assert not agent.approval_pending and speech.spoken == []
        speech.transcripts.append("")
        agent.on_utterance(PCM)
        await settle()
        assert agent.approval_pending and speech.spoken == [QUESTION]
        user_says(agent, speech, "ok")
        await settle()
        assert isinstance(await decision, PermissionResultAllow)


async def test_approval_times_out():
    async with running(approval_timeout=0.01) as (agent, client, speech):
        decision = await agent.can_use_tool("Write", {}, ToolPermissionContext())
        assert isinstance(decision, PermissionResultDeny)
        assert decision.message == "The user did not answer in time."


async def test_input_during_active_turn_is_queued_then_sent():
    async with running(barge_in=False) as (agent, client, speech):
        await agent.handle_text("first")
        await agent.handle_text("second")
        await agent.handle_text("third")
        assert client.queries == ["first"]
        client.push(result())
        await settle()
        assert client.queries == ["first", "second third"] and agent.turn_active


async def test_injected_result_does_not_end_the_turn():
    async with running() as (agent, client, speech):
        await agent.handle_text("hi")
        client.push(result(origin={"kind": "task-notification"}))
        await settle()
        assert agent.turn_active
        client.push(result(origin={"kind": "human"}))
        await settle()
        assert not agent.turn_active


async def test_error_result_is_spoken():
    async with running() as (agent, client, speech):
        await agent.handle_text("hi")
        client.push(result(is_error=True, errors=["boom"]))
        await settle()
        assert speech.spoken == [SORRY]


async def test_transcripts_are_handled_in_order_and_empty_ones_ignored():
    async with running() as (agent, client, speech):
        user_says(agent, speech, "hello")
        user_says(agent, speech, "")
        await settle()
        assert client.queries == ["hello"]


async def test_early_transcript_is_used_when_nothing_more_was_said():
    async with running() as (agent, client, speech):
        speech.transcripts.append("hello there")
        agent.on_user_speech()
        agent.on_pause(b"a" * 960)
        await settle()
        agent.on_utterance(b"a" * 1920, early=True)
        await settle()
        assert speech.heard == [b"a" * 960]
        assert client.queries == ["hello there"]


async def test_early_transcript_is_dropped_when_the_user_kept_talking():
    async with running() as (agent, client, speech):
        speech.transcripts += ["hello", "hello there"]
        agent.on_user_speech()
        agent.on_pause(b"a" * 960)
        await settle()
        agent.on_utterance(b"b" * 1920, early=False)
        await settle()
        assert speech.heard == [b"a" * 960, b"b" * 1920]
        assert client.queries == ["hello there"]


async def test_reconnect_ends_the_old_turn_and_uses_the_new_client():
    async with running() as (agent, client, speech):
        await agent.handle_text("hi")
        new_client = FakeClient()
        agent.attach(new_client)
        assert not agent.turn_active
        await agent.handle_text("again")
        assert new_client.queries == ["again"] and client.interrupts == 0


def test_parse_yes_no():
    assert parse_yes_no("Yes please.") is True
    assert parse_yes_no("Sure, go for it!") is True
    assert parse_yes_no("Why not?") is True
    assert parse_yes_no("Yes... no, wait.") is False
    assert parse_yes_no("Don't do that") is False
    assert parse_yes_no("hold on a second") is False
    assert parse_yes_no("Ja, doe maar.") is True
    assert parse_yes_no("Nee, liever niet.") is False
    assert parse_yes_no("Akkoord") is True
    assert parse_yes_no("banana") is None
    assert parse_yes_no("I know") is None  # "no" only matches as a whole word


def test_describe_tool():
    assert describe_tool("Bash", {"command": "ls", "description": "List the files."}) == (
        "run a command to list the files"
    )
    assert describe_tool("Bash", {"command": "/usr/bin/git status"}) == "run a git command"
    assert describe_tool("Write", {"file_path": "/a/b/notes.txt"}) == "write the file notes.txt"
    assert describe_tool("Edit", {"file_path": "C:\\x\\main.py"}) == "edit main.py"
    assert (
        describe_tool("NotebookEdit", {"notebook_path": "n.ipynb"}) == "edit the notebook n.ipynb"
    )
    assert (
        describe_tool("WebFetch", {"url": "https://docs.python.org/3/"}) == "open docs.python.org"
    )
    assert describe_tool("WebSearch", {"query": "weather"}) == "search the web for weather"
    assert describe_tool("mcp__my_server__send_mail", {}) == "use send mail from my server"
    assert describe_tool("Skill", {}) == "use the Skill tool"
