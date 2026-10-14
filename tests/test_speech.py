import contextlib
import io
import wave

import httpx
import ormsgpack
import pytest
from fishaudio import AsyncFishAudio
from fishaudio.exceptions import APIError

from lila import speech as speech_module
from lila.config import Settings
from lila.speech import FishSpeech, clean_transcript
from lila.wav import PcmFormat

PCM = b"\x01\x00\x02\x00" * 100


def fish(handler) -> AsyncFishAudio:
    http = httpx.AsyncClient(
        base_url="https://api.fish.audio", transport=httpx.MockTransport(handler)
    )
    return AsyncFishAudio(api_key="test-key", httpx_client=http)


def asr_handler(requests, statuses=(200,), text="hello"):
    statuses = list(statuses)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        status = statuses.pop(0)
        if status != 200:
            body = {"status": status, "message": "nope", "code": "x", "request_id": "r"}
            return httpx.Response(status, json=body)
        return httpx.Response(200, json={"text": text, "duration": 1000, "segments": []})

    return handler


async def test_transcribe_request_carries_model_header_and_msgpack_body():
    requests = []
    s = FishSpeech(Settings(), fish(asr_handler(requests)))
    assert await s.transcribe(PCM) == "hello"
    (req,) = requests
    assert req.url.path == "/v1/asr"
    assert req.headers["model"] == "transcribe-1-pro"
    body = ormsgpack.unpackb(req.content)
    assert body["ignore_timestamps"] is True
    assert "language" not in body
    with wave.open(io.BytesIO(body["audio"])) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
        assert w.readframes(1000) == PCM


async def test_transcribe_sends_language_when_set():
    requests = []
    s = FishSpeech(Settings(language="nl", stt_model="transcribe-1"), fish(asr_handler(requests)))
    await s.transcribe(PCM)
    assert ormsgpack.unpackb(requests[0].content)["language"] == "nl"
    assert requests[0].headers["model"] == "transcribe-1"


async def test_transcript_markers_and_cues_are_stripped():
    text = "<|speaker:0|>Hello [laughter] there. <|speaker:1|> [music]  Hi!"
    s = FishSpeech(Settings(), fish(asr_handler([], text=text)))
    assert await s.transcribe(PCM) == "Hello there. Hi!"
    assert clean_transcript("[noise]") == ""


async def test_server_error_is_retried_once(monkeypatch):
    monkeypatch.setattr(speech_module, "RETRY_DELAY", 0)
    requests = []
    s = FishSpeech(Settings(), fish(asr_handler(requests, statuses=(503, 200))))
    assert await s.transcribe(PCM) == "hello"
    assert len(requests) == 2


async def test_client_error_is_not_retried(monkeypatch):
    monkeypatch.setattr(speech_module, "RETRY_DELAY", 0)
    requests = []
    s = FishSpeech(Settings(), fish(asr_handler(requests, statuses=(400, 200))))
    with pytest.raises(APIError):
        await s.transcribe(PCM)
    assert len(requests) == 1


class FakeSocket:
    def __init__(self, replies):
        self.sent = []
        self.replies = [ormsgpack.packb(r) for r in replies]

    async def send_bytes(self, data):
        self.sent.append(ormsgpack.unpackb(data))

    async def receive_bytes(self):
        return self.replies.pop(0)


def fake_ws(monkeypatch, replies):
    calls = []
    socket = FakeSocket(replies)

    @contextlib.asynccontextmanager
    async def aconnect_ws(url, **kwargs):
        calls.append((url, kwargs))
        yield socket

    monkeypatch.setattr("fishaudio.resources.tts.aconnect_ws", aconnect_ws)
    return calls, socket


def wav_bytes(pcm: bytes, rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


async def test_synthesize_over_websocket(monkeypatch):
    data = wav_bytes(PCM, 44100)
    replies = [
        {"event": "audio", "audio": data[:30]},
        {"event": "audio", "audio": data[30:]},
        {"event": "finish", "reason": "stop"},
    ]
    calls, socket = fake_ws(monkeypatch, replies)
    s = FishSpeech(Settings(voice_id="voice-123"), fish(lambda r: httpx.Response(500)))

    async def texts():
        yield "Hello there. "
        yield "How are you? "

    out = [piece async for piece in s.synthesize(texts())]

    (url, kwargs) = calls[0]
    assert url == "/v1/tts/live"
    assert kwargs["headers"]["model"] == "s2.1-pro"
    assert kwargs["max_message_size_bytes"] == 16 * 1024 * 1024
    assert kwargs["keepalive_ping_timeout_seconds"] == 60

    events = [m["event"] for m in socket.sent]
    assert events == ["start", "text", "text", "stop"]
    start = socket.sent[0]["request"]
    assert (start["format"], start["latency"], start["reference_id"]) == (
        "wav",
        "balanced",
        "voice-123",
    )
    assert start.get("prosody") is None  # speed 1.0 is not sent
    assert [m["text"] for m in socket.sent[1:3]] == ["Hello there. ", "How are you? "]

    assert {fmt for fmt, _ in out} == {PcmFormat(44100, 1)}
    assert b"".join(pcm for _, pcm in out) == PCM


async def test_empty_text_is_sent_as_a_flush(monkeypatch):
    replies = [{"event": "finish", "reason": "stop"}]
    _, socket = fake_ws(monkeypatch, replies)
    s = FishSpeech(Settings(), fish(lambda r: httpx.Response(500)))

    async def texts():
        yield "Before the tool runs. "
        yield ""
        yield "After. "

    assert [piece async for piece in s.synthesize(texts())] == []
    assert [m["event"] for m in socket.sent] == ["start", "text", "flush", "text", "stop"]
