"""The HUD for --web: Lila's live state as Server-Sent Events on localhost, and the page."""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    TERMINAL_TASK_STATUSES,
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
    TaskUpdatedMessage,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from .term import screen_summary

HERE = Path(__file__).parent
FILES = {
    "/": ("hud.html", "text/html; charset=utf-8"),
    "/saira.woff2": ("saira.woff2", "font/woff2"),
}
PORT = 8484
TICK = 1 / 30  # state and audio levels, 30 times a second
KEEPALIVE = 15.0
HISTORY = 500  # recent events a page gets when it (re)connects
KEEP_DONE = 8  # finished background tasks it still gets
# Session totals, from the per-model usage in each ResultMessage.
COUNTERS = {
    "input": "inputTokens",
    "output": "outputTokens",
    "cache_read": "cacheReadInputTokens",
    "cache_write": "cacheCreationInputTokens",
    "web": "webSearchRequests",
}
CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; font-src 'self'; "
    "connect-src 'self'; img-src data:; frame-ancestors 'none'"
)


def _now() -> int:
    return round(time.time() * 1000)


def _usage(usage: dict[str, Any] | None) -> dict[str, Any]:
    if not usage:
        return {}
    return {
        "tokens": usage.get("total_tokens"),
        "tool_uses": usage.get("tool_uses"),
        "ms": usage.get("duration_ms"),
    }


class Feed:
    """What the HUD shows. A page that connects gets `sticky` (latest per key), then `history`."""

    def __init__(self) -> None:
        self.started = _now()
        self.subscribers: set[asyncio.Queue[dict | None]] = set()
        self.sticky: dict[str, dict] = {}
        self.history: deque[dict] = deque(maxlen=HISTORY)
        self.stats: dict[str, float] = dict.fromkeys(["cost", "replies", "tools", *COUNTERS], 0)
        self._last: dict[str, float] = {}  # Claude Code's running totals at the last result
        self._tasks: dict[str, dict] = {}
        self._done: deque[str] = deque()
        self._seen_tools: set[str] = set()

    def emit(self, kind: str, key: str | None = None, **data: Any) -> None:
        event = {"type": kind, "t": _now(), **data}
        if key:
            self.sticky[key] = event
        else:
            self.history.append(event)
        self.send(event)

    def send(self, event: dict | None) -> None:
        for queue in self.subscribers:
            queue.put_nowait(event)

    def subscribe(self) -> asyncio.Queue[dict | None]:
        queue: asyncio.Queue[dict | None] = asyncio.Queue()
        for event in [{"type": "hello", "started": self.started}, *self.sticky.values()]:
            queue.put_nowait(event)
        for event in self.history:
            queue.put_nowait(event)
        self.subscribers.add(queue)
        return queue

    # ---- what Lila reports ------------------------------------------------------------------

    def message(self, message: Any) -> None:
        """A message from the Claude Agent SDK."""
        if isinstance(message, TaskStartedMessage):
            self._task(
                message.task_id,
                description=message.description,
                task_type=message.task_type,
                tool_use_id=message.tool_use_id,
                status="running",
            )
        elif isinstance(message, TaskProgressMessage):
            self._task(
                message.task_id,
                description=message.description,
                last_tool=message.last_tool_name,
                **_usage(message.usage),
            )
        elif isinstance(message, TaskNotificationMessage):
            self._task(
                message.task_id,
                status=message.status,
                summary=message.summary,
                **_usage(message.usage),
            )
        elif isinstance(message, TaskUpdatedMessage):
            self._task(message.task_id, status=message.status)
        elif isinstance(message, SystemMessage):
            if message.subtype == "init":
                data = message.data
                self.emit(
                    "claude",
                    key="claude",
                    model=data.get("model"),
                    cwd=data.get("cwd"),
                    version=data.get("claude_code_version"),
                    tools=len(data.get("tools") or []),
                )
        elif isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock) and block.id not in self._seen_tools:
                    self._seen_tools.add(block.id)
                    self.emit(
                        "tool",
                        id=block.id,
                        name=block.name,
                        summary=screen_summary(block.input),
                        parent=message.parent_tool_use_id,
                    )
                    self.stats["tools"] += 1
                    self._emit_stats()
        elif isinstance(message, UserMessage) and isinstance(message.content, list):
            for block in message.content:
                if isinstance(block, ToolResultBlock):
                    self.emit("tool_done", id=block.tool_use_id, error=bool(block.is_error))
        elif isinstance(message, ResultMessage):
            self._result(message)

    def context(self, usage: dict[str, Any]) -> None:
        """What `ClaudeSDKClient.get_context_usage()` returned."""
        self.emit(
            "context",
            key="context",
            percent=usage.get("percentage"),
            used=usage.get("totalTokens"),
            max=usage.get("maxTokens"),
            model=usage.get("model"),
            parts=[
                {"name": c.get("name"), "tokens": c.get("tokens")}
                for c in usage.get("categories") or []
                if c.get("tokens") and not c.get("isDeferred")
            ],
        )

    def latency(self, ms: float) -> None:
        """From the user's words being understood to the first sound of the reply."""
        self.stats["latency"] = round(ms)
        self._emit_stats()

    def _task(self, task_id: str, **fields: Any) -> None:
        task = self._tasks.setdefault(task_id, {"id": task_id, "started": _now()})
        task.update((k, v) for k, v in fields.items() if v is not None)
        self.emit("task", key=f"task:{task_id}", **task)
        if task.get("status") in TERMINAL_TASK_STATUSES and task_id not in self._done:
            self._done.append(task_id)
            if len(self._done) > KEEP_DONE:
                old = self._done.popleft()
                self._tasks.pop(old, None)
                self.sticky.pop(f"task:{old}", None)

    def _result(self, message: ResultMessage) -> None:
        models = (message.model_usage or {}).values()
        totals = {"cost": message.total_cost_usd or 0.0}
        for name, key in COUNTERS.items():
            totals[name] = sum(usage.get(key) or 0 for usage in models)
        for name, value in totals.items():
            # Running totals of one Claude Code process: a reconnect or /clear starts them over.
            last = self._last.get(name, 0)
            self.stats[name] += value - last if value >= last else value
        self._last = totals
        self.stats["replies"] += 1
        self.stats["ms"] = message.duration_ms
        self.stats["api_ms"] = message.duration_api_ms
        self.stats["result_at"] = _now()
        self._emit_stats()

    def _emit_stats(self) -> None:
        self.emit("stats", key="stats", **self.stats)


