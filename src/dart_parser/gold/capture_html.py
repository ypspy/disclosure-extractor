"""공시 HTML을 허용 목록으로 정리한다."""

from __future__ import annotations

import html
import json
from html.parser import HTMLParser
from pathlib import Path

_KEEP = frozenset(
    {
        "p",
        "div",
        "span",
        "br",
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "td",
        "th",
        "caption",
        "colgroup",
        "col",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "ul",
        "ol",
        "li",
        "b",
        "strong",
        "i",
        "u",
        "em",
        "font",
        "center",
        "sub",
        "sup",
        "small",
        "pre",
        "hr",
        "style",
    }
)
_DROP = frozenset(
    {
        "script",
        "iframe",
        "object",
        "embed",
        "frame",
        "frameset",
        "template",
        "noscript",
        "svg",
        "math",
        "textarea",
        "select",
        "applet",
        "param",
        "xmp",
        "plaintext",
        "noembed",
        "noframes",
        "video",
        "audio",
        "source",
        "track",
        "head",
        "meta",
        "link",
        "base",
        "form",
        "input",
        "button",
    }
)
_VOID = frozenset({"br", "hr", "col", "img"})
_DROP_VOID = frozenset(
    {"embed", "base", "meta", "link", "input", "frame", "param", "source", "track"}
)
_PASS = frozenset({"html", "body"})
_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_ATTRS = frozenset(
    {"colspan", "rowspan", "align", "valign", "width", "height", "style", "class", "id"}
)


class _Clean(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self._skip = 0
        self._stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, close=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, close=True)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in _PASS:
            return
        if self._skip:
            if name in _DROP and name not in _DROP_VOID:
                self._skip -= 1
            return
        if name in _DROP or name in _DROP_VOID:
            return
        emit = name if name in _KEEP else "span"
        if self._stack and self._stack[-1] == emit:
            self._stack.pop()
            self.parts.append(f"</{emit}>")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if not self._skip:
            self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self._skip:
            self.parts.append(f"&#{name};")

    def close(self) -> None:
        super().close()
        while self._stack:
            name = self._stack.pop()
            self.parts.append(f"</{name}>")

    def _start(self, tag: str, attrs: list[tuple[str, str | None]], *, close: bool) -> None:
        name = tag.lower()
        if name in _DROP_VOID:
            return
        if self._skip:
            if name in _DROP and not close:
                self._skip += 1
            return
        if name in _DROP:
            if not close:
                self._skip += 1
            return
        if name in _PASS:
            return
        if name == "img":
            src = _data_image_src(attrs)
            if src is None:
                return
            self._emit("img", attrs, extra_src=src, void=True)
            return
        emit = name if name in _KEEP else "span"
        void = emit in _VOID
        self._emit(emit, attrs, extra_src=None, void=void)
        if void:
            return
        if close:
            self.parts.append(f"</{emit}>")
            return
        self._stack.append(emit)

    def _emit(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
        *,
        extra_src: str | None,
        void: bool,
    ) -> None:
        chunks = [f"<{tag}"]
        for key, value in attrs:
            if not _keep_attr(key):
                continue
            if value is None:
                chunks.append(f" {key}")
            else:
                chunks.append(f' {key}="{html.escape(value, quote=True)}"')
        if extra_src is not None:
            chunks.append(f' src="{html.escape(extra_src, quote=True)}"')
        chunks.append(" />" if void else ">")
        self.parts.append("".join(chunks))


def _keep_attr(key: str) -> bool:
    name = key.lower()
    if name.startswith("on") or name.endswith(":href"):
        return False
    return name in _ATTRS


def _data_image_src(attrs: list[tuple[str, str | None]]) -> str | None:
    for key, value in attrs:
        if key.lower() != "src" or not value:
            continue
        if value.strip().lower().startswith("data:image/"):
            return value.strip()
    return None


def prepare_disclosure_html(page: str) -> str:
    """스크립트를 빼고, 공시 태그는 클릭할 수 있는 요소로 남긴 HTML."""
    parser = _Clean()
    parser.feed(page)
    parser.close()
    return "".join(parser.parts)


def heading_toc(page: str) -> tuple[str, list[tuple[str, str]]]:
    """제목 태그에 없는 id를 붙이고 (id, 제목) 목록을 돌려준다."""
    parser = _Headings()
    parser.feed(page)
    parser.close()
    return "".join(parser.parts), parser.entries


class _Headings(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.entries: list[tuple[str, str]] = []
        self._capture: str | None = None
        self._buf: list[str] = []
        self._n = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._open(tag, attrs, close=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._open(tag, attrs, close=True)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if self._capture is not None and name in _HEADINGS:
            title = "".join(self._buf).strip() or self._capture
            self.entries.append((self._capture, title))
            self._capture = None
            self._buf = []
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._capture is not None:
            self._buf.append(data)
        self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        token = f"&{name};"
        if self._capture is not None:
            self._buf.append(token)
        self.parts.append(token)

    def handle_charref(self, name: str) -> None:
        token = f"&#{name};"
        if self._capture is not None:
            self._buf.append(token)
        self.parts.append(token)

    def _open(self, tag: str, attrs: list[tuple[str, str | None]], *, close: bool) -> None:
        name = tag.lower()
        rewritten = list(attrs)
        if name in _HEADINGS and not close:
            self._n += 1
            ident = _attr(rewritten, "id") or f"toc-{self._n}"
            if _attr(rewritten, "id") is None:
                rewritten.append(("id", ident))
            self._capture = ident
            self._buf = []
        self.parts.append(_start_html(tag, rewritten, close=close))


def _attr(attrs: list[tuple[str, str | None]], key: str) -> str | None:
    for name, value in attrs:
        if name.lower() == key and value:
            return value
    return None


def _start_html(tag: str, attrs: list[tuple[str, str | None]], *, close: bool) -> str:
    chunks = [f"<{tag}"]
    for key, value in attrs:
        if value is None:
            chunks.append(f" {key}")
        else:
            chunks.append(f' {key}="{html.escape(value, quote=True)}"')
    chunks.append(" />" if close else ">")
    return "".join(chunks)


def toc_ids_present(page: str, entries: list[tuple[str, str]]) -> bool:
    """목차 id가 HTML의 id 속성에 모두 있는지."""
    if not entries:
        return False
    for ident, _title in entries:
        if f'id="{html.escape(ident, quote=True)}"' not in page:
            return False
    return True


def toc_from_cache(path: Path) -> list[tuple[str, str]] | None:
    """toc.json에 제목이 있으면 (id, 제목)을 돌려준다. 없으면 None."""
    if not path.is_file():
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    entries = _toc_entries(parsed)
    if not entries:
        return None
    return entries


def _toc_entries(parsed: object) -> list[tuple[str, str]]:
    items: object = parsed
    if isinstance(parsed, dict):
        for key in ("sections", "items", "toc"):
            if isinstance(parsed.get(key), list):
                items = parsed[key]
                break
        else:
            return []
    if not isinstance(items, list):
        return []
    found: list[tuple[str, str]] = []
    for index, item in enumerate(items, start=1):
        if isinstance(item, str) and item.strip():
            found.append((f"toc-{index}", item.strip()))
            continue
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("name") or item.get("section_name")
        ident = item.get("id") or item.get("ele_id") or item.get("anchor")
        if not isinstance(title, str) or not title.strip():
            continue
        anchor = str(ident).strip() if isinstance(ident, str) and ident.strip() else f"toc-{index}"
        found.append((anchor, title.strip()))
    return found
