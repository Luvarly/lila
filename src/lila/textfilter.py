"""Streaming markdown-to-speech filter: turns Claude's text into chunks worth saying out loud."""

from __future__ import annotations

import re

CODE_NOTICE = "I've put the code on screen. "
MAX_HOLD = 160

_SENTENCE_END = re.compile(r"[.!?:;](?=\s)")
_FENCE = re.compile(r"^\s*(```|~~~)")
_RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_HEADING = re.compile(r"^\s*#{1,6}\s+")
_QUOTE = re.compile(r"^\s*(>\s?)+")
_LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")

_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_URL = re.compile(r"https?://\S+?(?=[.,;:!?)\]]*(?:\s|$))")
_CODE = re.compile(r"`+([^`]*)`+")
_EMPHASIS = re.compile(r"\*\*|__|~~|\*|`")
_SNAKE = re.compile(r"(?<=\w)_(?=\w)")
_CUE = re.compile(r"\[[^\[\]]{1,30}\](?!\()")
_EMOJI = re.compile(r"[\U0001F000-\U0001FAFF\u2300-\u23FF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]")


class SpeechFilter:
    """feed() text as it streams in; every returned chunk is clean and ends with one space."""

    def __init__(self, expressive: bool = False) -> None:
        self.expressive = expressive
        self._buf = ""
        self._line_start = True  # does _buf begin at the start of a line?
        self._code = False
        self._noticed = False

    def feed(self, text: str) -> list[str]:
        self._buf += text
        out: list[str] = []
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            out += self._emit(line, whole=True)
        # Hold partial lines in code and ones that may become a fence or a table row.
        if self._code or (self._line_start and self._buf.lstrip().startswith(("`", "~", "|"))):
            return out
        cut = max((m.end() for m in _SENTENCE_END.finditer(self._buf)), default=0)
        if not cut and len(self._buf) > MAX_HOLD:
            cut = self._buf.rfind(" ") + 1
        if cut:
            part, self._buf = self._buf[:cut], self._buf[cut:]
            out += self._emit(part, whole=False)
        return out

    def flush(self) -> list[str]:
        rest, self._buf = self._buf, ""
        return self._emit(rest, whole=True) if rest else []

    def _emit(self, text: str, whole: bool) -> list[str]:
        at_start, self._line_start = self._line_start, whole
        if at_start and _FENCE.match(text):
            self._code = not self._code
            if self._code and not self._noticed:
                self._noticed = True
                return [CODE_NOTICE]
            return []
        if self._code:
            return []
        if at_start:
            text = _line_rules(text)
        cleaned = self._inline(text)
        return [cleaned + " "] if cleaned else []

    def _inline(self, text: str) -> str:
        text = _LINK.sub(r"\1", text)
        text = _URL.sub("a link", text)
        text = _CODE.sub(r"\1", text)
        text = _EMPHASIS.sub("", text)
        text = _SNAKE.sub(" ", text)
        if not self.expressive:
            text = _CUE.sub("", text)
        text = _EMOJI.sub("", text)
        return " ".join(text.split())


def _line_rules(line: str) -> str:
    stripped = line.strip()
    if _RULE.match(line):
        return ""
    if "|" in stripped and "-" in stripped and set(stripped) <= set("|-: "):
        return ""  # table separator row
    if len(stripped) > 1 and stripped.startswith("|") and stripped.endswith("|"):
        return ", ".join(c.strip() for c in stripped[1:-1].split("|") if c.strip())
    line = _HEADING.sub("", line)
    line = _QUOTE.sub("", line)
    return _LIST.sub("", line)
