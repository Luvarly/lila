"""Lila's own tools for Claude: what the user copied, and what's on their screen."""

from __future__ import annotations

import asyncio
import base64
import io
from typing import Any

from claude_agent_sdk import McpSdkServerConfig, create_sdk_mcp_server, tool

TOOL_NAMES = ["mcp__lila__clipboard", "mcp__lila__screenshot"]
MAX_EDGE = 1568  # Claude scales larger images down anyway
MAX_TEXT = 20_000  # ponytail: a huge copy is cut; Claude can Read a file if it needs all of it


def _image(img: Any) -> dict[str, str]:
    img = img.convert("RGB")
    img.thumbnail((MAX_EDGE, MAX_EDGE))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return {
        "type": "image",
        "data": base64.b64encode(buf.getvalue()).decode(),
        "mimeType": "image/png",
    }


def _text(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _clipboard_text() -> str:
    import tkinter

    root = tkinter.Tk()
    root.withdraw()
    try:
        return root.clipboard_get()
    except tkinter.TclError:  # empty, or not text
        return ""
    finally:
        root.destroy()


@tool(
    "clipboard",
    "Read what the user copied to their clipboard: text, an image, or copied files. Use it when "
    'they refer to something they copied, e.g. "what\'s this?" or "explain what I copied".',
    {},
)
async def clipboard(args: dict[str, Any]) -> dict[str, Any]:
    from PIL import ImageGrab

    content = ImageGrab.grabclipboard()
    if isinstance(content, list):
        return _text("The user copied these files:\n" + "\n".join(map(str, content)))
    if content is not None:
        return {"content": [await asyncio.to_thread(_image, content)]}
    text = _clipboard_text()  # Tk wants the main thread on some systems
    if not text:
        return _text("The clipboard is empty.")
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT] + f"\n[cut: {len(text) - MAX_TEXT} more characters]"
    return _text(text)


@tool(
    "screenshot",
    "Take a screenshot of the user's screen to see what they're looking at. Use it only when they "
    'ask about their screen, e.g. "what am I looking at?" or "what\'s this error?".',
    {},
)
async def screenshot(args: dict[str, Any]) -> dict[str, Any]:
    from PIL import ImageGrab

    # ponytail: primary screen only; grab the monitor under the mouse if that's not enough.
    shot = await asyncio.to_thread(ImageGrab.grab)
    return {"content": [await asyncio.to_thread(_image, shot)]}


def lila_tools() -> McpSdkServerConfig:
    # alwaysLoad keeps the tools in Claude's prompt instead of behind a ToolSearch round trip.
    # It's an internal Claude Code option; if it's ever ignored, the tools still work, just slower.
    return {**create_sdk_mcp_server("lila", tools=[clipboard, screenshot]), "alwaysLoad": True}
