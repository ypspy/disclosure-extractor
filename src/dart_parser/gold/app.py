"""노트북 로컬 골드 리뷰 화면.

실행: ``python -m dart_parser.gold.app --catalog <경로> --gold <경로>``
카탈로그 경로는 인자로만 받는다. 바인딩은 127.0.0.1뿐이다.
판정 입력은 붙이지 않는다.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote
from wsgiref.simple_server import make_server

from dart_parser.gold.cache import CACHE_ROOT, cache_dir
from dart_parser.gold.db import migrate, open_gold
from dart_parser.gold.evidence import _WINDOW_ALIASES, section_windows
from dart_parser.gold.subjects import (
    BUNDLE_KEYS,
    extract_predicted,
    extraction_status,
    subjects_for,
)

LOOPBACK = "127.0.0.1"
_ID = re.compile(r"^[A-Za-z0-9]+$")
_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"


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

    def latest_snapshot(self, rcept_no: str, dcm_no: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT payload FROM extractor_snapshots
            WHERE rcept_no = ? AND dcm_no = ?
            ORDER BY captured_at DESC
            LIMIT 1
            """,
            (rcept_no, dcm_no),
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload"])
        if isinstance(payload, dict):
            return payload
        return None

    def cached_html(self, rcept_no: str) -> str | None:
        path = cache_dir(self.cache_root, rcept_no) / "main.html"
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")


class ReviewApplication:
    """문서 목록과 읽기 전용 문서 화면."""

    def __init__(self, catalog: Path, gold: Path, cache: Path) -> None:
        self.store = ReviewStore(catalog, gold, cache)

    def close(self) -> None:
        self.store.close()

    def __call__(self, environ: dict[str, Any], start_response: Any) -> list[bytes]:
        method = environ.get("REQUEST_METHOD", "GET")
        if method != "GET":
            return _html(
                start_response,
                "405 Method Not Allowed",
                "GET만 받습니다.",
                [("Allow", "GET")],
            )
        parts = [part for part in (environ.get("PATH_INFO") or "/").split("/") if part]
        query = parse_qs(environ.get("QUERY_STRING") or "")
        if not parts:
            return _html(start_response, "200 OK", _list_page(self.store, query))
        if len(parts) == 3 and parts[0] == "doc" and _safe_id(parts[1]) and _safe_id(parts[2]):
            page = _document_page(self.store, parts[1], parts[2])
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
            return _source(start_response, self.store, parts[1])
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


def _document_page(store: ReviewStore, rcept_no: str, dcm_no: str) -> str | None:
    sample = store.sample(rcept_no, dcm_no)
    if sample is None:
        return None
    snapshot = store.latest_snapshot(rcept_no, dcm_no)
    cached = store.cached_html(rcept_no)
    if cached is None:
        source = '<p id="cache-missing">캐시 없음</p>'
    else:
        src = f"/doc/{quote(rcept_no)}/{quote(dcm_no)}/source"
        source = (
            f'<iframe name="gold-source" title="원문" sandbox="" src="{src}"></iframe>'
        )
    version = ""
    commit = ""
    if snapshot is not None:
        version = str(snapshot.get("extractor_version") or "")
        commit = str(snapshot.get("commit") or "")
    meta = (
        f"<p>추출기 버전 {html.escape(version)} 커밋 {html.escape(commit)}</p>"
        if snapshot is not None
        else "<p>스냅샷 없음</p>"
    )
    fields = _field_table(rcept_no, dcm_no, snapshot)
    # B단계: 판정 폼은 이 aside에 붙인다. 지금은 비워 둔다.
    body = (
        '<p><a href="/">목록</a></p>'
        f"<h1>{html.escape(rcept_no)}/{html.escape(dcm_no)}</h1>"
        f"{meta}"
        '<div class="layout">'
        f"<section>{source}</section>"
        f"<section>{fields}</section>"
        '<aside id="judgment-slot"></aside>'
        "</div>"
    )
    return _page("문서", body)


def _field_table(rcept_no: str, dcm_no: str, snapshot: dict[str, Any] | None) -> str:
    rows: list[str] = []
    for bundle in BUNDLE_KEYS:
        window = section_windows(bundle)[0]
        href = f"/doc/{quote(rcept_no)}/{quote(dcm_no)}/source#win-{window}"
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


def _source(start_response: Any, store: ReviewStore, rcept_no: str) -> list[bytes]:
    cached = store.cached_html(rcept_no)
    if cached is None:
        return _html(start_response, "404 Not Found", "<p>캐시 없음</p>")
    document = (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        f'<meta http-equiv="Content-Security-Policy" content="{html.escape(_CSP)}">'
        f"</head><body>{_annotate(cached)}</body></html>"
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


def _annotate(page: str) -> str:
    """섹션 별칭 앞에 스크롤용 앵커를 붙인다. 캐시 파일은 바꾸지 않는다."""
    marked = page
    for window, aliases in _WINDOW_ALIASES.items():
        anchor = f'<span id="win-{html.escape(window)}"></span>'
        for alias in aliases:
            index = marked.find(alias)
            if index < 0:
                continue
            marked = f"{marked[:index]}{anchor}{marked[index:]}"
            break
    return marked


def _page(title: str, body: str) -> str:
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title>"
        "<style>"
        "body{margin:0;font-family:sans-serif}"
        ".layout{display:grid;grid-template-columns:1fr 1fr 12rem;height:100vh}"
        "iframe{width:100%;height:100%;border:0}"
        "aside{min-width:8rem}"
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


if __name__ == "__main__":
    main()
