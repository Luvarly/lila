# SPEC: voice-agent v0.1 (Fish Audio)

A personal voice assistant: you talk, an agent built on the **Claude Agent SDK** works in a folder on your machine, and it answers out loud while the answer is still being written.

- **Hearing:** Fish Audio speech-to-text (`transcribe-1-pro`). Fish has no live speech-to-text, so input is **turn-based**: you speak, pause, and the utterance is transcribed.
- **Speaking:** Fish Audio text-to-speech over a WebSocket (`s2.1-pro`), fed with text as Claude writes it, so output is streamed and can be interrupted.

> `voice-agent` is a placeholder name. Pick the real name before publishing (see rule R5).

---

## 0. Instructions for the implementing agent

1. Build in the milestone order in §11. Run the tests after every milestone and don't start the next one while tests fail.
2. **Verify every library call against the installed package source** before using it (`site-packages/claude_agent_sdk/`, `site-packages/fishaudio/`). The versions are pinned in §4, and the API facts in §5 were checked against exactly those versions. If something doesn't match, stop and report it. Don't guess.
3. Where §5 says "verify live", confirm the behaviour once with a real call during milestone 6 and write the result in the PR.
4. Don't add dependencies beyond §4 without asking.
5. Automated tests must never call the real Anthropic or Fish APIs, or open real audio devices. Use the fakes in §9.
6. Where this spec says MUST, it's not up for interpretation. Where it says SHOULD, deviate only with a written reason in the PR description.

---

## 1. Scope

**In v0.1**
- Continuous listening with local end-of-speech detection.
- Fish speech-to-text for each finished utterance.
- One long-lived Claude session (Agent SDK, `ClaudeSDKClient`) with all Claude Code tools.
- Streaming text-to-speech: speech starts before Claude finishes writing.
- Barge-in: talking over the assistant stops the speech and interrupts Claude's turn.
- Spoken approvals: tools that aren't pre-allowed are asked about out loud; the user answers yes or no.
- Spoken progress when Claude works silently.
- Optional expressive mode using Fish's bracket cues (`[laughing]`, `[whispering]`, …).
- Terminal output: transcript, Claude's full text and tool calls (code, commands and paths appear on screen, never spoken).
- Session resume, mic test, device listing.

