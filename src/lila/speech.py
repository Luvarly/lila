"""Fish Audio speech-to-text (batch, per utterance) and streaming text-to-speech."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterable, AsyncIterator

from fishaudio import AsyncFishAudio, FlushEvent, TTSConfig
from fishaudio.core import RequestOptions, WebSocketOptions
from fishaudio.exceptions import RateLimitError, ServerError

from .config import Settings
from .wav import PcmFormat, WavDecoder, encode_wav

RETRY_DELAY = 0.5
# Audio messages can exceed httpx-ws's 64 KiB default.
WS_OPTIONS = WebSocketOptions(
    max_message_size_bytes=16 * 1024 * 1024, keepalive_ping_timeout_seconds=60
)

_SPEAKER = re.compile(r"<\|speaker:\d+\|>")
_CUE = re.compile(r"\[[^\[\]]*\]")


def clean_transcript(text: str) -> str:
    """Drop transcribe-1-pro's speaker markers and sound cues like [laughter]."""
    return " ".join(_CUE.sub(" ", _SPEAKER.sub(" ", text)).split())


class FishSpeech:
    def __init__(self, settings: Settings, client: AsyncFishAudio | None = None) -> None:
        self.settings = settings
        self.client = client or AsyncFishAudio()  # reads FISH_API_KEY

    async def transcribe(self, pcm: bytes) -> str:
        # The model goes in a header; a missing or misspelled one is billed as transcribe-1.
        options = RequestOptions(additional_headers={"model": self.settings.stt_model})
        language = {"language": self.settings.language} if self.settings.language else {}
        try:
            result = await self._transcribe(pcm, options, language)
        except (RateLimitError, ServerError):
            await asyncio.sleep(RETRY_DELAY)
            result = await self._transcribe(pcm, options, language)
        return clean_transcript(result.text)

    async def _transcribe(self, pcm: bytes, options: RequestOptions, language: dict):
        return await self.client.asr.transcribe(
            audio=encode_wav(pcm), include_timestamps=False, request_options=options, **language
        )

    async def synthesize(self, texts: AsyncIterable[str]) -> AsyncIterator[tuple[PcmFormat, bytes]]:
        """One Fish WebSocket session for one stream of text; yields int16 PCM.

        An empty text is sent as a flush, so Fish speaks what it has without waiting for more.
        """

        async def events() -> AsyncIterator[str | FlushEvent]:
            async for text in texts:
                yield text or FlushEvent()

        s = self.settings
        speed = {"speed": s.speed} if s.speed != 1.0 else {}
        decoder = WavDecoder()
        async for audio in self.client.tts.stream_websocket(
            events(),
            config=TTSConfig(format="wav", latency=s.latency, reference_id=s.voice_id),
            model=s.tts_model,
            ws_options=WS_OPTIONS,
            **speed,
        ):
            fmt, pcm = decoder.feed(audio)
            if pcm:
                yield fmt, pcm
