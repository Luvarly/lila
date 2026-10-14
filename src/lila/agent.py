"""VoiceAgent: turn state, Claude message handling, the speech queue, barge-in and approvals.

No audio or Fish imports here, so tests can use fakes. Speech goes through an object with
`transcribe(pcm)` and `synthesize(texts)`, where an empty text means "say what you have now";
the speaker has `play`, `pause`, `resume`, `stop`, `drain` and `is_playing`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from claude_agent_sdk import (
    TERMINAL_TASK_STATUSES,
    AssistantMessage,
    ClaudeAgentOptions,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    TaskNotificationMessage,
    TaskStartedMessage,
    TaskUpdatedMessage,
    ToolPermissionContext,
    ToolUseBlock,
)

from .config import Settings
from .term import INDENT, LILA, YOU, ask_line, error, note, screen_summary, tool_line
from .textfilter import SpeechFilter
from .tools import TOOL_NAMES, lila_tools
from .web import Feed

log = logging.getLogger("lila")

GREETING = "Hey, it's Lila. Whenever you're ready."
SORRY = "Hm, something went wrong on my end. Sorry about that."
REPROMPT = "Sorry, was that a yes or a no?"
FLUSH = ""  # in a job's text: say everything so far now (before a tool runs)
INTERRUPT_TIMEOUT = 10.0
IDLE_CLOSE = 15.0  # close a reply's Fish socket after this long without text; reopen for more
MEMORY_DIR = "~/.lila/memory"  # Claude Code's own auto-memory, shared by every working folder
AGENT_TASKS = ("local_agent", "local_workflow")  # the task types the SDK itself waits for

PERSONALITY = """\
# Who you are
In this voice interface you are Lila, the user's personal assistant, powered by Claude. You live on their computer: you can work with their files and the web, look at what they've copied or at their screen when they ask, and remember things between conversations.

Your character is dry, but kind-hearted: the friend with a deadpan sense of humour who quietly has your back.
- Your humour is understated: a wry aside, an understatement, a bit of gentle teasing. At most one light touch per answer, and none when the user is stressed, in a hurry or dealing with something serious. Never at their expense.
- Under the dryness, you care. Notice how they're doing. Be glad for their wins without gushing, and be patient and warm when something goes wrong; a small "that's annoying, let's fix it" beats a pep talk.
- Be straightforward: plain words, short answers, an honest opinion when asked, and say so when you're not sure. No filler such as "Great question", no fake cheer, no repeating the question back.
- Pay attention to the person. When you learn something that will help later (their name, the people and projects they mention, what they like, how they want things done), save it to memory quietly and use it naturally, the way a friend remembers.

