"""Fakes for Claude, Fish and the audio devices. Tests never touch the real ones."""

import asyncio

from lila.wav import PcmFormat


class FakeClient:
    def __init__(self):
        self.queries: list[str] = []
        self.interrupts = 0
        self.inbox: asyncio.Queue = asyncio.Queue()

    async def query(self, text):
        self.queries.append(text)

    async def interrupt(self):
        self.interrupts += 1

    async def receive_messages(self):
        while True:
            yield await self.inbox.get()

    def push(self, *messages):
        for m in messages:
            self.inbox.put_nowait(m)


class FakeSpeech:
    """Records what is spoken, one entry per flushed piece, and how often a socket opens."""

    def __init__(self):
        self.spoken: list[str] = []
        self.calls = 0
        self.transcripts: list[str] = []
        self.heard: list[bytes] = []

    async def synthesize(self, texts):
        self.calls += 1
        part = []
        async for t in texts:
            if t:
                part.append(t)
            elif part:  # flush
                self.spoken.append("".join(part).strip())
                part = []
        if part:
            self.spoken.append("".join(part).strip())
        yield PcmFormat(16000, 1), b"\x00\x00"

    async def transcribe(self, pcm):
        self.heard.append(pcm)
        return self.transcripts.pop(0)


class FakeSpeaker:
    is_playing = False

    def __init__(self, *args):
        self.played = []
        self.stops = 0
        self.paused = False

    def play(self, rate, channels, pcm):
        self.played.append((rate, channels, pcm))

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        self.stops += 1

    def drain(self):
        pass

    def close(self):
        pass


class FakeMic:
    def __init__(self, *args):
        pass

    async def frames(self):
        await asyncio.Event().wait()
        yield b""

    def close(self):
        pass