**Out of scope for v0.1:** live speech-to-text (Fish doesn't offer it), wake word, GUI or web UI, multiple users, a hosted mode, phone calls, Fish Agents (the hosted agent product), custom in-process tools, subagent definitions.

---

## 2. Non-negotiable rules

**Compliance and credentials**
- **R1.** All Claude traffic goes through the official `claude-agent-sdk`, which runs Claude Code. The code MUST NOT call `api.anthropic.com` (or any Anthropic endpoint) itself, MUST NOT use third-party "Claude SDK" wrappers, and MUST NOT proxy requests.
- **R2.** The code MUST NOT read, copy, log or transmit Claude credentials: no `.credentials.json`, no Keychain, no token values. Authentication is entirely Claude Code's job. The Fish API key is read from the environment and sent only to Fish; it MUST NOT be printed or logged.
- **R3.** The only Claude-credential logic allowed:
  - (a) printing *which* credential source Claude Code will pick, based only on *whether* certain environment variables are set (never their values), see §6.15;
  - (b) the opt-in `--ignore-api-key` flag, which removes `ANTHROPIC_API_KEY` from `os.environ` before the SDK starts.
- **R4.** Self-hosted only: one person, on their own machine. No server mode, no shared instance, no multi-user features, no public endpoints.
- **R5.** Branding: the product has its own name. It MUST NOT be called "Claude Code…" or imitate Claude Code's look. "Powered by Claude" is fine.
- **R6.** The README describes Claude authentication neutrally: "Requires Claude Code to be installed and signed in; see Anthropic's authentication docs." It MUST NOT market the project as a way to use a Claude subscription instead of an API key.

**Safety and cost**
- **R7.** Never use `bypassPermissions` or `--dangerously-skip-permissions`.
- **R8.** No secrets in the repo. `.env` is git-ignored; ship `.env.example` only.
- **R9.** CI fails if the package source (`voice_agent/`, not dependencies) contains any of: `.credentials.json`, `api.anthropic.com`, `anthropic-beta`, `keychain` (case-insensitive).
- **R10.** Only confirmed utterances are sent to Fish speech-to-text (§6.3). Coughs, clicks and the assistant's own voice are never sent.

---

## 3. Architecture

```
 mic 16 kHz ─► local speech detection ─► utterance (after you pause) ─► Fish speech-to-text ─► text
                    │ "user started talking"                                                  │
                    ▼                                                                         ▼
               barge-in / answer                                                VoiceAgent (turn state)
                                                                                              │ query()
                                                                                              ▼
                                                                         ClaudeSDKClient ─► Claude Code
                                                                                              │ stream events
                                                                                              ▼
 speaker ◄── PCM ◄── WAV decoder ◄── Fish TTS WebSocket (one per text block) ◄── speech filter
```

| Module | Responsibility |
|---|---|
| `config.py` | Settings from CLI flags, env vars and `.env` |
| `audio.py` | `Microphone`, `SpeechDetector`, `UtteranceSegmenter` (pure logic), `Speaker` |
| `speech.py` | `FishSpeech`: `transcribe()` and `synthesize()` |
| `wav.py` | WAV encoding for speech-to-text; streaming WAV decoder for playback |
| `textfilter.py` | Streaming markdown-to-speech filter (and expressive-cue handling) |
| `agent.py` | `VoiceAgent`: turn state, Claude message handling, speech queue, barge-in, approvals, progress |
| `__main__.py` | Wiring, startup output, mic test, device listing |

`agent.py` MUST NOT import audio or Fish libraries, so it can be tested with fakes. It only uses a `synthesize(text_async_iterable)` interface that yields `(PcmFormat, pcm_bytes)`.

---

## 4. Stack and pinned versions

- Python ≥ 3.10, asyncio throughout.
- `claude-agent-sdk>=0.2.165,<0.3`. 0.2.165 bundles Claude Code CLI 2.1.294.
- `fish-audio-sdk>=1.3,<2` (import name `fishaudio`). 1.3.0 is the latest release (March 2026).
- `sounddevice>=0.5` (PortAudio; Linux needs `libportaudio2`).
- `numpy>=1.26`
- `webrtcvad-wheels>=2.0.14`
- `python-dotenv>=1.0`
- Dev: `pytest>=8`, `pytest-asyncio>=0.23` (`asyncio_mode = "auto"`), `ruff`.
- Packaging: `pyproject.toml`, console script `voice-agent = voice_agent.__main__:main`.

---

## 5. Verified API facts (and gotchas)

**Claude Agent SDK**
1. `ClaudeSDKClient(options=ClaudeAgentOptions(...))` is an async context manager. Use `query(str)`, `receive_messages()` (endless async iterator) and `interrupt()`.
2. Use **one long-lived `receive_messages()` loop**, not `receive_response()`. The latter stops after each `ResultMessage`, which breaks interrupts and queued input.
3. Use the client only inside the event loop and async context where it was connected. Tasks created inside the `async with` block are fine.
4. Message types: `StreamEvent(uuid, session_id, event: dict, parent_tool_use_id)` carries raw API stream events. `AssistantMessage(content, model, parent_tool_use_id, …)`, `ToolUseBlock(id, name, input)`, `SystemMessage(subtype, data)` (subtype `"init"`, data has `session_id`, `model`), `ResultMessage(subtype, is_error, session_id, total_cost_usd, errors, result, terminal_reason, origin, …)`.
5. After `interrupt()`, a `ResultMessage` arrives with `terminal_reason` `"aborted_streaming"` or `"aborted_tools"`. Stream events of the interrupted turn may still arrive before it.
6. `ResultMessage.origin` is a dict with `kind`. Only `None` or `kind == "human"` is the result of *our* prompt. Others (for example `"task-notification"`) MUST NOT end our turn.
7. `parent_tool_use_id` set means subagent output. It MUST NOT be spoken.
8. `system_prompt={"type": "preset", "preset": "claude_code", "append": "..."}` keeps Claude Code's prompt and adds ours.
9. `permission_mode`: `"default" | "acceptEdits" | "plan" | "bypassPermissions" | "dontAsk" | "auto"`. `"dontAsk"` means: deny anything not pre-approved.
10. `can_use_tool(tool_name: str, input: dict, context: ToolPermissionContext) -> PermissionResultAllow | PermissionResultDeny`. `PermissionResultDeny(message=..., interrupt=bool)`. The SDK then passes `--permission-prompt-tool stdio` itself.
11. Tools in `allowed_tools` skip `can_use_tool`. The SDK emits `CanUseToolShadowedWarning` about this on every start. That's intended here; suppress exactly that category with a comment.
12. Claude Code auto-approves some read-only Bash commands (for example `echo`) even in `"default"` mode. Approval tests MUST use a tool that always asks, such as `Write`.
13. `setting_sources=None` loads user, project and local settings (`CLAUDE.md`, skills, `.claude/`).
14. The SDK passes `os.environ` to Claude Code; `options.env` can add or override but **cannot unset**. To drop a variable, remove it from `os.environ` before connecting.
15. The SDK uses its bundled CLI before any `claude` on `PATH`; both share the same stored sign-in.
16. Claude Code's credential order: cloud provider vars (`CLAUDE_CODE_USE_BEDROCK` / `_VERTEX` / `_FOUNDRY`) > `ANTHROPIC_AUTH_TOKEN` > `ANTHROPIC_API_KEY` (always used in SDK mode when present) > `apiKeyHelper` > `CLAUDE_CODE_OAUTH_TOKEN` > profiles > `/login` sign-in.

**Fish Audio: speech-to-text**
17. `AsyncFishAudio(api_key=...)` reads `FISH_API_KEY` by default.
18. Fish speech-to-text is **batch only**: `POST /v1/asr`, one file per request, synchronous result. Fish documents no live or streaming speech-to-text.
19. `await client.asr.transcribe(audio=<file bytes>, language=..., include_timestamps=False, request_options=...)` returns an object with `.text`. Pass `language` **only when set**: passing `None` sends a null.
20. **The model is chosen with a `model` HTTP header**, which the SDK's `transcribe()` has no parameter for. Send it with `request_options=RequestOptions(additional_headers={"model": "transcribe-1-pro"})` (`fishaudio.core.RequestOptions`; the SDK merges `additional_headers` into the request). The value must be exactly lowercase. A missing or misspelled header is silently served and billed as `transcribe-1`.
21. `transcribe-1-pro` is Fish's recommended model; `transcribe-1` is the default. Both accept WAV; **raw PCM is rejected**, so wrap audio in a WAV container. Audio under ~0.08 s returns `audio_too_short`.
22. With `transcribe-1-pro`, the transcript can contain inline speaker markers `<|speaker:N|>` and bracketed sound cues like `[laughter]`. The SDK can't switch those off (its payload has no `diarize` or `tag_audio_events` fields), so **strip them** from the text (§6.4).
23. Errors return JSON with `status`, `message`, `code` and `request_id`. Retry 429 and 5xx once with a short backoff; don't retry other 4xx. Failed requests aren't billed.

**Fish Audio: text-to-speech**
24. `client.tts.stream_websocket(text_async_iterable, config=TTSConfig(...), model=..., speed=..., ws_options=WebSocketOptions(...))` is an async generator of audio bytes. Endpoint `/v1/tts/live`. Client events are `start`, `text`, `flush` and `stop`; server events are `audio` and `finish`. The SDK sends `stop` when the text iterable ends.
25. The TTS model is sent as the `model` header. Fish recommends **`s2.1-pro`**; `s2.1-pro-free` is the same model at no cost but without latency guarantees; `s2-pro` is the predecessor and is the SDK's default; `s1` is deprecated (retired 2026-12-31). The SDK's `Model` type hint lists only older values, but the argument is passed straight into the header (**verify live** that `s2.1-pro` works).
26. `TTSConfig(format="wav"|"pcm"|"mp3"|"opus", latency="normal"|"balanced", reference_id=<voice id>, chunk_length=100..300)`. Fish's guide: `normal` ≈ 500 ms (best quality), `balanced` ≈ 300 ms. **Use `balanced`.** The SDK type rejects `"low"`.
27. **`WebSocketOptions` defaults to a 64 KiB max message size, which audio messages can exceed.** Set `max_message_size_bytes=16 MiB` and `keepalive_ping_timeout_seconds=60`.
28. Fish doesn't document the raw PCM bit depth. **Request `format="wav"`** and read the sample rate, channels and bit depth from the WAV header (§6.6).
29. S2-family models support bracket cues in the text: emotions (`[happy]`, `[sad]`, `[calm]`), tone (`[whispering]`, `[soft tone]`, `[emphasis]`), effects (`[laughing]`, `[sighing]`) and pauses (`[break]`, `[long-break]`). Free-form cues like `[slightly excited]` also work. Sentence-level cues work best at the start of a sentence. Whether they work over the WebSocket is undocumented (**verify live**).
30. Fish's streaming guide recommends whole words with their spaces, punctuation for pauses, and buffering 2–3 audio chunks before playback.

---

## 6. Component specs

### 6.1 Microphone
- 16 000 Hz, mono, int16, 30 ms blocks (480 samples, 960 bytes), via `sounddevice.RawInputStream` with a callback.
- The callback hands frames to asyncio with `loop.call_soon_threadsafe(queue.put_nowait, bytes(indata))`, dropping frames if the queue is full (maxsize 1000).
- Exposes `async def frames()` and `close()`.

### 6.2 Local speech detection
- `voiced = rms(frame) >= threshold and webrtcvad.Vad(2).is_speech(frame, 16000)`. RMS is on the int16 scale.
- Thresholds: `speech_rms` (default 300) normally; `barge_in_rms` (default 1500) while the speaker is playing.
- If barge-in is disabled, frames are ignored entirely while the speaker is playing (half-duplex), **unless** an approval question is waiting for an answer.

### 6.3 Utterance segmenter (pure logic, no I/O)
`process(frame, voiced) -> list[Event]`. Events:

| Event | When | Payload |
|---|---|---|
| `speech` | confirmed: 400 ms of voiced audio since start; once per utterance; used for barge-in | none |
| `utterance` | after a confirmed utterance: 700 ms of continuous unvoiced frames (`--end-silence-ms`), or 30 s total | all audio: 300 ms pre-roll + every frame up to the end |
| `dropped` | the utterance ends before being confirmed | none |

Start detection: ≥ 6 voiced frames in the last 10 (~180 ms). A confirmed utterance never ends as `dropped`. Only `utterance` audio is ever sent to Fish.

### 6.4 Speech-to-text
1. Wrap the PCM in a WAV container (stdlib `wave`, 16 kHz, mono, 16-bit).
2. Call `asr.transcribe` with `include_timestamps=False`, `language` only when configured, and the model header from §5.20 (default `transcribe-1-pro`).
3. Post-process the text:
   - remove `<|speaker:N|>` markers;
   - remove standalone bracketed cues (`[laughter]`, `[music]`, …);
   - collapse whitespace and strip.

   An empty result is ignored.
4. On a 429 or 5xx, retry once after 500 ms. On any other error, print `(speech recognition failed: …)` and keep listening.
5. Transcription runs in its own task fed by a queue, so the mic loop never waits on it. Utterances are transcribed in order.

### 6.5 Speech filter (streaming)
`feed(text) -> list[str]` and `flush() -> list[str]`. Each returned chunk is cleaned, stripped and ends with one space.

- **Release points:** complete lines; within a line, everything up to the last sentence end (`.!?:;` followed by whitespace); and if more than 160 characters are held with no sentence end, cut at the last space. Hold a partial line that starts with `` ` `` or `~` (it may be a fence).
- **Code fences** (` ``` ` or `~~~` at line start) toggle a code state that persists across chunks. On entering, emit `"I've put the code on screen."` once. Text inside is dropped.
- **Line rules:** drop horizontal rules and table separator rows; strip heading `#`, blockquote `>` and list markers (`-`, `*`, `+`, `1.`, `1)`); a table row `| a | b |` becomes `a, b`.
- **Inline rules:** `[text](url)` → `text`; bare URLs → `a link`; `` `code` `` → `code`; remove `**`, `__`, `~~` and `*`; underscore between word characters → space; remove emoji; collapse whitespace.
- **Bracket cues** (`[` 1–30 characters `]`, not followed by `(`):
  - expressive mode off (default): removed;
  - expressive mode on: kept unchanged, so Fish performs them.

