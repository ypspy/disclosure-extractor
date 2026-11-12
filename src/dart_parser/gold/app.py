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
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote
from wsgiref.simple_server import make_server

from dart_parser.gold.cache import CACHE_ROOT, cache_dir, load_section_html
from dart_parser.gold.capture import (
    capture_rows,
    field_control,
    known_subject,
    money_group,
    parse_click,
)
from dart_parser.gold.capture_html import (
    heading_toc,
    prepare_disclosure_html,
    toc_from_cache,
    toc_ids_present,
)
from dart_parser.gold.capture_page import capture_feedback, render_capture_page
from dart_parser.gold.capture_store import (
    clear_capture,
    finish_recapture,
    load_captures,
    load_units,
    remove_list_item,
    save_capture,
    set_capture_status,
    set_unit,
)
from dart_parser.gold.db import migrate, open_gold
from dart_parser.gold.recapture import (
    can_open_recapture,
    consistency_report,
    disagreements,
    next_recapture,
    recapture_done,
    recapture_in_progress,
    recapture_progress,
    save_adjudication,
)
from dart_parser.gold.scoring import Label

LOOPBACK = "127.0.0.1"
_ID = re.compile(r"^[A-Za-z0-9]+$")
_MAX_BODY = 100_000
_ABSENT = frozenset({"not_applicable", "not_in_regime"})
_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; "
    "img-src data:; connect-src 'self'; form-action 'self'; base-uri 'none'; "
    "object-src 'none'; frame-ancestors 'none'"
)
_CAPTURE_JS = files("dart_parser.gold").joinpath("static/capture.js").read_bytes()


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
    toc: tuple[tuple[str, str], ...] = field(default_factory=tuple)


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
        """캐시에 있는 문서 전체 HTML을 읽는다. 앵커는 붙이지 않는다."""
        ambiguous = self._dcm_ambiguous(rcept_no, dcm_no)
        loaded = load_section_html(self.cache_root, rcept_no, {}, dcm_no=dcm_no)
        if loaded is None:
            return SourceDocument(None, False, ambiguous)
        cleaned = prepare_disclosure_html(loaded.text)
        folder = _document_folder(self.cache_root, rcept_no, dcm_no)
        listed = toc_from_cache(folder / "toc.json")
        if listed is not None and toc_ids_present(cleaned, listed):
            toc = tuple(listed)
        else:
            cleaned, headings = heading_toc(cleaned)
            toc = tuple(headings)
        return SourceDocument(cleaned, loaded.encoding_uncertain, ambiguous, toc)

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

    def period_progress(self, period: str) -> tuple[int, int]:
        """이 기간의 완료 문서 수와 전체 문서 수."""
        row = self.conn.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END), 0),
                   COUNT(*)
            FROM gold_samples
            WHERE period = ?
            """,
            (period,),
        ).fetchone()
        return int(row[0]), int(row[1])

    def next_sample(self, period: str) -> tuple[str, str] | None:
        """이어 할 문서를 고른다. 쓰지 않는다."""
        row = self.conn.execute(
            """
            SELECT rcept_no, dcm_no
            FROM gold_samples
            WHERE period = ?
              AND role IN ('main', 'oversample')
              AND status NOT IN ('done', 'excluded', 'skipped')
            ORDER BY CASE WHEN status = 'in_progress' THEN 0 ELSE 1 END,
                     queue_order, rcept_no
            LIMIT 1
            """,
            (period,),
        ).fetchone()
        if row is None:
            return None
        return str(row["rcept_no"]), str(row["dcm_no"])


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
        if parts[:1] == ["static"]:
            if method == "GET" and parts == ["static", "capture.js"]:
                return _javascript(start_response)
            return _html(start_response, "404 Not Found", "페이지가 없습니다.")
        if parts[:1] == ["recapture"]:
            return _recapture(self, environ, start_response, method, parts[1:], query)
        if (
            len(parts) == 4
            and parts[0] == "doc"
            and parts[3] == "export"
            and _safe_id(parts[1])
            and _safe_id(parts[2])
        ):
            if method != "GET":
                return _html(
                    start_response,
                    "405 Method Not Allowed",
                    "GET만 받습니다.",
                    [("Allow", "GET")],
                )
            return _get_export(
                self, environ, start_response, parts[1], parts[2], capture_pass=1
            )
        if parts == ["next"] and method == "GET":
            return _next_document(self, start_response, query)
        if (
            len(parts) == 4
            and parts[0] == "doc"
            and parts[3] in {"capture", "unit", "complete", "preview"}
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
            if parts[3] == "complete":
                return _post_complete(self, environ, start_response, parts[1], parts[2])
            if parts[3] == "preview":
                return _post_preview(self, environ, start_response, parts[1], parts[2])
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
            if recapture_in_progress(self.store.conn, parts[1], parts[2]):
                return _html(start_response, "409 Conflict", "재입수 중")
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
        ("Content-Security-Policy", _CSP),
        ("Referrer-Policy", "no-referrer"),
    ]
    if extra:
        headers.extend(extra)
    start_response(status, headers)
    return [data]


def _reject(start_response: Any) -> list[bytes]:
    return _html(start_response, "403 Forbidden", "요청을 거절했습니다.")


def _json(start_response: Any, status: str, payload: Any) -> list[bytes]:
    body = json.dumps(payload, ensure_ascii=False).encode()
    start_response(
        status,
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("X-Content-Type-Options", "nosniff"),
        ],
    )
    return [body]


def _wants_json(environ: dict[str, Any]) -> bool:
    return "application/json" in str(environ.get("HTTP_ACCEPT") or "")


def _confirmed(raw: str) -> Any:
    if raw == "":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _host_allowed(environ: dict[str, Any]) -> bool:
    host = str(environ.get("HTTP_HOST") or "")
    port = str(environ.get("SERVER_PORT") or "")
    allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
    if port == "80":
        allowed.update({"127.0.0.1", "localhost"})
    return host in allowed


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
    *,
    capture_pass: int = 1,
    base: str = "doc",
) -> str | None:
    if app.store.sample(rcept_no, dcm_no) is None:
        return None
    source = app.store.load_disclosure(rcept_no, dcm_no)
    company, report, filed = _filing_meta(app.store, rcept_no)
    sample = app.store.sample(rcept_no, dcm_no)
    assert sample is not None
    saved = load_captures(app.store.conn, rcept_no, dcm_no, capture_pass=capture_pass)
    rows = capture_rows()
    if capture_pass == 2:
        period_done, period_total = recapture_progress(app.store.conn, str(sample["period"]))
    else:
        period_done, period_total = app.store.period_progress(str(sample["period"]))
    return render_capture_page(
        rcept_no,
        dcm_no,
        app.token,
        source.html or "",
        rows,
        saved,
        load_units(app.store.conn, rcept_no, dcm_no, capture_pass=capture_pass),
        company,
        report,
        filed,
        miss_bundle=_one(query, "miss_bundle"),
        miss_subject=_one(query, "miss_subject"),
        encoding_uncertain=source.encoding_uncertain,
        dcm_ambiguous=source.dcm_ambiguous,
        cache_missing=source.html is None,
        recorded=len(saved),
        row_total=len(rows),
        period_done=period_done,
        period_total=period_total,
        period=str(sample["period"]),
        toc=source.toc,
        base=base,
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


def _post_preview(
    app: ReviewApplication,
    environ: dict[str, Any],
    start_response: Any,
    rcept_no: str,
    dcm_no: str,
    *,
    capture_pass: int = 1,
) -> list[bytes]:
    if not _host_allowed(environ) or not _origin_allowed(environ):
        return _reject(start_response)
    form = _form_body(environ)
    if not _token_ok(app.token, _one(form, "token")):
        return _reject(start_response)
    if app.store.sample(rcept_no, dcm_no) is None:
        return _json(start_response, "404 Not Found", {"error": "문서가 없습니다."})
    blocked = _ambiguous(app, rcept_no, dcm_no, start_response)
    if blocked is not None:
        return blocked
    if capture_pass == 1 and recapture_in_progress(app.store.conn, rcept_no, dcm_no):
        return _json(start_response, "409 Conflict", {"error": "재입수 중"})
    if capture_pass == 2 and recapture_done(app.store.conn, rcept_no, dcm_no):
        return _json(start_response, "409 Conflict", {"error": "재입수가 끝났습니다"})
    bundle = _one(form, "bundle")
    subject = _one(form, "subject")
    if not known_subject(bundle, subject):
        return _json(start_response, "400 Bad Request", {"error": "항목이 아닙니다."})
    text = _one(form, "text")
    scale = None
    group = money_group(bundle, subject)
    if group is not None:
        scale = load_units(
            app.store.conn, rcept_no, dcm_no, capture_pass=capture_pass
        ).get(group)
    engagement = None
    if bundle == "icfr":
        from dart_parser.gold.capture_store import _engagement

        engagement = _engagement(app.store.conn, rcept_no, dcm_no, capture_pass)
    control = field_control(bundle, subject, icfr_engagement=engagement)
    proposal = parse_click(
        bundle, subject, text, unit_scale=scale, icfr_engagement=engagement
    )
    blocked = control.blocked
    if group is not None and scale is None and not blocked:
        blocked = "단위를 먼저 선택하세요"
    payload = {
        "proposal": proposal,
        "kind": control.kind,
        "options": [{"value": value, "label": label} for value, label in control.options],
        "blocked": blocked,
    }
    return _json(start_response, "200 OK", payload)


def _post_capture(
    app: ReviewApplication,
    environ: dict[str, Any],
    start_response: Any,
    rcept_no: str,
    dcm_no: str,
    *,
    capture_pass: int = 1,
    base: str = "doc",
) -> list[bytes]:
    if not _host_allowed(environ) or not _origin_allowed(environ):
        return _reject(start_response)
    form = _form_body(environ)
    if not _token_ok(app.token, _one(form, "token")):
        return _reject(start_response)
    locked = _pass_write_locked(app, rcept_no, dcm_no, capture_pass, start_response)
    if locked is not None:
        return locked
    if app.store.sample(rcept_no, dcm_no) is None:
        return _html(start_response, "404 Not Found", "문서가 없습니다.")
    if capture_pass == 2:
        closed = _recapture_closed(app, rcept_no, dcm_no, start_response)
        if closed is not None:
            return closed
    blocked = _ambiguous(app, rcept_no, dcm_no, start_response)
    if blocked is not None:
        return blocked
    bundle = _one(form, "bundle")
    subject = _one(form, "subject")
    if not known_subject(bundle, subject):
        return _html(start_response, "400 Bad Request", "항목이 아닙니다.")
    status = _one(form, "status")
    conn = app.store.conn
    if status in {"remove_title", "remove_item"}:
        target = (
            ("notes_toc", "value") if status == "remove_title" else ("communications", "items")
        )
        if (bundle, subject) != target:
            return _html(start_response, "400 Bad Request", "항목이 아닙니다.")
        index = _index(_one(form, "index"))
        if index is None or not remove_list_item(
            conn, rcept_no, dcm_no, bundle, subject, index, capture_pass=capture_pass
        ):
            return _html(start_response, "400 Bad Request", "지우지 못했습니다.")
        if _wants_json(environ):
            return _capture_json(
                app, start_response, rcept_no, dcm_no, bundle, subject, capture_pass=capture_pass
            )
        return _see_other(start_response, rcept_no, dcm_no, base)
    if status in _ABSENT:
        if not set_capture_status(
            conn, rcept_no, dcm_no, bundle, subject, status, capture_pass=capture_pass
        ):
            return _html(start_response, "400 Bad Request", "저장하지 못했습니다.")
        if _wants_json(environ):
            return _capture_json(
                app, start_response, rcept_no, dcm_no, bundle, subject, capture_pass=capture_pass
            )
        return _see_other(start_response, rcept_no, dcm_no, base)
    if status == "clear":
        clear_capture(conn, rcept_no, dcm_no, bundle, subject, capture_pass=capture_pass)
        if _wants_json(environ):
            return _capture_json(
                app, start_response, rcept_no, dcm_no, bundle, subject, capture_pass=capture_pass
            )
        return _see_other(start_response, rcept_no, dcm_no, base)
    if not save_capture(
        conn,
        rcept_no,
        dcm_no,
        bundle,
        subject,
        _one(form, "text"),
        confirmed=_confirmed(_one(form, "confirmed")),
        capture_pass=capture_pass,
    ):
        if _wants_json(environ):
            return _json(
                start_response,
                "422 Unprocessable Entity",
                {
                    "ok": False,
                    "error": "읽을 수 없습니다.",
                    "miss_bundle": bundle,
                    "miss_subject": subject,
                },
            )
        location = (
            f"/{base}/{quote(rcept_no)}/{quote(dcm_no)}"
            f"?miss_bundle={quote(bundle)}&miss_subject={quote(subject)}"
        )
        return _html(
            start_response,
            "303 See Other",
            "읽을 수 없습니다.",
            [("Location", location)],
        )
    if _wants_json(environ):
        return _capture_json(
            app, start_response, rcept_no, dcm_no, bundle, subject, capture_pass=capture_pass
        )
    return _see_other(start_response, rcept_no, dcm_no, base)


def _capture_json(
    app: ReviewApplication,
    start_response: Any,
    rcept_no: str,
    dcm_no: str,
    bundle: str,
    subject: str,
    *,
    capture_pass: int,
) -> list[bytes]:
    saved = load_captures(app.store.conn, rcept_no, dcm_no, capture_pass=capture_pass)
    feedback = capture_feedback(bundle, subject, saved.get((bundle, subject)))
    return _json(
        start_response,
        "200 OK",
        {
            "ok": True,
            "bundle": bundle,
            "subject": subject,
            "status": feedback["status"],
            "value": feedback["value"],
            "evidence": feedback["evidence"],
            "shown": feedback["shown"],
            "lines": feedback["lines"],
            "replay": feedback["replay"],
            "recorded": len(saved),
            "row_total": len(capture_rows()),
            "cleared": (bundle, subject) not in saved,
        },
    )


def _get_export(
    app: ReviewApplication,
    environ: dict[str, Any],
    start_response: Any,
    rcept_no: str,
    dcm_no: str,
    *,
    capture_pass: int,
) -> list[bytes]:
    """저장 표만 읽는다. 위치와 선택 방법은 넣지 않는다."""
    if not _host_allowed(environ):
        return _reject(start_response)
    if capture_pass == 1 and recapture_in_progress(app.store.conn, rcept_no, dcm_no):
        return _html(start_response, "409 Conflict", "재입수 중")
    sample = app.store.sample(rcept_no, dcm_no)
    if sample is None:
        return _json(start_response, "404 Not Found", {"error": "문서가 없습니다."})
    if capture_pass == 2 and not can_open_recapture(
        app.store.conn, str(sample["run_id"]), rcept_no, dcm_no
    ):
        return _html(start_response, "409 Conflict", "재입수 대상이 아닙니다.")
    saved = load_captures(app.store.conn, rcept_no, dcm_no, capture_pass=capture_pass)
    doc_id = f"{rcept_no}/{dcm_no}"
    records: list[dict[str, Any]] = []
    for row in capture_rows():
        record = saved.get((row.bundle, row.subject))
        if record is None:
            continue
        value = None
        raw_value = record["value"]
        if raw_value:
            try:
                value = json.loads(raw_value)
            except (TypeError, json.JSONDecodeError):
                value = None
        records.append(
            {
                "doc_id": doc_id,
                "field_key": f"{row.bundle}/{row.subject}",
                "extracted_value": value,
                "raw_text": str(record["evidence"] or ""),
                "locator": None,
                "selection_method": None,
            }
        )
    body = json.dumps(records, ensure_ascii=False).encode()
    filename = f"gold-{rcept_no}-{dcm_no}.json"
    start_response(
        "200 OK",
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Content-Disposition", f'attachment; filename="{filename}"'),
            ("X-Content-Type-Options", "nosniff"),
        ],
    )
    return [body]


def _post_unit(
    app: ReviewApplication,
    environ: dict[str, Any],
    start_response: Any,
    rcept_no: str,
    dcm_no: str,
    *,
    capture_pass: int = 1,
    base: str = "doc",
) -> list[bytes]:
    if not _host_allowed(environ) or not _origin_allowed(environ):
        return _reject(start_response)
    form = _form_body(environ)
    if not _token_ok(app.token, _one(form, "token")):
        return _reject(start_response)
    locked = _pass_write_locked(app, rcept_no, dcm_no, capture_pass, start_response)
    if locked is not None:
        return locked
    if app.store.sample(rcept_no, dcm_no) is None:
        return _html(start_response, "404 Not Found", "문서가 없습니다.")
    if capture_pass == 2:
        closed = _recapture_closed(app, rcept_no, dcm_no, start_response)
        if closed is not None:
            return closed
    blocked = _ambiguous(app, rcept_no, dcm_no, start_response)
    if blocked is not None:
        return blocked
    scale = _unit_scale(_one(form, "unit_scale"))
    group = _one(form, "unit_group")
    if scale is None or not set_unit(
        app.store.conn, rcept_no, dcm_no, group, scale, capture_pass=capture_pass
    ):
        return _html(start_response, "400 Bad Request", "단위가 아닙니다.")
    return _see_other(start_response, rcept_no, dcm_no, base)


def _index(raw: str) -> int | None:
    if not raw.isdecimal():
        return None
    return int(raw)


def _ambiguous(
    app: ReviewApplication,
    rcept_no: str,
    dcm_no: str,
    start_response: Any,
) -> list[bytes] | None:
    if not app.store._dcm_ambiguous(rcept_no, dcm_no):
        return None
    return _html(start_response, "409 Conflict", "문서번호를 구분할 수 없습니다.")


def _post_complete(
    app: ReviewApplication,
    environ: dict[str, Any],
    start_response: Any,
    rcept_no: str,
    dcm_no: str,
    *,
    capture_pass: int = 1,
    base: str = "doc",
) -> list[bytes]:
    if not _host_allowed(environ) or not _origin_allowed(environ):
        return _reject(start_response)
    form = _form_body(environ)
    if not _token_ok(app.token, _one(form, "token")):
        return _reject(start_response)
    locked = _pass_write_locked(app, rcept_no, dcm_no, capture_pass, start_response)
    if locked is not None:
        return locked
    if app.store.sample(rcept_no, dcm_no) is None:
        return _html(start_response, "404 Not Found", "문서가 없습니다.")
    if capture_pass == 2:
        closed = _recapture_closed(app, rcept_no, dcm_no, start_response)
        if closed is not None:
            return closed
    blocked = _ambiguous(app, rcept_no, dcm_no, start_response)
    if blocked is not None:
        return blocked
    saved = load_captures(app.store.conn, rcept_no, dcm_no, capture_pass=capture_pass)
    missing = [
        row.label
        for row in capture_rows()
        if (row.bundle, row.subject) not in saved
    ]
    if missing:
        items = "".join(f"<li>{html.escape(name)}</li>" for name in missing)
        return _html(
            start_response,
            "400 Bad Request",
            f'<ul id="missing-rows">{items}</ul>',
        )
    if capture_pass == 2:
        finish_recapture(app.store.conn, rcept_no, dcm_no)
        return _see_other(start_response, rcept_no, dcm_no, base)
    app.store.conn.execute(
        """
        UPDATE gold_samples
        SET status = 'done', finished_at = ?
        WHERE rcept_no = ? AND dcm_no = ?
          AND status NOT IN ('excluded', 'skipped')
        """,
        (datetime.now(UTC).isoformat(), rcept_no, dcm_no),
    )
    app.store.conn.commit()
    return _see_other(start_response, rcept_no, dcm_no, base)


def _next_document(
    app: ReviewApplication,
    start_response: Any,
    query: dict[str, list[str]],
) -> list[bytes]:
    period = _one(query, "period")
    if not period:
        return _html(start_response, "400 Bad Request", "기간이 없습니다.")
    found = app.store.next_sample(period)
    if found is None:
        return _html(start_response, "404 Not Found", "다음 문서가 없습니다.")
    rcept_no, dcm_no = found
    location = f"/doc/{quote(rcept_no)}/{quote(dcm_no)}"
    return _html(start_response, "303 See Other", "다음 문서입니다.", [("Location", location)])


def _javascript(start_response: Any) -> list[bytes]:
    start_response(
        "200 OK",
        [
            ("Content-Type", "text/javascript"),
            ("Content-Length", str(len(_CAPTURE_JS))),
            ("X-Content-Type-Options", "nosniff"),
        ],
    )
    return [_CAPTURE_JS]


def _document_folder(root: Path, rcept_no: str, dcm_no: str) -> Path:
    folder = cache_dir(root, rcept_no)
    if dcm_no and (folder / dcm_no).is_dir():
        return folder / dcm_no
    return folder


def _unit_scale(raw: str) -> int | None:
    if not raw.isdigit():
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _see_other(
    start_response: Any, rcept_no: str, dcm_no: str, base: str = "doc"
) -> list[bytes]:
    location = f"/{base}/{quote(rcept_no)}/{quote(dcm_no)}"
    return _html(start_response, "303 See Other", "저장했습니다.", [("Location", location)])


def _recapture(
    app: ReviewApplication,
    environ: dict[str, Any],
    start_response: Any,
    method: str,
    parts: list[str],
    query: dict[str, list[str]],
) -> list[bytes]:
    if parts == ["next"] and method == "GET":
        return _next_recapture_document(app, start_response, query)
    if (
        len(parts) == 3
        and parts[2] == "export"
        and _safe_id(parts[0])
        and _safe_id(parts[1])
    ):
        if method != "GET":
            return _html(
                start_response,
                "405 Method Not Allowed",
                "GET만 받습니다.",
                [("Allow", "GET")],
            )
        return _get_export(
            app, environ, start_response, parts[0], parts[1], capture_pass=2
        )
    if parts == ["report"] and method == "GET":
        return _recapture_report(app, start_response, query)
    if parts == ["adjudication"] and method == "GET":
        return _adjudication_page(app, start_response, query)
    if parts == ["adjudicate"] and method == "POST":
        return _post_adjudicate(app, environ, start_response)
    if (
        len(parts) == 3
        and parts[2] in {"capture", "unit", "complete", "preview"}
        and _safe_id(parts[0])
        and _safe_id(parts[1])
    ):
        if method != "POST":
            return _html(
                start_response,
                "405 Method Not Allowed",
                "POST만 받습니다.",
                [("Allow", "POST")],
            )
        if parts[2] == "capture":
            return _post_capture(
                app,
                environ,
                start_response,
                parts[0],
                parts[1],
                capture_pass=2,
                base="recapture",
            )
        if parts[2] == "preview":
            return _post_preview(
                app,
                environ,
                start_response,
                parts[0],
                parts[1],
                capture_pass=2,
            )
        if parts[2] == "complete":
            return _post_complete(
                app,
                environ,
                start_response,
                parts[0],
                parts[1],
                capture_pass=2,
                base="recapture",
            )
        return _post_unit(
            app,
            environ,
            start_response,
            parts[0],
            parts[1],
            capture_pass=2,
            base="recapture",
        )
    if method != "GET":
        return _html(
            start_response,
            "405 Method Not Allowed",
            "GET만 받습니다.",
            [("Allow", "GET")],
        )
    if len(parts) == 2 and _safe_id(parts[0]) and _safe_id(parts[1]):
        sample = app.store.sample(parts[0], parts[1])
        if sample is None:
            return _html(start_response, "404 Not Found", "문서가 없습니다.")
        if not can_open_recapture(
            app.store.conn, str(sample["run_id"]), parts[0], parts[1]
        ):
            return _html(start_response, "409 Conflict", "재입수 대상이 아닙니다.")
        page = _capture_document(
            app, parts[0], parts[1], query, capture_pass=2, base="recapture"
        )
        if page is None:
            return _html(start_response, "404 Not Found", "문서가 없습니다.")
        return _html(start_response, "200 OK", page)
    return _html(start_response, "404 Not Found", "페이지가 없습니다.")


def _pass_write_locked(
    app: ReviewApplication,
    rcept_no: str,
    dcm_no: str,
    capture_pass: int,
    start_response: Any,
) -> list[bytes] | None:
    """토큰 검사 다음, 저장과 빠진 행 계산보다 먼저 쓰기를 막는다."""
    if capture_pass == 1 and recapture_in_progress(app.store.conn, rcept_no, dcm_no):
        return _html(start_response, "409 Conflict", "재입수 중")
    if capture_pass == 2 and recapture_done(app.store.conn, rcept_no, dcm_no):
        return _html(start_response, "409 Conflict", "재입수가 끝났습니다")
    return None


def _recapture_closed(
    app: ReviewApplication,
    rcept_no: str,
    dcm_no: str,
    start_response: Any,
) -> list[bytes] | None:
    sample = app.store.sample(rcept_no, dcm_no)
    if sample is None:
        return _html(start_response, "404 Not Found", "문서가 없습니다.")
    if can_open_recapture(app.store.conn, str(sample["run_id"]), rcept_no, dcm_no):
        return None
    return _html(start_response, "409 Conflict", "재입수 대상이 아닙니다.")


def _next_recapture_document(
    app: ReviewApplication,
    start_response: Any,
    query: dict[str, list[str]],
) -> list[bytes]:
    period = _one(query, "period")
    if not period:
        return _html(start_response, "400 Bad Request", "기간이 없습니다.")
    found = next_recapture(app.store.conn, period)
    if found is None:
        return _html(start_response, "404 Not Found", "다음 문서가 없습니다.")
    rcept_no, dcm_no = found
    location = f"/recapture/{quote(rcept_no)}/{quote(dcm_no)}"
    return _html(start_response, "303 See Other", "다음 문서입니다.", [("Location", location)])


def _recapture_report(
    app: ReviewApplication,
    start_response: Any,
    query: dict[str, list[str]],
) -> list[bytes]:
    run_id = _one(query, "run")
    if not run_id:
        return _html(start_response, "400 Bad Request", "실행이 없습니다.")
    rows = consistency_report(app.store.conn, run_id)
    body = "".join(
        (
            "<tr "
            f'data-period="{html.escape(row.period, quote=True)}" '
            f'data-bundle="{html.escape(row.bundle, quote=True)}" '
            f'data-subject="{html.escape(row.subject, quote=True)}">'
            f'<td class="n">{row.n}</td>'
            f'<td class="agree">{row.agree}</td>'
            f'<td class="rate">{row.rate:.10f}</td>'
            f'<td class="wilson">{row.wilson_lo:.10f}</td>'
            "</tr>"
        )
        for row in rows
    )
    page = _page(
        "재입수 일치",
        f'<table id="consistency-report"><tbody>{body}</tbody></table>',
    )
    return _html(start_response, "200 OK", page)


def _adjudication_page(
    app: ReviewApplication,
    start_response: Any,
    query: dict[str, list[str]],
) -> list[bytes]:
    run_id = _one(query, "run")
    if not run_id:
        return _html(start_response, "400 Bad Request", "실행이 없습니다.")
    decided = {
        (str(row["rcept_no"]), str(row["dcm_no"]), str(row["bundle"]), str(row["subject"]))
        for row in app.store.conn.execute(
            "SELECT rcept_no, dcm_no, bundle, subject FROM gold_adjudications"
        )
    }
    pending = [
        item
        for item in disagreements(app.store.conn, run_id)
        if (item.rcept_no, item.dcm_no, item.bundle, item.subject) not in decided
    ]
    forms = "".join(_adjudication_form(app.token, run_id, item) for item in pending)
    if not forms:
        forms = '<p id="adjudication-empty">판정할 항목이 없습니다.</p>'
    return _html(start_response, "200 OK", _page("재입수 판정", forms))


def _adjudication_form(token: str, run_id: str, item: Any) -> str:
    hidden = (
        f'<input type="hidden" name="token" value="{html.escape(token, quote=True)}">'
        f'<input type="hidden" name="run_id" value="{html.escape(run_id, quote=True)}">'
        f'<input type="hidden" name="rcept_no" value="{html.escape(item.rcept_no, quote=True)}">'
        f'<input type="hidden" name="dcm_no" value="{html.escape(item.dcm_no, quote=True)}">'
        f'<input type="hidden" name="bundle" value="{html.escape(item.bundle, quote=True)}">'
        f'<input type="hidden" name="subject" value="{html.escape(item.subject, quote=True)}">'
    )
    return (
        '<form method="post" action="/recapture/adjudicate">'
        f"{hidden}"
        f"<p>{html.escape(item.rcept_no)}/{html.escape(item.dcm_no)} "
        f"{html.escape(item.bundle)} {html.escape(item.subject)}</p>"
        f'<p class="pass-1">{html.escape(_label_text(item.first))}</p>'
        f'<p class="pass-2">{html.escape(_label_text(item.second))}</p>'
        '<label><input type="radio" name="chosen_pass" value="1"> 1차</label>'
        '<label><input type="radio" name="chosen_pass" value="2"> 2차</label>'
        '<input name="note">'
        '<button type="submit">판정</button>'
        "</form>"
    )


def _label_text(label: Label | None) -> str:
    if label is None:
        return "기록 없음"
    return f"{label.verdict} {json.dumps(label.gold_value, ensure_ascii=False)}"


def _post_adjudicate(
    app: ReviewApplication,
    environ: dict[str, Any],
    start_response: Any,
) -> list[bytes]:
    if not _host_allowed(environ) or not _origin_allowed(environ):
        return _reject(start_response)
    form = _form_body(environ)
    if not _token_ok(app.token, _one(form, "token")):
        return _reject(start_response)
    rcept_no = _one(form, "rcept_no")
    dcm_no = _one(form, "dcm_no")
    if app.store.sample(rcept_no, dcm_no) is None:
        return _html(start_response, "404 Not Found", "문서가 없습니다.")
    blocked = _ambiguous(app, rcept_no, dcm_no, start_response)
    if blocked is not None:
        return blocked
    chosen = _one(form, "chosen_pass")
    note = _one(form, "note")
    if chosen not in {"1", "2"} or not note.strip():
        return _html(start_response, "400 Bad Request", "판정할 수 없습니다.")
    if not save_adjudication(
        app.store.conn,
        rcept_no,
        dcm_no,
        _one(form, "bundle"),
        _one(form, "subject"),
        int(chosen),
        note,
        run_id=_one(form, "run_id"),
    ):
        return _html(start_response, "400 Bad Request", "판정할 수 없습니다.")
    location = f"/recapture/adjudication?run={quote(_one(form, 'run_id'))}"
    return _html(start_response, "303 See Other", "판정했습니다.", [("Location", location)])


if __name__ == "__main__":
    main()
