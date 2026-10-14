"""WAV encoding for speech-to-text and a streaming WAV decoder for playback."""

from __future__ import annotations

import io
import struct
import wave
from typing import NamedTuple

import numpy as np


class PcmFormat(NamedTuple):
    """Format of decoded audio, which is always 16-bit signed little-endian."""

    rate: int
    channels: int


def encode_wav(pcm: bytes, rate: int = 16000) -> bytes:
    """Wrap 16-bit mono PCM in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


class WavDecoder:
    """Turns a stream of WAV messages into int16 PCM.

    A header may start any message and may be split across messages. Messages without a
    header are PCM in the last known format.
    """

    def __init__(self) -> None:
        self.format = PcmFormat(44100, 1)
        self._bits = 16
        self._float = False
        self._pending = b""  # a header that hasn't fully arrived yet
        self._carry = b""  # trailing bytes of an incomplete sample frame

    def feed(self, data: bytes) -> tuple[PcmFormat, bytes]:
        if self._pending or data[:4] == b"RIFF":
            data = self._pending + data
            offset = self._parse_header(data)
            if offset is None:
                self._pending = data
                return self.format, b""
            self._pending = b""
            self._carry = b""
            data = data[offset:]
        data = self._carry + data
        align = self._bits // 8 * self.format.channels
        cut = len(data) - len(data) % align
        data, self._carry = data[:cut], data[cut:]
        return self.format, self._to_int16(data)

    def _parse_header(self, data: bytes) -> int | None:
        """Return the offset of the audio payload, or None if the header is incomplete."""
        if len(data) < 12:
            return None
        if data[8:12] != b"WAVE":
            return 0
        pos = 12
        while len(data) >= pos + 8:
            chunk_id = data[pos : pos + 4]
            size = int.from_bytes(data[pos + 4 : pos + 8], "little")
            if chunk_id == b"data":
                return pos + 8  # streams use placeholder sizes, so ignore it
            if len(data) < pos + 8 + size:
                return None
            if chunk_id == b"fmt ":
                self._parse_fmt(data[pos + 8 : pos + 8 + size])
            pos += 8 + size + (size & 1)
        return None

    def _parse_fmt(self, fmt: bytes) -> None:
        code, channels, rate = struct.unpack_from("<HHI", fmt, 0)
        (bits,) = struct.unpack_from("<H", fmt, 14)
        if code == 0xFFFE and len(fmt) >= 26:  # WAVE_FORMAT_EXTENSIBLE: real code is in the GUID
            (code,) = struct.unpack_from("<H", fmt, 24)
        self.format = PcmFormat(rate, channels)
        self._bits = bits
        self._float = code == 3

    def _to_int16(self, data: bytes) -> bytes:
        if not data or self._bits == 16:
            return data
        if self._bits == 32 and self._float:
            samples = np.clip(np.frombuffer(data, "<f4"), -1.0, 1.0)
            return (samples * 32767).astype("<i2").tobytes()
        if self._bits == 32:
            return (np.frombuffer(data, "<i4") >> 16).astype("<i2").tobytes()
        if self._bits == 24:
            return np.frombuffer(data, np.uint8).reshape(-1, 3)[:, 1:].copy().view("<i2").tobytes()
        if self._bits == 8:
            return ((np.frombuffer(data, np.uint8).astype("<i2") - 128) << 8).tobytes()
        raise ValueError(f"unsupported WAV sample size: {self._bits} bits")