### 6.6 Text-to-speech
- **One Fish WebSocket per Claude text block** (from `content_block_start` to `content_block_stop`), plus one per fixed phrase. Fish's protocol finishes a session with `stop`/`finish`. Text before a tool call must be spoken right away, not held in Fish's buffer while the tool runs.
- A job opens a socket only once its first non-empty chunk exists. Empty blocks open no socket.
- Config: `TTSConfig(format="wav", latency="balanced", reference_id=<voice id or None>)`, `model=<setting, default "s2.1-pro">`, `speed` only if not 1.0, `ws_options` per §5.27.
- **WAV stream decoder:**
  - If a message starts with `RIFF…WAVE`, parse `fmt ` (format, channels, rate, bits; handle WAVE_FORMAT_EXTENSIBLE) and skip to the `data` payload. Ignore the data chunk size; streams use placeholder sizes.
  - Accept a header at the start of *any* message, and buffer a header split across messages.
  - Carry odd trailing bytes to the next message so samples stay aligned.
  - Convert to int16: 16-bit pass-through; 32-bit float clamped and scaled; 32-bit int; 24-bit (top 16 bits); 8-bit unsigned.
  - Messages without a header are PCM in the last known format (initial default 44 100 Hz mono 16-bit).

### 6.7 Speaker
- `sounddevice.RawOutputStream` (int16) with a callback pulling from a lock-protected `bytearray`, padding with silence.
- Opened lazily at the first format and reopened if the format changes.
- `play(rate, channels, pcm)` appends. `stop()` clears the buffer immediately.
- **Pre-buffer:** after the buffer has run empty, wait until 150 ms of audio is queued before playing again, or until the job ends (per Fish's guidance §5.30). This avoids stutter.
- `is_playing` is true while the buffer is non-empty or less than 300 ms since the last audio was played (covers room echo).

### 6.8 Speech queue
- FIFO of jobs, processed by one task: Claude text blocks, progress phrases, approval questions, the greeting and error phrases, all in order.
- Each job's synthesis runs as its own task, so barge-in can cancel it. The loop awaits it with `asyncio.wait`, so a cancelled job doesn't kill the loop.
- Synthesis of job N+1 may start while job N's audio is still playing (the speaker buffers it).

### 6.9 Turn state machine (`VoiceAgent`)
State: `turn_active`, `turn_done` (Event), `muted`, `interrupting` (plus an Event for waiting on it), `queued: list[str]`, `permission_future`.

- **`handle_text(text)`** (a transcript):
  1. Print `you    > {text}`.
  2. If an approval is pending, resolve it with the text and return.
  3. Wait while an interrupt is in progress.
  4. If a turn is active (only possible with barge-in off), append to `queued`, print `(noted, I'll get to it after this)` and return.
  5. Otherwise begin a turn.
- **Begin turn:** set the state *synchronously* (`turn_active = True`, `turn_done.clear()`, `muted = False`, reset the progress state) before awaiting `client.query(text)`.
- **End turn** (our `ResultMessage`):
  1. Close any open text block.
  2. Set `turn_active = False` and `muted = False`, and set `turn_done`.
  3. If `queued` is non-empty, join it with spaces and begin a new turn.
- **Errors:** on a `ResultMessage` with `is_error` and not muted, print the errors and speak `"Sorry, something went wrong there."`
- **Connection loss:** if the Claude message loop ends or raises, print `(lost the connection to Claude Code: …)` and set a `closed` event; the app then exits cleanly.

### 6.10 Handling Claude's messages
| Message | Action |
|---|---|
| `StreamEvent`, subagent or muted | ignore |
| `content_block_start` with `content_block.type == "text"` | open a text block: new speech job + new filter, print `claude > ` |
| `content_block_delta` with `delta.type == "text_delta"` | print the raw text; feed the filter; queue the chunks; mark "spoke since last tool" |
| `content_block_stop` | flush the filter, close the job |
| `AssistantMessage`, subagent or muted | ignore |
| `ToolUseBlock` (deduplicate by id) | print `· {name} {summary}`; progress phrase (§6.12) |
| `SystemMessage` `init` | store `session_id`; log the model at debug level |
| `ResultMessage`, injected origin (§5.6) | ignore |
| `ResultMessage` (ours) | store `session_id`; log cost at debug level; end the turn |
| anything else | ignore |

### 6.11 Barge-in
Trigger: the segmenter emits `speech`, barge-in is enabled, no approval is pending, and (a turn is active or speech is playing or queued).

1. If already interrupting, do nothing.
2. Stop the speech: `speaker.stop()`, cancel all queued jobs, the current job and the open text block, and cancel the synthesis task.
3. If a turn is active:
   - set `muted = True` and print `(interrupted)`;
   - call `client.interrupt()` (log failures);
   - wait for `turn_done` for up to 10 s. On timeout, log a warning and end the turn locally.
4. Clear the interrupting state.

The user's utterance is then transcribed after they pause and starts the next turn.

### 6.12 Progress phrases
On a main-agent `ToolUseBlock`, speak a phrase only if:
- no text was spoken since the previous tool call in this turn;
- the tool is in `allowed_tools`;
- the phrase differs from the last progress phrase.

Then reset "spoke since last tool".

| Tool | Phrase |
|---|---|
| Read, Glob, Grep, LS | Looking through the files. |
| Bash | Running a command. |
| Edit, MultiEdit, Write, NotebookEdit | Making the changes. |
| WebSearch | Searching the web. |
| WebFetch | Reading a web page. |
| Task, Agent | Handing part of this to a helper. |
| TodoWrite, AskUserQuestion | (none) |
| anything else | Working on it. |

### 6.13 Spoken approvals (`can_use_tool`)
- If muted, return `PermissionResultDeny(message="The user interrupted.", interrupt=True)`.
- Print `? wants to use {tool}: {summary}`. Create the permission future, then queue the spoken question `"I'd like to {description}. Is that okay?"`.
- While the future is pending, detected speech MUST NOT barge in; it only stops the question's playback (the user is answering).
- Wait up to 45 s. On timeout, print `(no answer, so that's a no)` and deny with "The user did not answer in time."
- Answer parsing (`parse_yes_no`): lowercase, strip punctuation, match whole words or phrases.
  - `"why not"` → yes.
  - Otherwise any negative wins: no, nope, nah, don't, dont, do not, stop, cancel, wait, never, hold on, nee, niet, neen, liever niet.
  - Then any positive: yes, yeah, yep, yup, sure, ok, okay, go ahead, go for it, do it, fine, approve(d), allow, absolutely, of course, please do, ja, jawel, prima, doe maar, goed, akkoord.
  - Anything else is unclear.
- Yes → `PermissionResultAllow()`. No or unclear → `PermissionResultDeny(message='The user did not approve. They said: "<answer>"')`.
- Always reset the future in `finally`.

**Spoken description** (`describe_tool`):

| Tool | Description |
|---|---|
| Bash, with `description` | `run a command to <description, first letter lowercased>` |
| Bash, without | `run a <program basename> command` |
| Write | `write the file <basename>` |
| Edit, MultiEdit | `edit <basename>` |
| NotebookEdit | `edit the notebook <basename>` |
| WebFetch | `open <host>` |
| WebSearch | `search the web for <query>` |
| `mcp__server__tool` | `use <tool> from <server>` (underscores → spaces) |
| other | `use the <tool> tool` |

**Screen summary** (`screen_summary`): the first present of `command`, `file_path`, `notebook_path`, `url`, `pattern`, `query`, `path` (max 200 characters), else compact JSON (max 120).

### 6.14 Claude options
```python
ClaudeAgentOptions(
    system_prompt={"type": "preset", "preset": "claude_code",
                   "append": SPEECH_PROMPT + (EXPRESSIVE_PROMPT if settings.expressive else "")},
    include_partial_messages=True,
    allowed_tools=settings.allowed_tools,   # default: Read, Glob, Grep, WebSearch, WebFetch
    permission_mode="default" if settings.voice_approvals else "dontAsk",
    can_use_tool=agent.can_use_tool if settings.voice_approvals else None,
    cwd=settings.workdir,
    model=settings.claude_model,            # None = Claude Code's default
    resume=settings.resume,
)
```

**`SPEECH_PROMPT`** (use verbatim):
```
# Voice conversation
You are talking with the user through a voice interface. Their messages come from speech recognition and may contain recognition mistakes; if something looks garbled, ask a short question instead of guessing. Everything you write is read aloud by a text-to-speech voice, so:
- Answer in short, natural spoken sentences. Reply in the language the user speaks.
- No markdown: no headings, bullet lists, tables, bold text or emojis.
- Never read out code, file contents, long paths, commands or URLs. Write code to files and say in one sentence what you did; the user can see details on screen.
- Say numbers, dates and units the way a person would say them.
- For long results, give the gist in two or three sentences and offer more detail.
- Before a task that takes a while, say in one short sentence what you are about to do.
```

**`EXPRESSIVE_PROMPT`** (only with `--expressive`; use verbatim):
```
- You may add a delivery cue in square brackets at the start of a sentence, such as [happy], [calm], [soft tone] or [laughing]. Use one only when it truly fits, at most once every few sentences, and never in code, file names or quotes.
```

### 6.15 Startup and shutdown
1. Load `.env` (python-dotenv), then parse flags (§7).
2. Utility modes, each exiting afterwards:
   - `--list-devices`: print `sounddevice.query_devices()`.
   - `--mic-test`: show live RMS, a speech marker and a level bar for 10 s, then print the loudest level and advice for `--speech-rms`.
3. Exit with a clear message if `FISH_API_KEY` is missing. If `--ignore-api-key`, `os.environ.pop("ANTHROPIC_API_KEY", None)`.
4. Print `Working folder: …`, `Voice: <voice id or default> (<tts model>)`, `Hearing: <stt model>` and `Claude sign-in: …`. The sign-in line follows §5.16 using only variable *presence*: cloud provider / `ANTHROPIC_AUTH_TOKEN` / "your API key (ANTHROPIC_API_KEY)" / "a token from `claude setup-token`" / "Claude Code's own sign-in (check with `claude`, then /status)".
5. Connect Claude, start the agent tasks, print `Ready. Just start talking. Ctrl+C to quit.`, then speak the greeting (default `"Hi, I'm listening."`; `--no-greeting` turns it off).
6. Run the listen, transcribe and connection-closed tasks; stop on the first one that finishes and re-raise its exception if it has one.
7. Ctrl+C: cancel the tasks, stop the audio, disconnect Claude, print `Session <id> (continue it with --resume <id>)` and `Bye.`

### 6.16 Terminal output
```
         (listening…)          ← while you speak, after confirmation; removed when the transcript arrives
you    > <transcript>
claude > <streamed text as it arrives>
         · <Tool> <summary>
         ? wants to use <Tool>: <summary>
         (interrupted) | (noted, I'll get to it after this) | (error: …)
```
- The `(listening…)` indicator only appears when stdout is a TTY and no `claude >` line is streaming.
- Logging uses the `logging` module, logger `voice_agent`: WARNING by default, DEBUG with `--debug`.

**Debug metrics per turn:**
- end of speech → transcript (and audio length)
- transcript → first text delta
- first text delta → first audio byte
- Claude cost and duration

---

## 7. Configuration

Flags override env vars, which override defaults. `.env.example` documents every env var.

| Flag | Env | Default |
|---|---|---|
| — | `FISH_API_KEY` | required |
| `--voice-id` | `FISH_VOICE_ID` | Fish's default voice (any library voice or your own clone) |
| `--tts-model` | `FISH_TTS_MODEL` | `s2.1-pro` (`s2.1-pro-free`, `s2-pro`) |
| `--stt-model` | `FISH_STT_MODEL` | `transcribe-1-pro` (`transcribe-1`) |
| `--latency` | `FISH_LATENCY` | `balanced` (`normal`/`balanced`) |
| `--speed` | `FISH_SPEED` | `1.0` |
| `--expressive` | `VOICE_AGENT_EXPRESSIVE=1` | off |
| `--language` | `VOICE_AGENT_LANGUAGE` | auto (speech-to-text hint, e.g. `nl`) |
| `--workdir` | `VOICE_AGENT_WORKDIR` | current folder |
| `--model` | `CLAUDE_MODEL` | Claude Code default |
| `--allowed-tools` | `VOICE_AGENT_ALLOWED_TOOLS` | `Read,Glob,Grep,WebSearch,WebFetch` |
| `--no-voice-approvals` | `VOICE_AGENT_VOICE_APPROVALS=0` | approvals on |
| `--no-barge-in` | `VOICE_AGENT_BARGE_IN=0` | barge-in on |
| `--speech-rms` | `VOICE_AGENT_SPEECH_RMS` | 300 |
| `--barge-in-rms` | `VOICE_AGENT_BARGE_IN_RMS` | 1500 |
| `--end-silence-ms` | `VOICE_AGENT_END_SILENCE_MS` | 700 |
| `--input-device` / `--output-device` | `VOICE_AGENT_INPUT_DEVICE` / `_OUTPUT_DEVICE` | system default (number or name) |
| `--ignore-api-key` | `VOICE_AGENT_IGNORE_API_KEY=1` | off |
| `--resume <id>` | — | new session |
| `--no-greeting`, `--debug`, `--list-devices`, `--mic-test` | — | — |

Approval timeout (45 s), playback pre-buffer (150 ms) and VAD aggressiveness (2) are settings fields without flags.

---

## 8. Project layout
```
voice-agent/
  voice_agent/  __init__.py  __main__.py  config.py  agent.py  audio.py  speech.py  wav.py  textfilter.py
  tests/        test_textfilter.py  test_wav.py  test_segmenter.py  test_speech.py  test_agent.py
  pyproject.toml  README.md  .env.example  .gitignore  LICENSE
```
`.gitignore`: `.venv/`, `__pycache__/`, `*.egg-info/`, `.pytest_cache/`, `.ruff_cache/`, `.env`.

---

## 9. Testing

**Fakes** (in tests only):
- `FakeClient` (Claude): `query` records the text; `interrupt` counts calls; `receive_messages` yields from an `asyncio.Queue`. Tests push real SDK message objects.
- `FakeSpeech`: `synthesize` joins its text into a `spoken` list and yields one tiny PCM piece; `transcribe` returns scripted text.
- `FakeSpeaker`: records `play`/`stop`; `is_playing = False`.
- Fish WebSocket fake: monkeypatch `fishaudio.resources.tts.aconnect_ws` with an async context manager that yields a fake socket. It records sent msgpack events and replies with scripted `audio` and `finish` events.
- Fish HTTP fake: monkeypatch the SDK's async client request, or use `httpx.MockTransport`, to capture the ASR request and return a scripted JSON response.

**Required unit tests**
- *Text filter:* sentence-boundary release while streaming; inline markdown; URLs and snake_case; headings, lists, quotes and rules; a code fence split across chunks (notice spoken once, contents dropped); tables; the long-text cut; emoji; bracket cues removed by default and kept in expressive mode; `[text](url)` links still become `text`.
- *WAV decoder:* whole file; header split over three messages; an odd-byte split; a second header in a later message; raw PCM with no header; 32-bit float conversion.
- *Segmenter:* a normal utterance gives `speech` then `utterance` (with pre-roll); a short click is `dropped`; scattered noise never starts; the max length ends at 30 s.
- *Speech-to-text:*
  - the request carries the `model: transcribe-1-pro` header;
  - the body is msgpack with WAV audio, `ignore_timestamps: true`, and `language` only when set;
  - speaker markers and cues are stripped;
  - a 5xx is retried once; a 400 is not.
- *Text-to-speech* (against the real `fishaudio` code with the WebSocket faked):
  - URL `/v1/tts/live`, `model` header `s2.1-pro`, `max_message_size_bytes` = 16 MiB;
  - the sent events are `start` (format `wav`, latency `balanced`, `reference_id`), then the text events, then `stop`;
  - the decoded PCM and format are correct when a WAV is split over two `audio` events.
- *Agent flows:*
  - an answer is spoken without markdown;
  - subagent text is not spoken;
  - progress phrase rules;
  - no phrase for a tool that needs approval;
  - barge-in interrupts, and the old turn's late output is never spoken;
  - an approval with yes → Allow (and no new turn);
  - no → Deny containing the answer;
  - input during an active turn is queued, then sent;
  - an injected result doesn't end the turn.
- *Helpers:* `parse_yes_no`, including Dutch and "why not"; `describe_tool`.

**CI:** ruff (E, F, W, B, UP, ASYNC), pytest, and the forbidden-string check from R9.

**Manual end-to-end checklist** (record the results in the PR, including the "verify live" items from §5):
1. `--mic-test` shows clear separation between quiet and speech.
2. A question gets a spoken answer after you pause, and speech starts before Claude's text finishes.
3. `s2.1-pro` works as the TTS model header; `s2.1-pro-free` also works.
4. Latency: measure end of speech → transcript for 5 utterances with `transcribe-1-pro` and with `transcribe-1`. Write down both; keep `transcribe-1-pro` unless it's clearly slower for short utterances.
5. "Create a file named voice-check.txt containing hello" asks out loud; "yes" creates it; on a second run, "no" doesn't.
6. "Count from 1 to 300 in words": talk over it; it stops, then answers your new question after you pause.
7. A silent read-only task speaks a progress phrase.
8. A code answer shows the code on screen and speaks "I've put the code on screen."
9. A Dutch conversation works with `--language nl` and with auto-detect.
10. `--expressive`: a cue like `[laughing]` is performed, not read aloud.
11. Your own cloned voice works via `--voice-id`.
12. Ctrl+C prints the session id; `--resume <id>` remembers the conversation.
13. With speakers and `--no-barge-in`, the assistant never transcribes its own voice.

---

## 10. Definition of done
- All automated tests and lint pass; the R9 check passes.
- Every item on the manual checklist passes on macOS with headphones; the "verify live" results are written down.
- README covers what it is, requirements (Fish API key, Claude Code signed in), setup, settings, "good to know" (headphones, turn-based input: it listens until you pause, Fish usage billed to your Fish account, Claude usage billed to whatever Claude Code is signed in with) and how to run tests, worded per R6, plus the footer "Built on the Claude Agent SDK. Not affiliated with Anthropic or Fish Audio."
- No secrets, credentials or personal paths in the repo.

---

## 11. Milestones (build in this order)
1. **Skeleton:** packaging, config, `.env.example`, `.gitignore`, CI with lint and the R9 check.
2. **Pure logic with tests:** `textfilter.py`, `wav.py`, the segmenter.
3. **Agent core with fakes:** `agent.py` with all agent-flow tests.
4. **Fish with fakes:** `speech.py` (speech-to-text and text-to-speech) with its tests.
5. **Audio and wiring:** `audio.py` devices, `__main__.py`, mic test, device listing.
6. **Manual end-to-end:** go through the §9 checklist, settle the "verify live" items, tune the defaults, finish the README.

---

## 12. Later (not v0.1)
- **Fewer reconnects:** one Fish WebSocket per turn instead of per text block, using `flush` at each block end (Fish recommends reusing connections). This needs a way to keep the socket alive during long tool runs and to reopen it after barge-in.
- **Faster turn ending:** start transcribing speculatively after 400 ms of silence and throw the result away if you keep talking, so the transcript is ready sooner.
- **Live speech-to-text,** if Fish adds it. Until then, input stays turn-based.
- **Smarter barge-in,** so coughs and echo don't interrupt.
- **Echo cancellation,** so barge-in works with speakers.
- **Push-to-talk mode.**
- **Phone access:** Fish Agents with a phone number is a separate hosted product. Connecting it to Claude Code would need a public endpoint into your machine, which R4 rules out, so it's not planned.
- **Custom tools:** in-process tools (`@tool` + `create_sdk_mcp_server`) for your own services.
- **Background work:** a subagent for long tasks while the conversation continues.
- **"Undo that"** via file checkpoints.
