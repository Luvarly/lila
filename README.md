# Lila

A personal voice assistant. You talk, an agent works in a folder on your machine, and it answers out loud while the answer is still being written. Powered by Claude, through the Claude Agent SDK.

- **Hearing:** Fish Audio speech-to-text (`transcribe-1-pro`). Input is turn-based: you speak, pause, and what you said is transcribed.
- **Speaking:** Fish Audio streaming text-to-speech (`s2.1-pro`). Speech starts before the answer is finished, and you can talk over it to interrupt.
- **Doing:** the agent can read, search and change files and use the web. Tools that aren't pre-approved are asked about out loud; answer yes or no.
- **Screen:** your transcript, the full answer and every tool call are printed. Code, commands and paths appear on screen and are never read aloud.

## Requirements

- Python 3.10 or newer and [uv](https://docs.astral.sh/uv/).
- Claude Code installed and signed in; see Anthropic's authentication docs.
- A Fish Audio API key.
- A microphone and speakers or headphones. On Linux, install PortAudio (`sudo apt install libportaudio2`).

## Setup

```sh
uv sync
cp .env.example .env    # then put your FISH_API_KEY (and optionally FISH_VOICE_ID) in .env
uv run lila --mic-test  # check your microphone levels
uv run lila
```

Lila reads `.env` from the current folder (or a parent folder). Real environment variables win over `.env`, and command-line flags win over both.

## Settings

| Flag | Env | Default |
|---|---|---|
| — | `FISH_API_KEY` | required |
| `--voice-id` | `FISH_VOICE_ID` | Fish's default voice (any library voice or your own clone) |
| `--tts-model` | `FISH_TTS_MODEL` | `s2.1-pro` (`s2.1-pro-free`, `s2-pro`) |
| `--stt-model` | `FISH_STT_MODEL` | `transcribe-1-pro` (`transcribe-1`) |
| `--latency` | `FISH_LATENCY` | `balanced` (`normal`) |
| `--speed` | `FISH_SPEED` | `1.0` |
| `--expressive` | `LILA_EXPRESSIVE=1` | off: let Claude use delivery cues like `[laughing]` |
| `--language` | `LILA_LANGUAGE` | auto-detect (a hint such as `nl`) |
| `--workdir` | `LILA_WORKDIR` | current folder |
| `--model` | `CLAUDE_MODEL` | Claude Code's default (e.g. `opus`, `sonnet`, `haiku`) |
| `--effort` | `CLAUDE_EFFORT` | Claude Code's default (`low`, `medium`, `high`, `xhigh`, `max`) |
| `--allowed-tools` | `LILA_ALLOWED_TOOLS` | `Read,Glob,Grep,WebSearch,WebFetch` |
| `--no-voice-approvals` | `LILA_VOICE_APPROVALS=0` | approvals on (off = deny anything not pre-allowed) |
| `--no-barge-in` | `LILA_BARGE_IN=0` | barge-in on (off = never listen while speaking) |
| `--speech-rms` | `LILA_SPEECH_RMS` | `300` |
| `--barge-in-rms` | `LILA_BARGE_IN_RMS` | `1500` |
| `--end-silence-ms` | `LILA_END_SILENCE_MS` | `700` |
| `--input-device` / `--output-device` | `LILA_INPUT_DEVICE` / `LILA_OUTPUT_DEVICE` | system default (number or name) |
| `--ignore-api-key` | `LILA_IGNORE_API_KEY=1` | off: hide `ANTHROPIC_API_KEY` from Claude Code |
| `--resume <id>` | — | new session |
| `--no-greeting`, `--debug`, `--list-devices`, `--mic-test` | — | — |

## Good to know

- **Use headphones.** With speakers, the assistant can hear itself. Barge-in then needs a loud voice (`--barge-in-rms`), and `--no-barge-in` makes it stop listening while it talks.
- **It listens until you pause.** Fish has no live speech-to-text, so an utterance counts as finished after about 0.7 s of silence (`--end-silence-ms`). To save time, Lila already starts transcribing after 0.4 s and throws that away if you keep talking.
- **Talking over it** pauses the voice at once. Claude is only interrupted once your words are transcribed; a cough or a click just lets it carry on.
- **Fish usage** (speech-to-text and text-to-speech) is billed to your Fish account. A short pause mid-sentence costs one extra speech-to-text request.
- **Claude usage** is billed to whatever Claude Code is signed in with. Lila prints which sign-in Claude Code will use at startup.
- **If Claude Code stops**, Lila reconnects to the same conversation, up to three times in a row. Whatever Claude was doing at that moment is lost.
- When you quit with Ctrl+C, Lila prints the session id; `--resume <id>` continues that conversation.

## Tests

```sh
uv run pytest
uv run ruff check .
```

The tests use fakes and never call Fish or Claude or open audio devices.

---

Built on the Claude Agent SDK. Not affiliated with Anthropic or Fish Audio.
