"""Microphone, local speech detection, utterance segmentation and the speaker."""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from collections.abc import AsyncIterator
from typing import NamedTuple

import numpy as np
import sounddevice as sd
import webrtcvad

RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = RATE * FRAME_MS // 1000  # 480 samples, 960 bytes
START_WINDOW = 10  # frames; also the 300 ms pre-roll
START_VOICED = 6  # voiced frames in the window that start an utterance


def rms(frame: bytes) -> float:
    samples = np.frombuffer(frame, np.int16).astype(np.float64)
    return float(np.sqrt(np.mean(samples**2))) if samples.size else 0.0


class SpeechDetector:
    def __init__(self, aggressiveness: int = 2) -> None:
        self.vad = webrtcvad.Vad(aggressiveness)

    def is_voiced(self, frame: bytes, threshold: float) -> bool:
        return rms(frame) >= threshold and self.vad.is_speech(frame, RATE)


class Event(NamedTuple):
    kind: str  # "speech" | "pause" | "utterance" | "dropped"
    audio: bytes = b""
    early: bool = False  # utterance: nothing was said since the last pause, so its audio holds


class UtteranceSegmenter:
    """Pure logic: turns (frame, voiced) pairs into speech / pause / utterance / dropped events.

    "pause" comes after `early_ms` of silence in a confirmed utterance, with the audio so far,
    so transcription can start before the utterance is known to be over.
    """

    def __init__(
        self,
        end_silence_ms: int = 700,
        max_ms: int = 30_000,
        confirm_ms: int = 400,
        early_ms: int = 400,
    ) -> None:
        self.end_silence_ms = end_silence_ms
        self.max_ms = max_ms
        self.confirm_ms = confirm_ms
        self.early_ms = early_ms
        self._recent: deque[tuple[bytes, bool]] = deque(maxlen=START_WINDOW)
        self._frames: list[bytes] | None = None  # set while inside an utterance
        self._voiced_ms = 0
        self._silence_ms = 0
        self._confirmed = False
        self._paused = False  # a pause event went out and nothing was said since

    def process(self, frame: bytes, voiced: bool) -> list[Event]:
        if self._frames is None:
            self._recent.append((frame, voiced))
            voiced_frames = sum(v for _, v in self._recent)
            if voiced_frames < START_VOICED:
                return []
            self._frames = [f for f, _ in self._recent]
            self._recent.clear()
            self._voiced_ms = voiced_frames * FRAME_MS
            self._silence_ms = 0
            self._confirmed = False
            self._paused = False
            return []
        self._frames.append(frame)
        if voiced:
            self._voiced_ms += FRAME_MS
            self._silence_ms = 0
            self._paused = False
        else:
            self._silence_ms += FRAME_MS
        events = []
        if not self._confirmed and self._voiced_ms >= self.confirm_ms:
            self._confirmed = True
            events.append(Event("speech"))
        if self._silence_ms >= self.end_silence_ms or len(self._frames) * FRAME_MS >= self.max_ms:
            if self._confirmed:
                events.append(Event("utterance", b"".join(self._frames), self._paused))
            else:
                events.append(Event("dropped"))
            self._frames = None
        elif self._confirmed and not self._paused and self._silence_ms >= self.early_ms:
            self._paused = True
            events.append(Event("pause", b"".join(self._frames)))
        return events


class Microphone:
    """16 kHz mono int16 in 30 ms frames. Create it inside the running event loop."""

    def __init__(self, device: int | str | None = None) -> None:
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1000)
        loop = asyncio.get_running_loop()

        def callback(indata, frames, time_info, status) -> None:
            try:
                loop.call_soon_threadsafe(self._put, bytes(indata))
            except RuntimeError:  # loop already closed during shutdown
                pass

        self._stream = sd.RawInputStream(
            samplerate=RATE,
            blocksize=FRAME_SAMPLES,
            channels=1,
            dtype="int16",
            device=device,
            callback=callback,
        )
        self._stream.start()

    def _put(self, frame: bytes) -> None:
        if not self._queue.full():  # drop frames rather than block the audio thread
            self._queue.put_nowait(frame)

    async def frames(self) -> AsyncIterator[bytes]:
        while True:
            yield await self._queue.get()

    def close(self) -> None:
        self._stream.close()


class Speaker:
    """Plays int16 PCM from a buffer the audio callback drains, padding with silence."""

    def __init__(self, device: int | str | None = None, prebuffer_ms: int = 150) -> None:
        self._device = device
        self._prebuffer_ms = prebuffer_ms
        self._lock = threading.Lock()
        self._buf = bytearray()
        self._stream: sd.RawOutputStream | None = None
        self._format: tuple[int, int] | None = None
        self._prebuffer_bytes = 0
        self._primed = False  # playing; false again once the buffer runs empty
        self._draining = False  # the job ended, so play what's left without pre-buffering
        self._paused = False  # hold the buffer silently while the user may be interrupting
        self._last_audio = 0.0

    @property
    def is_playing(self) -> bool:
        with self._lock:
            if self._paused:
                return False
            return bool(self._buf) or time.monotonic() - self._last_audio < 0.3

    def play(self, rate: int, channels: int, pcm: bytes) -> None:
        if (rate, channels) != self._format:
            # ponytail: audio still buffered in the old format is dropped; Fish keeps one format.
            self.close()
            self._format = (rate, channels)
            self._prebuffer_bytes = rate * channels * 2 * self._prebuffer_ms // 1000
            self._stream = sd.RawOutputStream(
                samplerate=rate,
                channels=channels,
                dtype="int16",
                device=self._device,
                callback=self._callback,
            )
            self._stream.start()
        with self._lock:
            self._buf += pcm

    def drain(self) -> None:
        """The current job has no more audio: play the rest even if it's under the pre-buffer."""
        with self._lock:
            self._draining = bool(self._buf)

    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            self._paused = False

    def stop(self) -> None:
        with self._lock:
            self._buf.clear()
            self._primed = self._draining = False

    def close(self) -> None:
        self.stop()
        if self._stream is not None:
            self._stream.close()
            self._stream = None
            self._format = None

    def _callback(self, outdata, frames, time_info, status) -> None:
        n = len(outdata)
        with self._lock:
            if not self._primed and (len(self._buf) >= self._prebuffer_bytes or self._draining):
                self._primed = True
            chunk = b""
            if self._primed and not self._paused:
                chunk = bytes(self._buf[:n])
                del self._buf[:n]
                if chunk:
                    self._last_audio = time.monotonic()
                if not self._buf:
                    self._primed = self._draining = False
        outdata[: len(chunk)] = chunk
        outdata[len(chunk) :] = b"\x00" * (n - len(chunk))
