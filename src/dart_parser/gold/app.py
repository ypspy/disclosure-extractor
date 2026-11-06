"""노트북 로컬 골드 리뷰 화면.

실행: ``python -m dart_parser.gold.app --catalog <경로> --gold <경로>``
카탈로그 경로는 인자로만 받는다. 바인딩은 127.0.0.1뿐이다.
판정 저장은 POST이며, 샘플 라운드에 고정된 추출기 스냅샷만 보여 준다.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote
from wsgiref.simple_server import make_server

from dart_parser.gold.cache import CACHE_ROOT, cache_dir, load_section_html
from dart_parser.gold.db import migrate, open_gold
from dart_parser.gold.evidence import _matches_window, evidence_for, section_windows
from dart_parser.gold.labels import required_subjects
from dart_parser.gold.subjects import (
    BUNDLE_KEYS,
    TABLE_BUNDLES,
    extract_predicted,
    extraction_status,
    subjects_for,
)
from dart_parser.normalizer.numeric import to_int, to_number

LOOPBACK = "127.0.0.1"
_ID = re.compile(r"^[A-Za-z0-9]+$")
_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"
_VERDICTS = ("correct", "wrong", "na")
_PASS = "prefill"
_VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}
)
_SKIP_TAGS = frozenset({"head", "title", "script", "style"})
_MAX_BODY = 100_000


def bind_host(host: str) -> str:
    """루프백이 아니면 거부한다."""
    if host != LOOPBACK:
        raise ValueError("127.0.0.1만 바인딩합니다.")
    return LOOPBACK


def make_loopback_server(app: Any, port: int = 0) -> Any:
    """127.0.0.1에만 듣는 서버."""
    return make_server(bind_host(LOOPBACK), port, app)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """카탈로그와 gold.db 경로를 인자로 받는다."""
    parser = argparse.ArgumentParser(description="로컬 골드 리뷰 화면")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=CACHE_ROOT)
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args(argv)


@dataclass
class SourceDocument:
    """화면에 붙일 원문과 경고."""

    html: str | None
    encoding_uncertain: bool
    dcm_ambiguous: bool


class ReviewStore:
    """gold.db 읽기·쓰기와 캐시 파일 읽기. 카탈로그는 읽기 전용이다."""

    def __init__(self, catalog: Path, gold: Path, cache: Path) -> None:
        self.cache_root = Path(cache)
        self.conn = open_gold(Path(gold), Path(catalog))
        migrate(self.conn)

    def close(self) -> None:
        self.conn.close()

    def samples(self, period: str, stratum: str, status: str) -> list[sqlite3.Row]:
        rows = self.conn.execute(
            """
            SELECT run_id, rcept_no, dcm_no, period, stratum, status, queue_order
            FROM gold_samples
            ORDER BY period, stratum, status, queue_order, rcept_no
            """
        )
        chosen: list[sqlite3.Row] = []
        for row in rows:
            if period and row["period"] != period:
                continue
            if stratum and row["stratum"] != stratum:
                continue
            if status and row["status"] != status:
                continue
            chosen.append(row)
        return chosen

    def sample(self, rcept_no: str, dcm_no: str) -> sqlite3.Row | None:
        return self.conn.execute(
            """
            SELECT * FROM gold_samples
            WHERE rcept_no = ? AND dcm_no = ?
            ORDER BY queue_order
            LIMIT 1
            """,
            (rcept_no, dcm_no),
        ).fetchone()

    def pinned(self, run_id: str) -> tuple[str, str] | None:
        """라운드에 고정된 추출기 버전과 커밋. 없으면 None."""
        row = self.conn.execute(
            "SELECT params FROM gold_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        params = _object(None if row is None else row["params"])
        version = params.get("extractor_version")
        commit = params.get("extractor_commit")
        if isinstance(version, str) and version and isinstance(commit, str) and commit:
            return version, commit
        found = self.conn.execute(
            """
            SELECT extractor_version, extractor_commit
            FROM gold_run_extractors
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        if found is None:
            return None
        pinned_version = str(found["extractor_version"] or "")
        pinned_commit = str(found["extractor_commit"] or "")
        if pinned_version and pinned_commit:
            return pinned_version, pinned_commit
        return None

    def snapshot(self, version: str, rcept_no: str, dcm_no: str) -> dict[str, Any] | None:
        """고정 버전의 스냅샷만 읽는다."""
        row = self.conn.execute(
            """
            SELECT payload FROM extractor_snapshots
            WHERE extractor_version = ? AND rcept_no = ? AND dcm_no = ?
            """,
            (version, rcept_no, dcm_no),
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload"])
        if isinstance(payload, dict):
            return payload
        return None

    def load_source(self, rcept_no: str, dcm_no: str) -> SourceDocument:
        """섹션 HTML을 읽고 텍스트 노드에만 근거 앵커를 붙인다."""
        ambiguous = self._dcm_ambiguous(rcept_no, dcm_no)
        pieces: list[str] = []
        seen: set[str] = set()
        needles: dict[str, str] = {}
        uncertain = False
        identity = {"rcept_no": rcept_no, "dcm_no": dcm_no}
        for bundle in BUNDLE_KEYS:
            windows = _windows(bundle)
            if not windows:
                continue
            for item in _evidence(self.conn, identity, bundle):
                name = item.section_name or ""
                for window in windows:
                    if name and _matches_window(name, window):
                        needles.setdefault(window, name)
                loaded = load_section_html(
                    self.cache_root,
                    rcept_no,
                    {"ele_id": item.ele_id},
                    dcm_no=dcm_no,
                )
                if loaded is None:
                    continue
                uncertain = uncertain or loaded.encoding_uncertain
                key = item.ele_id or loaded.text
                if key in seen:
                    continue
                seen.add(key)
                pieces.append(loaded.text)
        if not pieces:
            loaded = load_section_html(self.cache_root, rcept_no, {}, dcm_no=dcm_no)
            if loaded is not None:
                pieces.append(loaded.text)
                uncertain = uncertain or loaded.encoding_uncertain
        if not pieces:
            return SourceDocument(None, False, ambiguous)
        combined = "\n".join(pieces)
        try:
            marked = _anchor_text(combined, needles)
        except Exception:
            marked = combined
        return SourceDocument(marked, uncertain, ambiguous)

    def _dcm_ambiguous(self, rcept_no: str, dcm_no: str) -> bool:
        """캐시가 문서 번호를 가리지 못하고 접수번호에 문서가 둘 이상이면 True."""
        base = cache_dir(self.cache_root, rcept_no)
        if not base.is_dir():
            return False
        if (base / dcm_no).is_dir():
            return False
        if _toc_names_dcm(base / "toc.json"):
            return False
        count = self.conn.execute(
            "SELECT COUNT(DISTINCT dcm_no) FROM gold_samples WHERE rcept_no = ?",
            (rcept_no,),
        ).fetchone()
        return count is not None and int(count[0]) > 1


class ReviewApplication:
    """문서 목록, 고정 스냅샷, 판정 저장."""

    def __init__(self, catalog: Path, gold: Path, cache: Path) -> None:
        self.store = ReviewStore(catalog, gold, cache)
        self.token = secrets.token_urlsafe(32)

    def close(self) -> None:
        self.store.close()

    def __call__(self, environ: dict[str, Any], start_response: Any) -> list[bytes]:
        method = environ.get("REQUEST_METHOD", "GET")
        parts = [part for part in (environ.get("PATH_INFO") or "/").split("/") if part]
        if len(parts) == 4 and parts[0] == "doc" and parts[3] == "label":
            if method != "POST":
                return _html(
                    start_response,
                    "405 Method Not Allowed",
                    "POST만 받습니다.",
                    [("Allow", "POST")],
                )
            if not (_safe_id(parts[1]) and _safe_id(parts[2])):
                return _html(start_response, "404 Not Found", "문서가 없습니다.")
            return _save(self, environ, start_response, parts[1], parts[2])
        if method != "GET":
            return _html(
                start_response,
                "405 Method Not Allowed",
                "GET만 받습니다.",
                [("Allow", "GET")],
            )
        query = parse_qs(environ.get("QUERY_STRING") or "")
        if not parts:
            return _html(start_response, "200 OK", _list_page(self.store, query))
        if len(parts) == 3 and parts[0] == "doc" and _safe_id(parts[1]) and _safe_id(parts[2]):
            page = _document_page(self, parts[1], parts[2])
            if page is None:
                return _html(start_response, "404 Not Found", "문서가 없습니다.")
            return _html(start_response, "200 OK", page)
        if (
            len(parts) == 4
            and parts[0] == "doc"
            and parts[3] == "source"
            and _safe_id(parts[1])
            and _safe_id(parts[2])
        ):
            return _source(start_response, self.store, parts[1], parts[2])
        return _html(start_response, "404 Not Found", "페이지가 없습니다.")


def main(argv: list[str] | None = None) -> None:
    """루프백에서 화면을 연다. 샘플링과 내려받기는 하지 않는다."""
    os.environ.setdefault("DART_LLM_ENABLED", "false")
    args = parse_args(argv)
    app = ReviewApplication(args.catalog, args.gold, args.cache)
    server = make_loopback_server(app, args.port)
    host, port = server.server_address[:2]
    print(f"http://{host}:{port}/", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        app.close()


def _safe_id(value: str) -> bool:
    return _ID.fullmatch(value) is not None


def _one(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key) or []
    return values[0] if values else ""


def _object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def _windows(bundle: str) -> tuple[str, ...]:
    try:
        return section_windows(bundle)
    except KeyError:
        return ()


def _evidence(conn: sqlite3.Connection, snapshot: dict[str, Any], bundle: str) -> list[Any]:
    try:
        return list(evidence_for(conn, snapshot, bundle))
    except sqlite3.Error:
        return []


def _toc_names_dcm(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return _has_dcm_marker(parsed)


def _has_dcm_marker(node: Any) -> bool:
    if isinstance(node, dict):
        marker = node.get("dcm_no")
        if isinstance(marker, str) and marker:
            return True
        return any(_has_dcm_marker(value) for value in node.values())
    if isinstance(node, list):
        return any(_has_dcm_marker(item) for item in node)
    return False


def _list_page(store: ReviewStore, query: dict[str, list[str]]) -> str:
    rows = store.samples(_one(query, "period"), _one(query, "stratum"), _one(query, "status"))
    if not rows:
        body = (
            '<p id="empty-samples">샘플이 없습니다. '
            "이 화면은 gold.db에 들어 있는 문서만 보여 주며, 샘플링은 실행하지 않습니다.</p>"
        )
    else:
        body = _sample_groups(rows)
    return _page("문서 목록", body)


def _sample_groups(rows: list[sqlite3.Row]) -> str:
    parts: list[str] = []
    current: tuple[str, str, str] | None = None
    for row in rows:
        key = (str(row["period"]), str(row["stratum"]), str(row["status"]))
        if key != current:
            if current is not None:
                parts.append("</section>")
            current = key
            period, stratum, status = key
            parts.append(
                "<section>"
                f"<h2>{html.escape(period)}</h2>"
                f"<h3>{html.escape(stratum)}</h3>"
                f"<p>{html.escape(status)}</p>"
            )
        rcept_no = str(row["rcept_no"])
        dcm_no = str(row["dcm_no"])
        href = f"/doc/{quote(rcept_no)}/{quote(dcm_no)}"
        parts.append(
            f'<p><a href="{href}">{html.escape(rcept_no)}/{html.escape(dcm_no)}</a></p>'
        )
    if current is not None:
        parts.append("</section>")
    return "".join(parts)


def _document_page(app: ReviewApplication, rcept_no: str, dcm_no: str) -> str | None:
    store = app.store
    sample = store.sample(rcept_no, dcm_no)
    if sample is None:
        return None
    pinned = store.pinned(str(sample["run_id"]))
    snapshot = None
    if pinned is not None:
        snapshot = store.snapshot(pinned[0], rcept_no, dcm_no)
    source_doc = store.load_source(rcept_no, dcm_no)
    if source_doc.html is None:
        source = '<p id="cache-missing">캐시 없음</p>'
    else:
        src = f"/doc/{quote(rcept_no)}/{quote(dcm_no)}/source"
        source = f'<iframe name="gold-source" title="원문" sandbox="" src="{src}"></iframe>'
    notices: list[str] = []
    if pinned is None:
        notices.append(
            '<p id="pin-missing">추출기 버전이 고정되어 있지 않습니다. 저장할 수 없습니다.</p>'
        )
        meta = ""
    else:
        meta = (
            f"<p>추출기 버전 {html.escape(pinned[0])} 커밋 {html.escape(pinned[1])}</p>"
        )
        if snapshot is None:
            notices.append(
                '<p id="snapshot-missing">고정된 버전의 스냅샷이 없습니다. 저장할 수 없습니다.</p>'
            )
    if source_doc.encoding_uncertain:
        notices.append('<p id="encoding-check">인코딩 확인 필요</p>')
    if source_doc.dcm_ambiguous:
        notices.append('<p id="dcm-warning">문서 번호를 구분할 수 없습니다.</p>')
    ready = pinned is not None and snapshot is not None
    slot = _forms(app.token, rcept_no, dcm_no, snapshot) if ready and snapshot is not None else ""
    fields = _field_table(rcept_no, dcm_no, snapshot if ready else None)
    notice = "".join(notices)
    body = (
        '<p><a href="/">목록</a></p>'
        f"<h1>{html.escape(rcept_no)}/{html.escape(dcm_no)}</h1>"
        f"{meta}{notice}"
        '<div class="layout">'
        f"<section>{source}</section>"
        f"<section>{fields}</section>"
        f'<aside id="judgment-slot">{notice}{slot}</aside>'
        "</div>"
    )
    return _page("문서", body)


def _field_table(rcept_no: str, dcm_no: str, snapshot: dict[str, Any] | None) -> str:
    rows: list[str] = []
    for bundle in BUNDLE_KEYS:
        windows = _windows(bundle)
        if windows:
            href = f"/doc/{quote(rcept_no)}/{quote(dcm_no)}/source#win-{windows[0]}"
        else:
            href = f"/doc/{quote(rcept_no)}/{quote(dcm_no)}/source"
        for subject in subjects_for(bundle):
            predicted = extract_predicted(snapshot, bundle, subject) if snapshot else None
            status = extraction_status(snapshot, bundle) if snapshot else None
            rows.append(
                "<tr "
                f'data-bundle="{html.escape(bundle)}" '
                f'data-subject="{html.escape(subject)}">'
                f'<td><a href="{href}" target="gold-source">{html.escape(bundle)}</a></td>'
                f"<td>{html.escape(subject)}</td>"
                f"<td>{html.escape(_show(status))}</td>"
                f"<td>{html.escape(_show(predicted))}</td>"
                "</tr>"
            )
    return "<table>" + "".join(rows) + "</table>"


def _show(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _forms(token: str, rcept_no: str, dcm_no: str, snapshot: dict[str, Any]) -> str:
    parts = [
        _subject_form(token, rcept_no, dcm_no, bundle, subject, snapshot)
        for bundle in BUNDLE_KEYS
        for subject in subjects_for(bundle)
    ]
    return "".join(parts)


def _subject_form(
    token: str,
    rcept_no: str,
    dcm_no: str,
    bundle: str,
    subject: str,
    snapshot: dict[str, Any],
) -> str:
    predicted = extract_predicted(snapshot, bundle, subject)
    action = f"/doc/{quote(rcept_no)}/{quote(dcm_no)}/label"
    rule = ""
    if bundle == "going_concern":
        rule = (
            "<p>의견 근거만 있거나, 전기 인용만 있거나, "
            "청산기준 강조만 있으면 0입니다.</p>"
        )
    return (
        f'<form method="post" action="{action}">'
        f'<input type="hidden" name="token" value="{html.escape(token)}">'
        f'<input type="hidden" name="bundle" value="{html.escape(bundle)}">'
        f'<input type="hidden" name="subject" value="{html.escape(subject)}">'
        f"<p>{html.escape(bundle)} {html.escape(subject)}</p>"
        f"{rule}"
        '<label><input type="radio" name="verdict" value="correct"> 맞음</label>'
        '<label><input type="radio" name="verdict" value="wrong"> 틀림</label>'
        '<label><input type="radio" name="verdict" value="na"> 해당 없음</label>'
        f"{_answer_inputs(bundle, predicted)}"
        '<button type="submit">저장</button>'
        "</form>"
    )


def _answer_inputs(bundle: str, predicted: Any) -> str:
    if bundle == "accounts":
        value = ""
        scale = ""
        if isinstance(predicted, dict):
            if predicted.get("value") is not None:
                value = str(predicted.get("value"))
            if predicted.get("unit_scale") is not None:
                scale = str(predicted.get("unit_scale"))
        return (
            '<label>표시값 <input name="display_value" '
            f'value="{html.escape(value)}"></label>'
            '<label>단위 <input name="unit_scale" '
            f'value="{html.escape(scale)}"></label>'
        )
    if bundle == "notes_toc":
        count = ""
        titles: list[str] = []
        if isinstance(predicted, dict):
            if predicted.get("count") is not None:
                count = str(predicted.get("count"))
            raw_titles = predicted.get("titles")
            if isinstance(raw_titles, list):
                titles = [str(item) for item in raw_titles]
        body = html.escape("\n".join(titles))
        return (
            '<label>개수 <input name="toc_count" '
            f'value="{html.escape(count)}"></label>'
            f'<label>제목 <textarea name="toc_titles">{body}</textarea></label>'
        )
    if bundle in TABLE_BUNDLES:
        return '<label>메모 <textarea name="note"></textarea></label>'
    return '<label>정답 <input name="gold_text" value=""></label>'


def _source(
    start_response: Any, store: ReviewStore, rcept_no: str, dcm_no: str
) -> list[bytes]:
    cached = store.load_source(rcept_no, dcm_no)
    if cached.html is None:
        return _html(start_response, "404 Not Found", "<p>캐시 없음</p>")
    document = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f'<meta http-equiv="Content-Security-Policy" content="{html.escape(_CSP)}">'
        f"</head><body>{cached.html}</body></html>"
    )
    return _html(
        start_response,
        "200 OK",
        document,
        [
            ("Content-Security-Policy", _CSP),
            ("Referrer-Policy", "no-referrer"),
        ],
    )


class _TextAnchor(HTMLParser):
    """근거 문자열 앞을 텍스트 노드에서만 표시한다."""

    def __init__(self, needles: dict[str, str]) -> None:
        super().__init__(convert_charrefs=False)
        self.pending = dict(needles)
        self.parts: list[str] = []
        self._skip_stack: list[bool] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.parts.append(_start_tag(tag, attrs))
        if tag in _VOID_TAGS:
            return
        self._skip_stack.append(tag in _SKIP_TAGS or _is_toc(tag, attrs))

    def handle_endtag(self, tag: str) -> None:
        if tag not in _VOID_TAGS and self._skip_stack:
            self._skip_stack.pop()
        self.parts.append(f"</{tag}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.parts.append(_start_tag(tag, attrs))

    def handle_data(self, data: str) -> None:
        if not any(self._skip_stack) and self.pending:
            for window, needle in list(self.pending.items()):
                index = data.find(needle)
                if index < 0 or not needle:
                    continue
                span = f'<span id="win-{html.escape(window)}"></span>'
                data = f"{data[:index]}{span}{data[index:]}"
                del self.pending[window]
        self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.parts.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self.parts.append(f"<!--{data}-->")


def _is_toc(tag: str, attrs: list[tuple[str, str | None]]) -> bool:
    if tag == "nav":
        return True
    attr = {name.lower(): value or "" for name, value in attrs}
    blob = f"{attr.get('id', '')} {attr.get('class', '')}".lower()
    return "toc" in blob or "목차" in blob


def _start_tag(tag: str, attrs: list[tuple[str, str | None]]) -> str:
    chunks = [f"<{tag}"]
    for name, value in attrs:
        if value is None:
            chunks.append(f" {name}")
        else:
            chunks.append(f' {name}="{html.escape(value, quote=True)}"')
    chunks.append(">")
    return "".join(chunks)


def _anchor_text(page: str, needles: dict[str, str]) -> str:
    if not needles:
        return page
    parser = _TextAnchor(needles)
    parser.feed(page)
    parser.close()
    return "".join(parser.parts)


def _page(title: str, body: str) -> str:
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title>"
        "<style>"
        "body{margin:0;font-family:sans-serif}"
        ".layout{display:grid;grid-template-columns:1fr 1fr minmax(18rem,24rem);height:100vh}"
        "iframe{width:100%;height:100%;border:0}"
        "aside{min-width:16rem;overflow:auto}"
        "form{border-top:1px solid #ccc;padding:0.4rem 0}"
        "</style></head><body>"
        f"{body}</body></html>"
    )


def _html(
    start_response: Any,
    status: str,
    body: str,
    extra: list[tuple[str, str]] | None = None,
) -> list[bytes]:
    data = body.encode("utf-8")
    headers = [
        ("Content-Type", "text/html; charset=utf-8"),
        ("Content-Length", str(len(data))),
        ("X-Content-Type-Options", "nosniff"),
    ]
    if extra:
        headers.extend(extra)
    start_response(status, headers)
    return [data]


def _save(
    app: ReviewApplication,
    environ: dict[str, Any],
    start_response: Any,
    rcept_no: str,
    dcm_no: str,
) -> list[bytes]:
    if not _host_allowed(environ) or not _origin_allowed(environ):
        return _reject(start_response)
    form = _form_body(environ)
    if not _token_ok(app.token, _one(form, "token")):
        return _reject(start_response)
    sample = app.store.sample(rcept_no, dcm_no)
    if sample is None:
        return _html(start_response, "404 Not Found", "문서가 없습니다.")
    bundle = _one(form, "bundle")
    subject = _one(form, "subject")
    if bundle not in BUNDLE_KEYS or subject not in subjects_for(bundle):
        return _html(start_response, "400 Bad Request", "판정 항목이 아닙니다.")
    verdict = _one(form, "verdict")
    if verdict not in _VERDICTS:
        return _html(start_response, "400 Bad Request", "판정이 필요합니다.")
    pinned = app.store.pinned(str(sample["run_id"]))
    if pinned is None:
        return _html(
            start_response,
            "400 Bad Request",
            "추출기 버전이 고정되어 있지 않습니다.",
        )
    snapshot = app.store.snapshot(pinned[0], rcept_no, dcm_no)
    if snapshot is None:
        return _html(start_response, "400 Bad Request", "고정된 버전의 스냅샷이 없습니다.")
    predicted = extract_predicted(snapshot, bundle, subject)
    built = _gold_value(bundle, verdict, predicted, form)
    if isinstance(built, str):
        return _html(start_response, "400 Bad Request", built)
    gold_value, note = built
    try:
        _write_label(
            app.store.conn,
            run_id=str(sample["run_id"]),
            rcept_no=rcept_no,
            dcm_no=dcm_no,
            bundle=bundle,
            subject=subject,
            verdict=verdict,
            gold_value=gold_value,
            shown_value=predicted,
            shown_version=pinned[0],
            note=note,
        )
    except Exception:
        return _html(start_response, "500 Internal Server Error", "저장하지 못했습니다.")
    return _html(
        start_response,
        "303 See Other",
        "저장했습니다.",
        [("Location", f"/doc/{quote(rcept_no)}/{quote(dcm_no)}")],
    )


def _reject(start_response: Any) -> list[bytes]:
    return _html(start_response, "403 Forbidden", "요청을 거절했습니다.")


def _host_allowed(environ: dict[str, Any]) -> bool:
    host = str(environ.get("HTTP_HOST") or "")
    port = str(environ.get("SERVER_PORT") or "")
    return host in {f"127.0.0.1:{port}", f"localhost:{port}"}


def _origin_allowed(environ: dict[str, Any]) -> bool:
    port = str(environ.get("SERVER_PORT") or "")
    bases = (f"http://127.0.0.1:{port}", f"http://localhost:{port}")
    origin = environ.get("HTTP_ORIGIN")
    if origin is not None and str(origin) not in bases:
        return False
    referer = environ.get("HTTP_REFERER")
    if referer is None:
        return True
    ref = str(referer)
    return any(ref == base or ref.startswith(f"{base}/") for base in bases)


def _token_ok(expected: str, given: str) -> bool:
    try:
        return secrets.compare_digest(given.encode("ascii"), expected.encode("ascii"))
    except UnicodeEncodeError:
        return False


def _form_body(environ: dict[str, Any]) -> dict[str, list[str]]:
    try:
        length = int(environ.get("CONTENT_LENGTH") or "0")
    except ValueError:
        return {}
    if length < 0 or length > _MAX_BODY:
        return {}
    raw = environ["wsgi.input"].read(length)
    return parse_qs(raw.decode("utf-8", errors="replace"), keep_blank_values=True)


def _gold_value(
    bundle: str, verdict: str, predicted: Any, form: dict[str, list[str]]
) -> tuple[Any, str] | str:
    note = _one(form, "note").strip()
    if verdict == "na":
        return None, ""
    if verdict == "correct":
        if bundle in TABLE_BUNDLES:
            return {"verdict": "correct"}, note
        return predicted, ""
    if bundle in TABLE_BUNDLES:
        if not note:
            return "메모가 필요합니다."
        return {"verdict": "wrong"}, note
    if bundle == "accounts":
        number = to_number(_one(form, "display_value").strip())
        scale = to_int(_one(form, "unit_scale").strip())
        if number is None:
            return "표시값이 필요합니다."
        if scale is None:
            return "단위가 필요합니다."
        stored = int(number) if number == int(number) else number
        return {"value": stored, "unit_scale": scale}, ""
    if bundle == "notes_toc":
        count = to_int(_one(form, "toc_count").strip())
        titles = [
            line.strip() for line in _one(form, "toc_titles").splitlines() if line.strip()
        ]
        if count is None or not titles or count != len(titles):
            return "주석 목차가 필요합니다."
        return {"count": count, "titles": titles}, ""
    text = _one(form, "gold_text").strip()
    if not text:
        return "정답 값이 필요합니다."
    whole = to_int(text)
    if whole is not None and str(whole) == text:
        return whole, ""
    return text, ""


def _write_label(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    rcept_no: str,
    dcm_no: str,
    bundle: str,
    subject: str,
    verdict: str,
    gold_value: Any,
    shown_value: Any,
    shown_version: str,
    note: str,
) -> None:
    try:
        existing = conn.execute(
            """
            SELECT * FROM gold_labels
            WHERE rcept_no = ? AND dcm_no = ? AND bundle = ? AND subject = ? AND pass = ?
            """,
            (rcept_no, dcm_no, bundle, subject, _PASS),
        ).fetchone()
        now = datetime.now(UTC).isoformat()
        if existing is not None:
            conn.execute(
                """
                INSERT INTO gold_label_history (
                    rcept_no, dcm_no, bundle, subject, pass, verdict, gold_value,
                    shown_value, shown_extractor_version, evidence, error_tag, note,
                    labeled_at, seconds, superseded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    existing["rcept_no"],
                    existing["dcm_no"],
                    existing["bundle"],
                    existing["subject"],
                    existing["pass"],
                    existing["verdict"],
                    existing["gold_value"],
                    existing["shown_value"],
                    existing["shown_extractor_version"],
                    existing["evidence"],
                    existing["error_tag"],
                    existing["note"],
                    existing["labeled_at"],
                    existing["seconds"],
                    now,
                ),
            )
            conn.execute(
                """
                DELETE FROM gold_labels
                WHERE rcept_no = ? AND dcm_no = ? AND bundle = ? AND subject = ? AND pass = ?
                """,
                (rcept_no, dcm_no, bundle, subject, _PASS),
            )
        conn.execute(
            """
            INSERT INTO gold_labels (
                rcept_no, dcm_no, bundle, subject, pass, verdict, gold_value, shown_value,
                shown_extractor_version, evidence, error_tag, note, labeled_at, seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rcept_no,
                dcm_no,
                bundle,
                subject,
                _PASS,
                verdict,
                _dump(gold_value),
                _dump(shown_value),
                shown_version,
                None,
                None,
                note,
                now,
                None,
            ),
        )
        _touch_sample(conn, run_id, rcept_no, dcm_no, now)
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _touch_sample(
    conn: sqlite3.Connection, run_id: str, rcept_no: str, dcm_no: str, now: str
) -> None:
    sample = conn.execute(
        """
        SELECT * FROM gold_samples
        WHERE run_id = ? AND rcept_no = ? AND dcm_no = ?
        """,
        (run_id, rcept_no, dcm_no),
    ).fetchone()
    if sample is None or sample["status"] in {"excluded", "skipped"}:
        return
    complete = True
    for bundle, subject in required_subjects(conn, run_id, rcept_no, dcm_no):
        found = conn.execute(
            """
            SELECT 1 FROM gold_labels
            WHERE rcept_no = ? AND dcm_no = ? AND bundle = ? AND subject = ? AND pass = ?
            """,
            (rcept_no, dcm_no, bundle, subject, _PASS),
        ).fetchone()
        if found is None:
            complete = False
            break
    if complete:
        status = "done"
        finished = sample["finished_at"] or now
    else:
        status = "in_progress"
        finished = None
    conn.execute(
        """
        UPDATE gold_samples
        SET status = ?, started_at = ?, finished_at = ?
        WHERE run_id = ? AND rcept_no = ? AND dcm_no = ?
        """,
        (
            status,
            sample["started_at"] or now,
            finished,
            run_id,
            rcept_no,
            dcm_no,
        ),
    )


def _dump(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


if __name__ == "__main__":
    main()