"""  # noqa: E501

SPEECH_PROMPT = """\
# Voice conversation
You are talking with the user through a voice interface. Their messages come from speech recognition and may contain recognition mistakes; if something looks garbled, ask a short question instead of guessing. Everything you write is read aloud by a text-to-speech voice, so:
- Answer in short, natural spoken sentences. Reply in the language the user speaks.
- No markdown: no headings, bullet lists, tables, bold text or emojis.
- Never read out code, file contents, long paths, commands or URLs. Write code to files and say in one sentence what you did; the user can see details on screen.
- Say numbers, dates and units the way a person would say them.
- For long results, give the gist in two or three sentences and offer more detail.
- Before a task that takes a while, say in one short sentence what you are about to do.
- For work that will take more than a minute or so, such as research, a long search or a bigger change, start a background agent (the Agent tool with run_in_background) so the user can keep talking with you, and say you'll let them know. When it reports back, give them the result in a sentence or two.
"""  # noqa: E501

EXPRESSIVE_PROMPT = """\
- You may add a delivery cue in square brackets at the start of a sentence, such as [happy], [calm], [soft tone] or [laughing]. Use one only when it truly fits, at most once every few sentences, and never in code, file names or quotes.
"""  # noqa: E501

_PROGRESS = {
    **dict.fromkeys(["Read", "Glob", "Grep", "LS"], "Looking through the files."),
    "Bash": "Running a command.",
    **dict.fromkeys(["Edit", "MultiEdit", "Write", "NotebookEdit"], "Making the changes."),
    "WebSearch": "Searching the web.",
    "WebFetch": "Reading a web page.",
    **dict.fromkeys(["Task", "Agent"], "Handing part of this to a helper."),
    **dict.fromkeys(["TodoWrite", "AskUserQuestion", "mcp__lila__clipboard"], None),
    "mcp__lila__screenshot": "Taking a look.",
}

_NEGATIVE = [
    "no", "nope", "nah", "don't", "dont", "do not", "stop", "cancel", "wait", "never", "hold on",
    "nee", "niet", "neen", "liever niet",
]  # fmt: skip
_POSITIVE = [
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "go ahead", "go for it", "do it", "fine",
    "approve", "approved", "allow", "absolutely", "of course", "please do",
    "ja", "jawel", "prima", "doe maar", "goed", "akkoord",
]  # fmt: skip

_ALWAYS_ALLOWED = [*TOOL_NAMES, f"Write({MEMORY_DIR}/**)", f"Edit({MEMORY_DIR}/**)"]


def build_options(settings: Settings, can_use_tool: Callable | None) -> ClaudeAgentOptions:
    append = PERSONALITY + SPEECH_PROMPT + (EXPRESSIVE_PROMPT if settings.expressive else "")
    return ClaudeAgentOptions(
        system_prompt={"type": "preset", "preset": "claude_code", "append": append},
        include_partial_messages=True,
        # Lila's own tools and its memory folder never need a spoken yes.
        allowed_tools=[*settings.allowed_tools, *_ALWAYS_ALLOWED],
        mcp_servers={"lila": lila_tools()},
        settings=json.dumps({"autoMemoryDirectory": MEMORY_DIR}),
        permission_mode="default" if settings.voice_approvals else "dontAsk",
        can_use_tool=can_use_tool if settings.voice_approvals else None,
        cwd=settings.workdir,
        model=settings.claude_model,
        effort=settings.effort,
        resume=settings.resume,
    )


def _words(text: str) -> str:
    """Lowercase, punctuation stripped ("don't" -> "dont"), padded so phrases match whole words."""
    text = re.sub(r"['’]", "", text.lower())
    return " " + " ".join(re.sub(r"[^\w\s]", " ", text).split()) + " "


def parse_yes_no(answer: str) -> bool | None:
    """True for yes, False for no, None when unclear. Any negative beats any positive."""
    words = _words(answer)

    def has(phrases: list[str]) -> bool:
        return any(_words(p) in words for p in phrases)

    if has(["why not"]):
        return True
    if has(_NEGATIVE):
        return False
    if has(_POSITIVE):
        return True
    return None


def _basename(path: Any) -> str:
    return re.split(r"[\\/]", str(path or "").rstrip("\\/"))[-1]


def describe_tool(name: str, tool_input: dict[str, Any]) -> str:
    """What the tool is about to do, phrased to follow "I'd like to"."""
    if name == "Bash":
        description = str(tool_input.get("description") or "").strip().rstrip(".")
        if description:
            return f"run a command to {description[0].lower()}{description[1:]}"
        program = str(tool_input.get("command") or "").split()
        return f"run a {_basename(program[0])} command" if program else "run a command"
    if name == "Write":
        return f"write the file {_basename(tool_input.get('file_path'))}"
    if name in ("Edit", "MultiEdit"):
        return f"edit {_basename(tool_input.get('file_path'))}"
    if name == "NotebookEdit":
        return f"edit the notebook {_basename(tool_input.get('notebook_path'))}"
    if name == "WebFetch":
        url = str(tool_input.get("url") or "")
        host = re.sub(r"^[a-z]+://", "", url).split("/")[0]
        return f"open {host or 'a web page'}"
    if name == "WebSearch":
        return f"search the web for {tool_input.get('query', '')}"
    if name.startswith("mcp__") and name.count("__") >= 2:
        _, server, tool = name.split("__", 2)
        return f"use {tool.replace('_', ' ')} from {server.replace('_', ' ')}"
    return f"use the {name} tool"


class _Job:
    """One thing to say, fed in chunks: a whole Claude reply, or a phrase outside a turn."""

    def __init__(self) -> None:
        self.chunks: asyncio.Queue[str | None] = asyncio.Queue()
        self.closed = False  # nothing more will be added
        self.done = False  # the speaker side read to the end
        self.cancelled = False

    def put(self, chunk: str) -> None:
        if not self.closed:
            self.chunks.put_nowait(chunk)

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.chunks.put_nowait(None)

    def cancel(self) -> None:
        self.cancelled = True
        self.close()
        self.chunks.put_nowait(None)  # wake a reader even if the job was already closed


class VoiceAgent:
    def __init__(self, client: Any, speech: Any, speaker: Any, settings: Settings) -> None:
        self.client = client
        self.speech = speech
        self.speaker = speaker
        self.settings = settings

        self.turn_active = False
        self.turn_done = asyncio.Event()
        self.turn_done.set()
        self.muted = False
        self.session_id: str | None = None
        self.feed = Feed()  # what the HUD shows (--web)
        self.mic_level = 0.0
        # (transcript task, audio bytes, when the utterance ended), in the order spoken
        self.utterances: asyncio.Queue[tuple[asyncio.Future[str], int, float]] = asyncio.Queue()

        self._early: asyncio.Future[str] | None = None  # transcript started at a pause
        self._pending_speech = 0  # confirmed utterances whose transcript isn't handled yet
        self._quiet = asyncio.Event()
        self._quiet.set()
        self._stale_results = 0  # results of turns we gave up waiting for
        self._queued: list[str] = []
        self._permission: asyncio.Future[str] | None = None
        self._approval_lock = asyncio.Lock()
        self._agents: set[str] = set()  # running agent tasks; an interrupt would kill them
        self._hush = False  # don't say the rest of the message the user talked over

        self._jobs: asyncio.Queue[_Job] = asyncio.Queue()
        self._current: _Job | None = None
        self._synth_task: asyncio.Task | None = None
        self._turn_job: _Job | None = None
        self._filter: SpeechFilter | None = None  # set while a text block is open
        self._seen_tools: set[str] = set()
        self._spoke_since_tool = False
        self._last_progress: str | None = None
        self._tasks: set[asyncio.Task] = set()

        self._streaming = False  # a "lila ›" line is open on screen
        self._listening = False  # the "(listening…)" indicator is on screen
        self._t_query: float | None = None
        self._t_first_delta: float | None = None
        self._awaiting_audio = False

    def attach(self, client: Any) -> None:
        """Use a (re)connected client. A turn the old connection was running is over."""
        self.client = client
        self._stale_results = 0
        self._agents.clear()  # they ended with the old connection
        if self.turn_active:
            self._end_turn()
        if self.settings.web:
            self._spawn(self._measure_context())

    # ---- terminal ---------------------------------------------------------------------------

    def _write(self, text: str) -> None:
        self.show_listening(False)
        sys.stdout.write(text)
        sys.stdout.flush()

    def _println(self, line: str) -> None:
        if self._streaming:
            self._streaming = False
            self._write("\n")
        self._write(line + "\n")

    def show_listening(self, on: bool) -> None:
        if on == self._listening or self._streaming or not sys.stdout.isatty():
            return
        self._listening = on
        sys.stdout.write(note("listening…") if on else "\r" + " " * 30 + "\r")
        sys.stdout.flush()

    # ---- input ------------------------------------------------------------------------------

    @property
    def approval_pending(self) -> bool:
        return self._permission is not None and not self._permission.done()

    @property
    def state(self) -> str:
        """What Lila is doing right now, for the HUD."""
        if self.approval_pending:
            return "asking"
        if not self._quiet.is_set():
            return "hearing"
        if self.speaker.is_playing:
            return "speaking"
        if self.turn_active:
            return "thinking"
        return "listening"

    def on_user_speech(self) -> None:
        """The segmenter confirmed the user is talking. Their transcript decides what it was."""
        self._pending_speech += 1
        self._quiet.clear()
        if self.approval_pending:
            self._stop_speech()  # they're answering the question
        elif self.settings.barge_in:
            self.speaker.pause()  # resumed if it turns out to be a cough

    def on_pause(self, pcm: bytes) -> None:
        """The user paused mid-utterance: start transcribing in case they're done."""
        self._drop_early()
        self._early = self._transcribe(pcm)

    def on_utterance(self, pcm: bytes, early: bool = False) -> None:
        """The utterance ended. `early`: nothing was said since the last pause."""
        if early and self._early is not None:
            transcript, self._early = self._early, None
        else:
            self._drop_early()
            transcript = self._transcribe(pcm)
        self.utterances.put_nowait((transcript, len(pcm), time.monotonic()))

    def _transcribe(self, pcm: bytes) -> asyncio.Future[str]:
        task = asyncio.ensure_future(self.speech.transcribe(pcm))
        task.add_done_callback(lambda t: t.cancelled() or t.exception())  # dropped ones may fail
        return task

    def _drop_early(self) -> None:
        if self._early is not None:
            self._early.cancel()
            self._early = None

    async def run_transcriber(self) -> None:
        """Handles transcripts in the order they were spoken, off the mic loop."""
        while True:
            transcript, size, ended = await self.utterances.get()
            try:
                try:
                    text = await transcript
                except Exception as e:
                    self.show_listening(False)
                    self._println(error(f"(speech recognition failed: {e})"))
                    continue
                log.debug(
                    "end of speech -> transcript: %.0f ms for %.1f s of audio",
                    (time.monotonic() - ended) * 1000,
                    size / 32000,
                )
                self.show_listening(False)
                if text:
                    await self.handle_text(text)
            finally:
                self._pending_speech = max(0, self._pending_speech - 1)
                if not self._pending_speech:
                    self._quiet.set()
                    self.speaker.resume()

    async def handle_text(self, text: str) -> None:
        self._println(YOU + text)
        self.feed.emit("you", text=text)
        if self.approval_pending:
            self._permission.set_result(text)
            return
        if self.settings.barge_in:
            await self._barge_in()
        elif self.turn_active:
            self._queued.append(text)
            self._println(note("(noted, I'll get to it after this)"))
            return
        await self._begin_turn(text)

    def _begin_turn(self, text: str) -> Awaitable[None]:
        # State is set synchronously so nothing can start a second turn in between.
        self._start_turn()
        self._t_query = time.monotonic()
        return self._send(text)

    def _start_turn(self) -> None:
        self.turn_active = True
        self.turn_done.clear()
        self.muted = False
        self._spoke_since_tool = False
        self._last_progress = None
        self._t_query = None
        self._t_first_delta = None
        if self._turn_job is None:
            # Queued now so its Fish socket opens while Claude thinks (that takes ~0.5 s).
            self._turn_job = _Job()
            self._jobs.put_nowait(self._turn_job)

    async def _send(self, text: str) -> None:
        try:
            await self.client.query(text)
        except Exception as e:
            self._println(error(f"(couldn't send that to Claude Code: {e})"))
            self._end_turn()

    def _end_turn(self) -> None:
        self._close_block()
        if self._turn_job is not None:
            self._turn_job.close()
            self._turn_job = None
        self.turn_active = False
        self.muted = False
        self.turn_done.set()
        if self._queued:
            text = " ".join(self._queued)
            self._queued.clear()
            self._spawn(self._begin_turn(text))

    # ---- barge-in ---------------------------------------------------------------------------

    async def _barge_in(self) -> None:
        """New words from the user: stop speaking, and interrupt Claude if it's mid-turn."""
        self._close_block()  # an unfinished sentence goes with the speech being stopped
        self._stop_speech()
        if not self.turn_active:
            return
        self._println(note("(interrupted)"))
        if self._agents:
            # An interrupt would kill the background agents too. Claude reads the new words at
            # its next step instead; until then, the rest of what it was saying goes unsaid.
            self._hush = True
            return
        self.muted = True
        try:
            await self.client.interrupt()
        except Exception as e:
            log.warning("interrupt failed: %s", e)
        try:
            await asyncio.wait_for(self.turn_done.wait(), INTERRUPT_TIMEOUT)
        except asyncio.TimeoutError:
            log.warning("Claude didn't finish the interrupted turn; ending it locally")
            self._stale_results += 1  # its late result must not end the next turn
            self._end_turn()

    def _stop_speech(self) -> None:
        self.speaker.stop()
        while not self._jobs.empty():
            self._jobs.get_nowait().cancel()
        for job in (self._current, self._turn_job):
            if job is not None:
                job.cancel()
        self._turn_job = None
        if self._synth_task is not None:
            self._synth_task.cancel()

    # ---- approvals --------------------------------------------------------------------------

    async def can_use_tool(
        self, tool_name: str, tool_input: dict[str, Any], context: ToolPermissionContext
    ) -> PermissionResultAllow | PermissionResultDeny:
        async with self._approval_lock:  # parallel tool calls are asked one at a time
            # Words already being spoken are not an answer: they may be an interruption.
            await self._quiet.wait()
            if self.muted:
                return PermissionResultDeny(message="The user interrupted.", interrupt=True)
            summary = screen_summary(tool_input)
            self._println(ask_line(tool_name, summary))
            who = "My helper would" if context.agent_id else "I'd"
            question = f"{who} like to {describe_tool(tool_name, tool_input)}. Is that okay?"
            self.feed.emit("ask", tool=tool_name, summary=summary, question=question)
            for prompt in (question, REPROMPT):
                self._permission = asyncio.get_running_loop().create_future()
                try:
                    self.say(prompt)
                    answer = await asyncio.wait_for(
                        self._permission, self.settings.approval_timeout
                    )
                except asyncio.TimeoutError:
                    self._println(note("(no answer, so that's a no)"))
                    return PermissionResultDeny(message="The user did not answer in time.")
                finally:
                    self._permission = None
                verdict = parse_yes_no(answer)
                if verdict is not None:
                    break
            if verdict:
                return PermissionResultAllow()
            return PermissionResultDeny(message=f'The user did not approve. They said: "{answer}"')

    # ---- Claude messages --------------------------------------------------------------------

    async def run_messages(self) -> None:
        """The one long-lived receive loop; returns when the connection ends."""
        try:
            async for message in self.client.receive_messages():
                self._handle_message(message)
            reason = "the stream ended"
        except Exception as e:
            reason = str(e) or type(e).__name__
        self._println(error(f"(lost the connection to Claude Code: {reason})"))

    def _handle_message(self, message: Any) -> None:
        try:
            self.feed.message(message)
        except Exception as e:  # the HUD must never break the conversation
            log.warning("HUD feed: %r", e)
        ignore = self.muted or self._stale_results > 0
        if isinstance(message, StreamEvent):
            if message.parent_tool_use_id or ignore:
                return
            event = message.event
            kind = event.get("type")
            if kind == "message_start":
                self._hush = False  # a new message answers what the user said over the last one
                if not self.turn_active:
                    self._start_turn()  # Claude began on its own: a background task reported back
            if self._hush:
                return
            block_type = event.get("content_block", {}).get("type")
            delta = event.get("delta", {})
            if kind == "content_block_start" and block_type == "text":
                self._open_block()
            elif kind == "content_block_delta" and delta.get("type") == "text_delta":
                self._on_text(delta.get("text", ""))
            elif kind == "content_block_stop":
                self._close_block()
        elif isinstance(message, AssistantMessage):
            if message.parent_tool_use_id or ignore:
                return
            for block in message.content:
                if isinstance(block, ToolUseBlock) and block.id not in self._seen_tools:
                    self._seen_tools.add(block.id)
                    self._on_tool(block)
        elif isinstance(message, TaskStartedMessage):
            if message.task_type in AGENT_TASKS:
                self._agents.add(message.task_id)
        elif isinstance(message, (TaskNotificationMessage, TaskUpdatedMessage)):
            if message.status in TERMINAL_TASK_STATUSES:
                self._agents.discard(message.task_id)
        elif isinstance(message, SystemMessage):
            if message.subtype == "init":
                self.session_id = message.data.get("session_id", self.session_id)
                log.debug("model: %s", message.data.get("model"))
        elif isinstance(message, ResultMessage):
            # Every result ends what Claude was doing, also a turn it started itself. If more
            # follows (words it hadn't read yet), its message_start begins a new turn.
            self.session_id = message.session_id
            if self.settings.web:
                self._spawn(self._measure_context())
            if self._stale_results:
                self._stale_results -= 1  # the turn we already ended locally
                return
            log.debug(
                "claude: %.1f s, $%.4f", message.duration_ms / 1000, message.total_cost_usd or 0
            )
            if message.is_error and not self.muted:
                self._println(error(f"(error: {'; '.join(message.errors or [message.subtype])})"))
                self.say(SORRY)
            self._end_turn()

    async def _measure_context(self) -> None:
        try:
            self.feed.context(await self.client.get_context_usage())
        except Exception as e:
            log.debug("context usage unavailable: %s", e)

    def _open_block(self) -> None:
        self._close_block()
        self._filter = SpeechFilter(self.settings.expressive)
        self.feed.emit("lila_start")
        self._write(LILA)
        self._streaming = True

    def _on_text(self, text: str) -> None:
        if self._filter is None:
            return
        if self._t_first_delta is None:
            self._t_first_delta = time.monotonic()
            self._awaiting_audio = True
            if self._t_query is not None:
                ms = (self._t_first_delta - self._t_query) * 1000
                log.debug("transcript -> first text: %.0f ms", ms)
        sys.stdout.write(text.replace("\n", "\n" + INDENT))  # keep the answer in its column
        self.feed.emit("lila", text=text)
        sys.stdout.flush()
        self._turn_put(self._filter.feed(text))
        self._spoke_since_tool = True

    def _close_block(self) -> None:
        if self._filter is None:
            return
        self._turn_put(self._filter.flush(), flush=True)  # speak it before any tool runs
        self._filter = None
        if self._streaming:
            self._streaming = False
            self._write("\n")

    def _on_tool(self, block: ToolUseBlock) -> None:
        self._println(tool_line(block.name, screen_summary(block.input)))
        phrase = _PROGRESS.get(block.name, "Working on it.")
        if (
            phrase
            and not self._hush
            and not self._spoke_since_tool
            and (block.name in self.settings.allowed_tools or block.name in TOOL_NAMES)
            and phrase != self._last_progress
        ):
            self._last_progress = phrase
            self.say(phrase)
        self._spoke_since_tool = False

    # ---- speech queue -----------------------------------------------------------------------

    def say(self, text: str) -> None:
        if self.turn_active:  # part of the reply: same order, same Fish connection
            self._turn_put([text], flush=True)
            return
        job = _Job()
        job.put(text)
        job.close()
        self._jobs.put_nowait(job)

    def _turn_put(self, chunks: list[str], flush: bool = False) -> None:
        """Add to the reply's job, which is created by the first thing it has to say."""
        if not chunks and self._turn_job is None:
            return
        if self._turn_job is None:
            self._turn_job = _Job()
            self._jobs.put_nowait(self._turn_job)
        for chunk in chunks:
            self._turn_job.put(chunk)
        if flush:
            self._turn_job.put(FLUSH)

    async def run_speech(self) -> None:
        """Speaks jobs in order; each synthesis is its own task so barge-in can cancel it."""
        try:
            while True:
                job = await self._jobs.get()
                if job.cancelled:
                    continue
                self._current = job
                self._synth_task = asyncio.create_task(self._speak(job))
                await asyncio.wait([self._synth_task])
                self._current = None
                self._synth_task = None
        finally:
            if self._synth_task is not None:
                self._synth_task.cancel()

    async def _speak(self, job: _Job) -> None:
        """Opens a Fish socket at once, and again for more text after an idle close or an error."""
        first: str | None = None  # the first socket opens before there's anything to say
        opened = False
        while not job.done:
            if opened:
                first = await job.chunks.get()
                if first is None:
                    return
                if first == FLUSH or job.cancelled:
                    continue
            opened = True
            try:
                async for fmt, pcm in self.speech.synthesize(self._texts(job, first)):
                    if job.cancelled:
                        return
                    if self._awaiting_audio and self._t_first_delta is not None:
                        self._awaiting_audio = False
                        now = time.monotonic()
                        ms = (now - self._t_first_delta) * 1000
                        log.debug("first text -> first audio: %.0f ms", ms)
                        if self._t_query is not None:
                            self.feed.latency((now - self._t_query) * 1000)
                    self.speaker.play(fmt.rate, fmt.channels, pcm)
            except Exception as e:
                self._println(error(f"(error: text-to-speech failed: {e})"))
            self.speaker.drain()

    async def _texts(self, job: _Job, first: str | None) -> AsyncIterator[str]:
        chunk = first
        while True:
            if job.cancelled:
                raise asyncio.CancelledError
            if chunk is not None:  # None only for a socket opened ahead of the text
                yield chunk
            try:
                chunk = await asyncio.wait_for(job.chunks.get(), IDLE_CLOSE)
            except asyncio.TimeoutError:
                return  # nothing to say for a while (a tool is running): let this socket finish
            if chunk is None:
                if job.cancelled:
                    raise asyncio.CancelledError
                job.done = True
                return

    def _spawn(self, coro: Awaitable[Any]) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            log.error("background task failed: %r", task.exception())
