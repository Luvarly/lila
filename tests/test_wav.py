import io
import struct
import wave

import numpy as np

from lila.wav import PcmFormat, WavDecoder, encode_wav


def wav_bytes(pcm: bytes, rate: int = 24000, channels: int = 1) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


PCM = np.arange(-50, 50, dtype="<i2").tobytes()


def decode(*messages: bytes) -> tuple[PcmFormat, bytes]:
    d = WavDecoder()
    out = b""
    fmt = d.format
    for m in messages:
        fmt, pcm = d.feed(m)
        out += pcm
    return fmt, out


def test_whole_file():
    assert decode(wav_bytes(PCM, 24000, 2)) == (PcmFormat(24000, 2), PCM)


def test_header_split_over_three_messages():
    data = wav_bytes(PCM)
    assert decode(data[:6], data[6:30], data[30:]) == (PcmFormat(24000, 1), PCM)


def test_odd_byte_split_keeps_samples_aligned():
    data = wav_bytes(PCM)
    d = WavDecoder()
    _, first = d.feed(data[:51])  # 44-byte header + 7 payload bytes
    assert len(first) == 6
    _, rest = d.feed(data[51:])
    assert first + rest == PCM


def test_second_header_in_later_message():
    first = wav_bytes(PCM, 24000)
    second = wav_bytes(PCM[:10], 44100)
    assert decode(first, second) == (PcmFormat(44100, 1), PCM + PCM[:10])


def test_raw_pcm_without_header_uses_default_format():
    assert decode(PCM) == (PcmFormat(44100, 1), PCM)


def test_32_bit_float_is_converted():
    floats = np.array([0.0, 0.5, -1.0, 2.0], dtype="<f4")
    fmt_chunk = struct.pack("<HHIIHH", 3, 1, 22050, 22050 * 4, 4, 32)
    header = (
        b"RIFF"
        + struct.pack("<I", 0xFFFFFFFF)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<I", len(fmt_chunk))
        + fmt_chunk
        + b"data"
        + struct.pack("<I", 0xFFFFFFFF)
    )
    fmt, pcm = decode(header + floats.tobytes())
    assert fmt == PcmFormat(22050, 1)
    assert np.frombuffer(pcm, "<i2").tolist() == [0, 16383, -32767, 32767]


def test_encode_wav_round_trip():
    with wave.open(io.BytesIO(encode_wav(PCM))) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
        assert w.readframes(1000) == PCM
