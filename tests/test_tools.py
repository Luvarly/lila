import base64
import io
import json

from PIL import Image, ImageGrab

from lila import tools
from lila.agent import MEMORY_DIR, build_options
from lila.config import Settings


def decoded(result) -> Image.Image:
    (item,) = result["content"]
    assert item["type"] == "image" and item["mimeType"] == "image/png"
    return Image.open(io.BytesIO(base64.b64decode(item["data"])))


async def test_screenshot_is_scaled_down(monkeypatch):
    monkeypatch.setattr(ImageGrab, "grab", lambda: Image.new("RGB", (3136, 1764)))
    assert decoded(await tools.screenshot.handler({})).size == (1568, 882)


async def test_clipboard_image(monkeypatch):
    monkeypatch.setattr(ImageGrab, "grabclipboard", lambda: Image.new("RGBA", (40, 30)))
    assert decoded(await tools.clipboard.handler({})).size == (40, 30)


async def test_clipboard_files(monkeypatch):
    monkeypatch.setattr(ImageGrab, "grabclipboard", lambda: ["C:\\a.txt", "C:\\b.png"])
    result = await tools.clipboard.handler({})
    assert result["content"][0]["text"] == "The user copied these files:\nC:\\a.txt\nC:\\b.png"


async def test_clipboard_text_empty_and_long(monkeypatch):
    monkeypatch.setattr(ImageGrab, "grabclipboard", lambda: None)
    monkeypatch.setattr(tools, "_clipboard_text", lambda: "TypeError: x is undefined")
    assert (await tools.clipboard.handler({}))["content"][0]["text"] == "TypeError: x is undefined"
    monkeypatch.setattr(tools, "_clipboard_text", lambda: "")
    assert (await tools.clipboard.handler({}))["content"][0]["text"] == "The clipboard is empty."
    monkeypatch.setattr(tools, "_clipboard_text", lambda: "x" * (tools.MAX_TEXT + 5))
    text = (await tools.clipboard.handler({}))["content"][0]["text"]
    assert text.endswith("[cut: 5 more characters]")


def test_options_add_personality_memory_and_tools():
    options = build_options(Settings(), can_use_tool=None)
    assert "you are Lila" in options.system_prompt["append"]
    assert json.loads(options.settings) == {"autoMemoryDirectory": MEMORY_DIR}
    assert options.mcp_servers["lila"]["alwaysLoad"] is True
    assert {*tools.TOOL_NAMES, f"Write({MEMORY_DIR}/**)", "Read"} <= set(options.allowed_tools)


def test_options_use_auto_mode_unless_turned_off():
    assert build_options(Settings(), None).permission_mode == "auto"
    assert build_options(Settings(auto_mode=False), None).permission_mode == "default"
    off = Settings(auto_mode=False, voice_approvals=False)
    assert build_options(off, None).permission_mode == "dontAsk"