def _response(status: str, body: bytes = b"", kind: str = "text/plain; charset=utf-8") -> bytes:
    head = (
        f"HTTP/1.1 {status}\r\nContent-Type: {kind}\r\nContent-Length: {len(body)}\r\n"
        f"Cache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\n"
        f"Content-Security-Policy: {CSP}\r\nConnection: close\r\n\r\n"
    )
    return head.encode() + body


class Hud:
    """Serves the page and the event stream on 127.0.0.1, for this machine only."""

    def __init__(self, feed: Feed, sample: Callable[[], dict[str, Any]]) -> None:
        self.feed = feed
        self.sample = sample  # the live state for each tick
        self.port = 0
        self._server: asyncio.Server | None = None
        self._ticker: asyncio.Task | None = None

    async def start(self, port: int = PORT) -> str:
        try:
            self._server = await asyncio.start_server(self._handle, "127.0.0.1", port)
        except OSError:  # the port is taken: let the system pick one
            self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        self._ticker = asyncio.create_task(self._tick())
        return f"http://127.0.0.1:{self.port}/"

    async def close(self) -> None:
        if self._ticker is not None:
            self._ticker.cancel()
        self.feed.send(None)  # ends every open event stream
        if self._server is not None:
            self._server.close()

    async def _tick(self) -> None:
        while True:
            await asyncio.sleep(TICK)
            if self.feed.subscribers:
                self.feed.send({"type": "tick", **self.sample()})

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
            request, *lines = head.decode("latin-1").split("\r\n")
            method, target, _ = request.split(" ", 2)
            pairs = (h.partition(":") for h in lines)
            headers = {k.strip().lower(): v.strip() for k, _, v in pairs}
            path = target.split("?")[0]
            # By name too: a site that points its own domain at 127.0.0.1 is refused.
            if headers.get("host") not in (f"127.0.0.1:{self.port}", f"localhost:{self.port}"):
                writer.write(_response("403 Forbidden"))
            elif method != "GET":
                writer.write(_response("405 Method Not Allowed"))
            elif path in FILES:
                name, kind = FILES[path]
                writer.write(_response("200 OK", (HERE / name).read_bytes(), kind))
            elif path == "/events":
                await self._events(writer)
            else:
                writer.write(_response("404 Not Found"))
            await writer.drain()
        except (
            OSError,
            ValueError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
            asyncio.TimeoutError,
        ):
            pass  # the page went away, or it wasn't a request we serve
        finally:
            writer.close()

    async def _events(self, writer: asyncio.StreamWriter) -> None:
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-store\r\n"
            b"X-Content-Type-Options: nosniff\r\n\r\nretry: 2000\n\n"
        )
        queue = self.feed.subscribe()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), KEEPALIVE)
                except asyncio.TimeoutError:
                    writer.write(b": keep-alive\n\n")
                else:
                    if event is None:
                        return
                    data = json.dumps(event, separators=(",", ":"), default=str)
                    writer.write(f"data: {data}\n\n".encode())
                if queue.empty():
                    await asyncio.wait_for(writer.drain(), 10)  # a page that stopped reading
        finally:
            self.feed.subscribers.discard(queue)
