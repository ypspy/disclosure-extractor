"""노트북 로컬 골드 입수 화면.

실행: ``python -m dart_parser.gold.app --catalog <경로> --gold <경로>``
카탈로그 경로는 인자로만 받는다. 바인딩은 127.0.0.1뿐이다.
문서 페이지에서 고른 공시 글자를 gold_captures에 저장한다.
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
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote
from wsgiref.simple_server import make_server

from dart_parser.gold.cache import CACHE_ROOT, cache_dir, load_section_html
from dart_parser.gold.capture import capture_rows, known_subject
from dart_parser.gold.capture_page import render_capture_page
from dart_parser.gold.capture_store import (
    clear_capture,
    load_captures,
    load_units,
    save_capture,
    set_capture_status,
    set_unit,
)
from dart_parser.gold.db import migrate, open_gold
from dart_parser.gold.evidence import evidence_for, section_windows
from dart_parser.gold.subjects import BUNDLE_KEYS

LOOPBACK = "127.0.0.1"
_ID = re.compile(r"^[A-Za-z0-9]+$")
_MAX_BODY = 100_000
_ABSENT = frozenset({"not_applicable", "not_in_regime"})


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
    parser = argparse.ArgumentParser(description="로컬 골드 입수 화면")
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

    def load_disclosure(self, rcept_no: str, dcm_no: str) -> SourceDocument:
        """섹션 HTML을 이어 붙인다. 앵커는 붙이지 않는다."""
        ambiguous = self._dcm_ambiguous(rcept_no, dcm_no)
        pieces: list[str] = []
        seen: set[str] = set()
        uncertain = False
        identity = {"rcept_no": rcept_no, "dcm_no": dcm_no}
        for bundle in BUNDLE_KEYS:
            if not _windows(bundle):
                continue
            for item in _evidence(self.conn, identity, bundle):
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
        return SourceDocument("\n".join(pieces), uncertain, ambiguous)

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
    """문서 목록과 입수 저장."""

    def __init__(self, catalog: Path, gold: Path, cache: Path) -> None:
        self.store = ReviewStore(catalog, gold, cache)
        self.token = secrets.token_urlsafe(32)

    def close(self) -> None:
        self.store.close()

    def __call__(self, environ: dict[str, Any], start_response: Any) -> list[bytes]:
        method = environ.get("REQUEST_METHOD", "GET")
        parts = [part for part in (environ.get("PATH_INFO") or "/").split("/") if part]
        query = parse_qs(environ.get("QUERY_STRING") or "")
        if (
            len(parts) == 4
            and parts[0] == "doc"
            and parts[3] in {"capture", "unit"}
            and _safe_id(parts[1])
            and _safe_id(parts[2])
        ):
            if method != "POST":
                return _html(
                    start_response,
                    "405 Method Not Allowed",
                    "POST만 받습니다.",
                    [("Allow", "POST")],
                )
            if parts[3] == "capture":
                return _post_capture(self, environ, start_response, parts[1], parts[2])
            return _post_unit(self, environ, start_response, parts[1], parts[2])
        if method != "GET":
            return _html(
                start_response,
                "405 Method Not Allowed",
                "GET만 받습니다.",
                [("Allow", "GET")],
            )
        if not parts:
            return _html(start_response, "200 OK", _list_page(self.store, query))
        if len(parts) == 3 and parts[0] == "doc" and _safe_id(parts[1]) and _safe_id(parts[2]):
            page = _capture_document(self, parts[1], parts[2], query)
            if page is None:
                return _html(start_response, "404 Not Found", "문서가 없습니다.")
            return _html(start_response, "200 OK", page)
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


def _page(title: str, body: str) -> str:
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title>"
        "<style>"
        "body{margin:0;font-family:sans-serif}"
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


def _capture_document(
    app: ReviewApplication,
    rcept_no: str,
    dcm_no: str,
    query: dict[str, list[str]],
) -> str | None:
    if app.store.sample(rcept_no, dcm_no) is None:
        return None
    source = app.store.load_disclosure(rcept_no, dcm_no)
    company, report, filed = _filing_meta(app.store, rcept_no)
    return render_capture_page(
        rcept_no,
        dcm_no,
        app.token,
        source.html or "",
        capture_rows(),
        load_captures(app.store.conn, rcept_no, dcm_no),
        load_units(app.store.conn, rcept_no, dcm_no),
        company,
        report,
        filed,
        miss_bundle=_one(query, "miss_bundle"),
        miss_subject=_one(query, "miss_subject"),
    )


def _filing_meta(store: ReviewStore, rcept_no: str) -> tuple[str, str, str]:
    """회사명, 보고서명, 제출일. 카탈로그를 못 읽으면 빈 문자열이다."""
    try:
        row = store.conn.execute(
            """
            SELECT
                COALESCE(c.corp_name, d.corp_name, '') AS company,
                COALESCE(d.report_nm, '') AS report,
                COALESCE(d.rcept_dt, '') AS filed
            FROM cat.disclosures d
            LEFT JOIN cat.corps c ON c.corp_code = d.corp_code
            WHERE d.rcept_no = ?
            """,
            (rcept_no,),
        ).fetchone()
    except sqlite3.Error:
        return "", "", ""
    if row is None:
        return "", "", ""
    return str(row["company"] or ""), str(row["report"] or ""), str(row["filed"] or "")


def _post_capture(
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
    if app.store.sample(rcept_no, dcm_no) is None:
        return _html(start_response, "404 Not Found", "문서가 없습니다.")
    bundle = _one(form, "bundle")
    subject = _one(form, "subject")
    if not known_subject(bundle, subject):
        return _html(start_response, "400 Bad Request", "항목이 아닙니다.")
    status = _one(form, "status")
    conn = app.store.conn
    if status in _ABSENT:
        if not set_capture_status(conn, rcept_no, dcm_no, bundle, subject, status):
            return _html(start_response, "400 Bad Request", "저장하지 못했습니다.")
        return _see_other(start_response, rcept_no, dcm_no)
    if status == "clear":
        clear_capture(conn, rcept_no, dcm_no, bundle, subject)
        return _see_other(start_response, rcept_no, dcm_no)
    if not save_capture(conn, rcept_no, dcm_no, bundle, subject, _one(form, "text")):
        location = (
            f"/doc/{quote(rcept_no)}/{quote(dcm_no)}"
            f"?miss_bundle={quote(bundle)}&miss_subject={quote(subject)}"
        )
        return _html(
            start_response,
            "303 See Other",
            "읽을 수 없습니다.",
            [("Location", location)],
        )
    return _see_other(start_response, rcept_no, dcm_no)


def _post_unit(
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
    if app.store.sample(rcept_no, dcm_no) is None:
        return _html(start_response, "404 Not Found", "문서가 없습니다.")
    scale = _unit_scale(_one(form, "unit_scale"))
    group = _one(form, "unit_group")
    if scale is None or not set_unit(app.store.conn, rcept_no, dcm_no, group, scale):
        return _html(start_response, "400 Bad Request", "단위가 아닙니다.")
    return _see_other(start_response, rcept_no, dcm_no)


def _unit_scale(raw: str) -> int | None:
    if not raw.isdigit():
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _see_other(start_response: Any, rcept_no: str, dcm_no: str) -> list[bytes]:
    location = f"/doc/{quote(rcept_no)}/{quote(dcm_no)}"
    return _html(start_response, "303 See Other", "저장했습니다.", [("Location", location)])


if __name__ == "__main__":
    main()
