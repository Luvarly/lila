"""Wiring, startup output, mic test and device listing."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
import time
import warnings
import webbrowser
from collections.abc import Mapping

import sounddevice as sd
from claude_agent_sdk import CanUseToolShadowedWarning, ClaudeSDKClient
from dotenv import find_dotenv, load_dotenv

from .agent import GREETING, MEMORY_DIR, VoiceAgent, build_options
from .audio import (
    FRAME_SAMPLES,
    RATE,
    START_VOICED,
    START_VOICED_OVER_SPEECH,
    Microphone,
    Speaker,
    SpeechDetector,
    UtteranceSegmenter,
    rms,
)
from .config import Settings, parse_args
from .speech import FishSpeech
from .term import LogFormatter, dim, error, note, paint
from .web import Hud

MAX_RECONNECTS = 3
RECONNECT_DELAY = 2.0  # seconds, times the attempt number
STABLE_CONNECTION = 60.0  # a connection that lasted this long resets the attempt count


def claude_sign_in(env: Mapping[str, str] = os.environ) -> str:
    """Which credential Claude Code will pick, judged only by which variables are set."""
    if any(env.get(f"CLAUDE_CODE_USE_{p}") for p in ("BEDROCK", "VERTEX", "FOUNDRY")):
        return "a cloud provider (Bedrock, Vertex or Foundry)"
    if env.get("ANTHROPIC_AUTH_TOKEN"):
        return "ANTHROPIC_AUTH_TOKEN"
    if env.get("ANTHROPIC_API_KEY"):
        return "your API key (ANTHROPIC_API_KEY)"
    if env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return "a token from `claude setup-token`"
    return "Claude Code's own sign-in (check with `claude`, then /status)"


async def listen(mic: Microphone, agent: VoiceAgent, settings: Settings) -> None:
    detector = SpeechDetector(settings.vad_aggressiveness)
    segmenter = UtteranceSegmenter(end_silence_ms=settings.end_silence_ms)
    async for frame in mic.frames():
        agent.mic_level = rms(frame)
        playing = agent.speaker.is_playing
        if playing and not settings.barge_in and not agent.approval_pending:
            continue  # half-duplex: never hear our own voice
        # Stays high while she's paused mid-speech, or the noise that paused her keeps the utterance open.
        speaking = agent.speaker.is_speaking
        threshold = settings.barge_in_rms if speaking else settings.speech_rms
        need = START_VOICED_OVER_SPEECH if speaking else START_VOICED
        for event in segmenter.process(frame, detector.is_voiced(frame, threshold), need):
            if event.kind == "speech":
                agent.show_listening(True)
                agent.on_user_speech()
            elif event.kind == "pause":
                agent.on_pause(event.audio)
            elif event.kind == "utterance":
                agent.on_utterance(event.audio, event.early)


async def converse(client: ClaudeSDKClient, agent: VoiceAgent, background: list) -> None:
    """Serve one Claude connection. Returns when it drops; raises if a background task fails."""
    agent.attach(client)
    # Created inside the client's context, as the SDK requires for anything using the client.
    tasks = [
        asyncio.create_task(agent.run_messages()),
        asyncio.create_task(agent.run_transcriber()),
    ]
    try:
        done, _ = await asyncio.wait([*tasks, *background], return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()  # re-raise a failure
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def run(settings: Settings) -> None:
    speaker = Speaker(settings.output_device, settings.prebuffer_ms)
    agent = VoiceAgent(None, FishSpeech(settings), speaker, settings)
    # allowed_tools skip can_use_tool on purpose: they are the pre-approved tools.
    warnings.filterwarnings("ignore", category=CanUseToolShadowedWarning)
    mic: Microphone | None = None
    background: list[asyncio.Task] = []
    failures = 0
    hud: Hud | None = None
    try:
        if settings.web:
            hud = Hud(
                agent.feed,
                lambda: {
                    "state": agent.state,
                    "mic": round(agent.mic_level),
                    "voice": round(speaker.level),
                },
            )
            url = await hud.start()
            agent.feed.emit(
                "setup",
                key="setup",
                folder=settings.workdir,
                model=settings.claude_model,
                effort=settings.effort,
                voice=settings.voice_id,
                tts=settings.tts_model,
                stt=settings.stt_model,
                barge_in=settings.barge_in,
            )
            print(f"  {dim('hud      ')}{url}\n")
            webbrowser.open(url)
        while True:
            if agent.session_id:
                settings.resume = agent.session_id  # reconnect into the same conversation
            connected_at = time.monotonic()
            try:
                options = build_options(settings, agent.can_use_tool)
                async with ClaudeSDKClient(options=options) as client:
                    if mic is None:
                        mic = Microphone(settings.input_device)
                        background = [
                            asyncio.create_task(agent.run_speech()),
                            asyncio.create_task(listen(mic, agent, settings)),
                        ]
                        print(
                            f"  {paint('●', '32')} Ready. Just start talking."
                            + dim("  Ctrl+C to quit.")
                            + "\n"
                        )
                        if settings.greeting:
                            agent.say(GREETING)
                    else:
                        print(note("(reconnected)"))
                    await converse(client, agent, background)
            except Exception as e:
                if mic is None or any(t.done() for t in background):
                    raise  # never got going, or the mic or speech side broke
                print(error(f"(Claude Code stopped: {e})"))
            if time.monotonic() - connected_at > STABLE_CONNECTION:
                failures = 0
            failures += 1
            if failures > MAX_RECONNECTS:
                print(error("(can't reach Claude Code, giving up)"))
                return
            print(note("(reconnecting to Claude Code…)"))
            await asyncio.sleep(RECONNECT_DELAY * failures)
    finally:
        for task in background:
            task.cancel()
        await asyncio.gather(*background, return_exceptions=True)
        if hud is not None:
            await hud.close()
        if mic is not None:
            mic.close()
        speaker.close()
        print()
        if agent.session_id:
            print(
                dim(f"  Session {agent.session_id}  ·  continue with --resume {agent.session_id}")
            )
        print(f"  {paint('lila', '1;35')} {dim('· bye for now.')}")


def mic_test(settings: Settings) -> None:
    detector = SpeechDetector(settings.vad_aggressiveness)
    levels: list[float] = []
    print("Talk normally for a few seconds, then stay quiet. Listening for 10 seconds...")
    with sd.RawInputStream(
        samplerate=RATE,
        blocksize=FRAME_SAMPLES,
        channels=1,
        dtype="int16",
        device=settings.input_device,
    ) as stream:
        end = time.monotonic() + 10
        while time.monotonic() < end:
            data, _ = stream.read(FRAME_SAMPLES)
            frame = bytes(data)
            level = rms(frame)
            levels.append(level)
            voiced = detector.is_voiced(frame, settings.speech_rms)
            marker = paint("speech", "1;32") if voiced else "      "
            bar = paint(f"{'█' * min(40, int(level / 50)):<40}", "32" if voiced else "2")
            print(f"\r{level:6.0f} {marker} {bar}", end="", flush=True)
    quiet = sorted(levels)[len(levels) // 5]
    loudest = max(levels)
    print(f"\n\nLoudest level: {loudest:.0f}. Quiet room: about {quiet:.0f}.")
    print(
        f"--speech-rms (now {settings.speech_rms}) should sit well above the quiet level and "
        f"below your speaking level; around {max(quiet * 3, (quiet + loudest) / 4):.0f} is a "
        "good start. Raise it if noise triggers listening, lower it if you aren't heard."
    )


def banner(settings: Settings) -> None:
    model = settings.claude_model or "Claude Code's default"
    rows = [
        ("folder", settings.workdir),
        ("voice", f"{settings.voice_id or 'Fish default'} · {settings.tts_model}"),
        ("hearing", settings.stt_model + (f" · {settings.language}" if settings.language else "")),
        ("claude", model + (f" · {settings.effort} effort" if settings.effort else "")),
        ("sign-in", claude_sign_in()),
        ("memory", MEMORY_DIR),
    ]
    print(f"\n  {paint('lila', '1;35')} {dim('· your voice assistant, powered by Claude')}\n")
    for label, value in rows:
        print(f"  {dim(f'{label:<8}')} {value}")
    print()


def main(argv: list[str] | None = None) -> None:
    load_dotenv(find_dotenv(usecwd=True))
    sys.stdout.reconfigure(errors="replace")  # piped output on Windows can't encode "●" and co.
    settings = parse_args(argv)
    handler = logging.StreamHandler()
    handler.setFormatter(LogFormatter())
    logging.basicConfig(handlers=[handler])
    logging.getLogger("lila").setLevel(logging.DEBUG if settings.debug else logging.WARNING)

    if settings.list_devices:
        print(sd.query_devices())
        return
    if settings.mic_test:
        with contextlib.suppress(KeyboardInterrupt):
            mic_test(settings)
        return
    if not os.environ.get("FISH_API_KEY"):
        sys.exit("FISH_API_KEY is not set. Add it to .env (see .env.example) or your environment.")
    if settings.ignore_api_key:
        os.environ.pop("ANTHROPIC_API_KEY", None)

    banner(settings)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run(settings))


if __name__ == "__main__":
    main()
