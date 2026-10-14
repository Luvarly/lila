"""Settings from command-line flags, environment variables and .env (flags win over env)."""

from __future__ import annotations

import argparse
import os
from collections.abc import Mapping
from dataclasses import dataclass, field

DEFAULT_TOOLS = "Read,Glob,Grep,WebSearch,WebFetch"
EFFORTS = ["low", "medium", "high", "xhigh", "max"]


@dataclass
class Settings:
    voice_id: str | None = None
    tts_model: str = "s2.1-pro"
    stt_model: str = "transcribe-1-pro"
    latency: str = "balanced"
    speed: float = 1.0
    expressive: bool = False
    language: str | None = None
    workdir: str = "."
    claude_model: str | None = None
    effort: str | None = None
    allowed_tools: list[str] = field(default_factory=lambda: DEFAULT_TOOLS.split(","))
    voice_approvals: bool = True
    barge_in: bool = True
    speech_rms: int = 300
    barge_in_rms: int = 1500
    end_silence_ms: int = 700
    input_device: int | str | None = None
    output_device: int | str | None = None
    ignore_api_key: bool = False
    resume: str | None = None
    greeting: bool = True
    debug: bool = False
    list_devices: bool = False
    mic_test: bool = False
    # No flags for these.
    approval_timeout: float = 45.0
    prebuffer_ms: int = 150
    vad_aggressiveness: int = 2


def _on(value: str | None, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _device(value: str | None) -> int | str | None:
    if not value:
        return None
    return int(value) if value.isdigit() else value


def parse_args(argv: list[str] | None = None, env: Mapping[str, str] = os.environ) -> Settings:
    e = env.get
    p = argparse.ArgumentParser(prog="lila", description="Talk to Claude Code with your voice.")
    p.add_argument("--voice-id", default=e("FISH_VOICE_ID") or None)
    p.add_argument("--tts-model", default=e("FISH_TTS_MODEL") or "s2.1-pro")
    p.add_argument("--stt-model", default=e("FISH_STT_MODEL") or "transcribe-1-pro")
    p.add_argument(
        "--latency", choices=["normal", "balanced"], default=e("FISH_LATENCY") or "balanced"
    )
    p.add_argument("--speed", type=float, default=float(e("FISH_SPEED") or 1.0))
    p.add_argument("--expressive", action="store_true", default=_on(e("LILA_EXPRESSIVE"), False))
    p.add_argument("--language", default=e("LILA_LANGUAGE") or None)
    p.add_argument("--workdir", default=e("LILA_WORKDIR") or os.getcwd())
    p.add_argument("--model", dest="claude_model", default=e("CLAUDE_MODEL") or None)
    p.add_argument("--effort", choices=EFFORTS, default=e("CLAUDE_EFFORT") or None)
    p.add_argument("--allowed-tools", default=e("LILA_ALLOWED_TOOLS") or DEFAULT_TOOLS)
    p.add_argument(
        "--no-voice-approvals",
        dest="voice_approvals",
        action="store_false",
        default=_on(e("LILA_VOICE_APPROVALS"), True),
    )
    p.add_argument(
        "--no-barge-in",
        dest="barge_in",
        action="store_false",
        default=_on(e("LILA_BARGE_IN"), True),
    )
    p.add_argument("--speech-rms", type=int, default=int(e("LILA_SPEECH_RMS") or 300))
    p.add_argument("--barge-in-rms", type=int, default=int(e("LILA_BARGE_IN_RMS") or 1500))
    p.add_argument("--end-silence-ms", type=int, default=int(e("LILA_END_SILENCE_MS") or 700))
    p.add_argument("--input-device", type=_device, default=_device(e("LILA_INPUT_DEVICE")))
    p.add_argument("--output-device", type=_device, default=_device(e("LILA_OUTPUT_DEVICE")))
    p.add_argument(
        "--ignore-api-key", action="store_true", default=_on(e("LILA_IGNORE_API_KEY"), False)
    )
    p.add_argument("--resume", metavar="ID")
    p.add_argument("--no-greeting", dest="greeting", action="store_false")
    p.add_argument("--debug", action="store_true")
    p.add_argument("--list-devices", action="store_true")
    p.add_argument("--mic-test", action="store_true")
    args = p.parse_args(argv)
    if args.effort not in (None, *EFFORTS):  # argparse doesn't check values from the env
        p.error(f"CLAUDE_EFFORT must be one of: {', '.join(EFFORTS)}")
    args.allowed_tools = [t.strip() for t in args.allowed_tools.split(",") if t.strip()]
    return Settings(**vars(args))
