"""공시 HTML을 왼쪽 영역에 넣기 전에 실행 요소를 뺀다."""

from __future__ import annotations

import html
from html.parser import HTMLParser

_DROP = frozenset({"script", "iframe"})
_SCRIPT_URL_ATTRS = frozenset({"action", "formaction", "href", "src"})


class _Clean(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, close=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, close=True)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in _DROP:
            if self._skip:
                self._skip -= 1
            return
        if self._skip:
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if not self._skip:
            self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self._skip:
            self.parts.append(f"&#{name};")

    def _start(self, tag: str, attrs: list[tuple[str, str | None]], *, close: bool) -> None:
        name = tag.lower()
        if name in _DROP:
            if not close:
                self._skip += 1
            return
        if self._skip:
            return
        chunks = [f"<{tag}"]
        for key, value in attrs:
            if not _keep_attr(key, value):
                continue
            if value is None:
                chunks.append(f" {key}")
            else:
                chunks.append(f' {key}="{html.escape(value, quote=True)}"')
        chunks.append(" />" if close else ">")
        self.parts.append("".join(chunks))


def _keep_attr(key: str, value: str | None) -> bool:
    name = key.lower()
    if name.startswith("on"):
        return False
    script_url = name in _SCRIPT_URL_ATTRS or name.endswith(":href")
    return not (script_url and value is not None and _javascript_url(value))


def _javascript_url(value: str) -> bool:
    text = "".join(ch for ch in html.unescape(value) if ch.isprintable())
    return text.strip().casefold().startswith("javascript:")


def prepare_disclosure_html(page: str) -> str:
    parser = _Clean()
    parser.feed(page)
    parser.close()
    return "".join(parser.parts)
