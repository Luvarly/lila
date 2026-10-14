"""Wiring, startup output, mic test and device listing."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
import time
import warnings
from collections.abc import Mapping

import sounddevice as sd
from claude_agent_sdk import CanUseToolShadowedWarning, ClaudeSDKClient
from dotenv import find_dotenv, load_dotenv

from .agent import GREETING, INDENT, VoiceAgent, build_options
from .audio import (
    FRAME_SAMPLES,
    RATE,
    Microphone,
    Speaker,
    SpeechDetector,
    UtteranceSegmenter,
    rms,
)
from .config import Settings, parse_args
from .speech import FishSpeech

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
        playing = agent.speaker.is_playing
        if playing and not settings.barge_in and not agent.approval_pending:
            continue  # half-duplex: never hear our own voice
        threshold = settings.barge_in_rms if playing else settings.speech_rms
        for event in segmenter.process(frame, detector.is_voiced(frame, threshold)):
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
    try:
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
                        print("Ready. Just start talking. Ctrl+C to quit.")
                        if settings.greeting:
                            agent.say(GREETING)
                    else:
                        print(f"{INDENT}(reconnected)")
                    await converse(client, agent, background)
            except Exception as e:
                if mic is None or any(t.done() for t in background):
                    raise  # never got going, or the mic or speech side broke
                print(f"{INDENT}(Claude Code stopped: {e})")
            if time.monotonic() - connected_at > STABLE_CONNECTION:
                failures = 0
            failures += 1
            if failures > MAX_RECONNECTS:
                print(f"{INDENT}(can't reach Claude Code, giving up)")
                return
            print(f"{INDENT}(reconnecting to Claude Code…)")
            await asyncio.sleep(RECONNECT_DELAY * failures)
    finally:
        for task in background:
            task.cancel()
        await asyncio.gather(*background, return_exceptions=True)
        if mic is not None:
            mic.close()
        speaker.close()
        if agent.session_id:
            print()
            print(f"Session {agent.session_id} (continue it with --resume {agent.session_id})")
        print("Bye.")


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
            marker = "speech" if detector.is_voiced(frame, settings.speech_rms) else "      "
            bar = "#" * min(40, int(level / 50))
            print(f"\r{level:6.0f} {marker} {bar:<40}", end="", flush=True)
    quiet = sorted(levels)[len(levels) // 5]
    loudest = max(levels)
    print(f"\n\nLoudest level: {loudest:.0f}. Quiet room: about {quiet:.0f}.")
    print(
        f"--speech-rms (now {settings.speech_rms}) should sit well above the quiet level and "
        f"below your speaking level; around {max(quiet * 3, (quiet + loudest) / 4):.0f} is a "
        "good start. Raise it if noise triggers listening, lower it if you aren't heard."
    )


def main(argv: list[str] | None = None) -> None:
    load_dotenv(find_dotenv(usecwd=True))
    settings = parse_args(argv)
    logging.basicConfig(format="%(levelname)s %(name)s: %(message)s")
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

    print(f"Working folder: {settings.workdir}")
    print(f"Voice: {settings.voice_id or 'default'} ({settings.tts_model})")
    print(f"Hearing: {settings.stt_model}")
    print(f"Claude sign-in: {claude_sign_in()}")
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run(settings))


if __name__ == "__main__":
    main()
