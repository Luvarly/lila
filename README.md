# Lila

A personal voice assistant. You talk, an agent works in a folder on your machine, and it answers out loud while the answer is still being written. Powered by Claude, through the Claude Agent SDK.

- **Hearing:** Fish Audio speech-to-text (`transcribe-1-pro`). Input is turn-based: you speak, pause, and what you said is transcribed.
- **Speaking:** Fish Audio streaming text-to-speech (`s2.1-pro`). Speech starts before the answer is finished, and you can talk over it to interrupt.
- **Doing:** the agent can read, search and change files and use the web. Claude Code's auto mode decides which actions are safe, so Lila rarely asks. Whatever it does ask about, or every tool that isn't pre-approved with `--no-auto-mode`, is asked out loud; answer yes or no.
- **Background work:** longer jobs, like research or a bigger change, go to a background helper, so you can keep talking. Lila tells you the result when it's done. If the helper needs approval, Lila asks out loud: "My helper would like to…".
- **Screen:** your transcript, the full answer and every tool call are printed. Code, commands and paths appear on screen and are never read aloud.
- **Memory:** Lila remembers what's worth knowing about you between conversations, such as your name, the people and projects you mention and how you like things done. It's kept as plain Markdown files in `~/.lila/memory`, shared by every working folder, so you can read, edit or delete them any time. This is Claude Code's own memory feature, pointed at a folder of Lila's.
- **Personality:** warm, quick and to the point, with a dry sense of humour. Tell it how you'd rather it be, and it remembers that too.
- **HUD:** `lila --web` opens a live view in your browser: a lilac reactor that shows whether Lila is listening, thinking or speaking, a trace of who spoke when, the context window, background helpers as satellites, live captions, every tool call, and what the session has used. It only shows; it never controls Lila.
- **Clipboard and screen:** say "what's this?" and Lila reads what you copied (text, an image or files). Say "what am I looking at?" and it takes a screenshot of your main screen. It only does either when you ask, and each use shows up on screen.

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
| `--no-auto-mode` | `LILA_AUTO_MODE=0` | auto mode on (off = ask about every tool that isn't pre-allowed) |
| `--no-voice-approvals` | `LILA_VOICE_APPROVALS=0` | approvals on (off = deny anything not pre-allowed) |
| `--no-barge-in` | `LILA_BARGE_IN=0` | barge-in on (off = never listen while speaking) |
| `--speech-rms` | `LILA_SPEECH_RMS` | `300` |
| `--barge-in-rms` | `LILA_BARGE_IN_RMS` | `1500` |
| `--end-silence-ms` | `LILA_END_SILENCE_MS` | `700` |
| `--input-device` / `--output-device` | `LILA_INPUT_DEVICE` / `LILA_OUTPUT_DEVICE` | system default (number or name) |
| `--ignore-api-key` | `LILA_IGNORE_API_KEY=1` | off: hide `ANTHROPIC_API_KEY` from Claude Code |
| `--resume <id>` | — | new session |
| `--web` | — | off: open the HUD in your browser |
| `--no-greeting`, `--debug`, `--list-devices`, `--mic-test` | — | — |

## Good to know

- **Use headphones.** With speakers, the assistant can hear itself. Barge-in then needs a loud voice (`--barge-in-rms`), and `--no-barge-in` makes it stop listening while it talks.
- **It listens until you pause.** Fish has no live speech-to-text, so an utterance counts as finished after about 0.7 s of silence (`--end-silence-ms`). To save time, Lila already starts transcribing after 0.4 s and throws that away if you keep talking.
- **Talking over it** pauses the voice at once. Claude is only interrupted once your words are transcribed; a cough or a click just lets it carry on. While a background helper is working, Claude isn't interrupted, because that would stop the helper too. Lila goes quiet instead, and Claude reads what you said at its next step.
- **Fish usage** (speech-to-text and text-to-speech) is billed to your Fish account. A short pause mid-sentence costs one extra speech-to-text request.
- **Claude usage** is billed to whatever Claude Code is signed in with. Lila prints which sign-in Claude Code will use at startup.
- **If Claude Code stops**, Lila reconnects to the same conversation, up to three times in a row. Whatever Claude was doing at that moment is lost, background helpers included. Quitting stops them too.
- **Screenshots and clipboard contents go to Claude**, like everything else you say. Clear anything private before you ask.
- **The HUD is local.** It's served on `127.0.0.1` (port 8484, or a free one if that's taken), only answers requests addressed to this machine, and has no buttons. Its spend figure is Claude Code's estimate at API prices; with a subscription sign-in that isn't what you pay. Everything it needs ships with Lila, so it makes no outside requests (the Saira font is included under the SIL Open Font License, `src/lila/saira-OFL.txt`).
- When you quit with Ctrl+C, Lila prints the session id; `--resume <id>` continues that conversation.

## Tests

```sh
uv run pytest
uv run ruff check .
```

The tests use fakes and never call Fish or Claude or open audio devices.

---

Built on the Claude Agent SDK. Not affiliated with Anthropic or Fish Audio.
