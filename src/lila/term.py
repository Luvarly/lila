"""Terminal styling: a few ANSI colours, off when the output is piped or NO_COLOR is set."""

from __future__ import annotations

import logging
import os
import sys

INDENT = " " * 9  # status lines line up with the text after a "  lila › " label


def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return False
    if sys.platform == "win32":  # older consoles need ANSI support switched on
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    return True


COLOR = _color_enabled()


def paint(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if COLOR else text


def dim(text: str) -> str:
    return paint(text, "2")


def note(text: str) -> str:
    """A status line such as "(interrupted)", indented under the conversation."""
    return INDENT + paint(text, "2;3")


def error(text: str) -> str:
    return INDENT + paint(text, "31")


YOU = "   " + paint("you", "1;36") + dim(" › ")
LILA = "  " + paint("lila", "1;35") + dim(" › ")


def tool_line(name: str, summary: str) -> str:
    label = name.removeprefix("mcp__lila__")
    return INDENT + dim("· ") + paint(label, "34") + (" " + dim(summary) if summary else "")


def ask_line(name: str, summary: str) -> str:
    label = name.removeprefix("mcp__lila__")
    return (
        INDENT
        + paint("?", "1;33")
        + f" wants to use {label}"
        + (": " + dim(summary) if summary else "")
    )


class LogFormatter(logging.Formatter):
    COLORS = {logging.DEBUG: "2", logging.INFO: "2", logging.WARNING: "33"}

    def format(self, record: logging.LogRecord) -> str:
        text = f"{record.levelname.lower()}: {record.getMessage()}"
        return INDENT + paint(text, self.COLORS.get(record.levelno, "31"))
