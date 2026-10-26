"""HTML / text normalization for DART disclosure documents.

DART HTML is produced by a word-processor exporter: every run of text is wrapped in
`<font>`/`<span>` with inline styles, whitespace is a mix of `&nbsp;`, full-width spaces
and literal newlines, and there is a lot of `style`/`class` noise. The cleaner strips all
of that and keeps only the semantic skeleton (headings, paragraphs, tables, lists).
"""

from __future__ import annotations

import re
import unicodedata

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

# Tags whose content is never meaningful for extraction.
_DROP_TAGS = frozenset({"script", "style", "head", "meta", "link", "noscript", "iframe", "object"})

# Inline wrappers that carry only presentation; they are unwrapped (children preserved).
_UNWRAP_TAGS = frozenset(
    {"font", "span", "b", "i", "u", "strong", "em", "small", "big", "sub", "sup", "a", "center"}
)

# Attributes allowed to survive. Everything else (style, class, width, align, ...) is removed.
_KEEP_ATTRS = frozenset({"colspan", "rowspan", "id"})

# Whitespace-like characters that must become a plain space.
_SPACE_CHARS = {
    "\u00a0",  # NBSP
    "\u2002",
    "\u2003",
    "\u2009",
    "\u200a",
    "\u202f",
    "\u205f",
    "\u3000",  # full-width (ideographic) space
    "\ufeff",  # BOM
}
_ZERO_WIDTH = {"\u200b", "\u200c", "\u200d", "\u2060"}
_SPACE_RE = re.compile(r"[ \t\r\f\v]+")
_MULTI_NL_RE = re.compile(r"\n\s*\n+")


def normalize_text(text: str | None, *, keep_newlines: bool = False) -> str:
    """Normalize a text fragment for comparison and storage.

    - NFKC normalization (full-width digits/latin -> ASCII)
    - NBSP / ideographic spaces -> space, zero-width characters removed
    - runs of whitespace collapsed to one space (newlines optionally preserved)
    """
    if not text:
        return ""
    out = unicodedata.normalize("NFKC", text)
    for ch in _SPACE_CHARS:
        out = out.replace(ch, " ")
    for ch in _ZERO_WIDTH:
        out = out.replace(ch, "")
    if keep_newlines:
        out = _SPACE_RE.sub(" ", out)
        out = _MULTI_NL_RE.sub("\n", out)
        return "\n".join(line.strip() for line in out.split("\n")).strip()
    return " ".join(out.split())


def _parse(html: str) -> BeautifulSoup:
    # lxml is fast and tolerant; html5lib is slower but recovers badly nested tables.
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:  # pragma: no cover - defensive
        return BeautifulSoup(html, "html5lib")


def clean_soup(soup: BeautifulSoup) -> BeautifulSoup:
    """Strip presentation noise from a soup in place and return it."""
    for el in soup.find_all(string=lambda s: isinstance(s, Comment)):
        el.extract()
    for tag in soup.find_all(list(_DROP_TAGS)):
        tag.decompose()
    for tag in soup.find_all(list(_UNWRAP_TAGS)):
        tag.unwrap()
    for tag in soup.find_all(True):
        if not isinstance(tag, Tag):
            continue
        for attr in list(tag.attrs):
            if attr not in _KEEP_ATTRS:
                del tag.attrs[attr]
    for node in soup.find_all(string=True):
        if isinstance(node, NavigableString) and not isinstance(node, Comment):
            cleaned = normalize_text(str(node), keep_newlines=True)
            if cleaned != str(node):
                node.replace_with(cleaned)
    return soup


def clean_html(html: str) -> str:
    """Return a cleaned HTML string with only semantic structure left."""
    soup = clean_soup(_parse(html))
    body = soup.body or soup
    return str(body)


def html_to_text(html: str) -> str:
    """Flatten HTML to newline-separated text (block boundaries become newlines)."""
    soup = clean_soup(_parse(html))
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text(separator="\n")
    return normalize_text(text, keep_newlines=True)
