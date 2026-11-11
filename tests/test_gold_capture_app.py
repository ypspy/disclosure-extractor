"""입수 화면. 클릭과 상태 버튼이 gold_captures에 남는다."""

from __future__ import annotations

import io
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

from dart_parser.gold.app import ReviewApplication
from dart_parser.gold.db import migrate, open_gold
from gold_fixtures import make_catalog


def _request(
    app: ReviewApplication,
    method: str,
    path: str,
    query: str = "",
) -> tuple[str, dict[str, str], bytes]:
    environ = {"PATH_INFO": path, "QUERY_STRING": query, "REQUEST_METHOD": method}
    setup_testing_defaults(environ)
    environ["wsgi.input"] = io.BytesIO()
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]], exc_info=None) -> None:
        del exc_info
        captured["status"] = status
        captured["headers"] = {key: value for key, value in headers}

    body = b"".join(app(environ, start_response))
    return str(captured["status"]), dict(captured["headers"]), body


def _build(tmp_path: Path) -> ReviewApplication:
    catalog = make_catalog(tmp_path)
    gold_path = tmp_path / "gold.db"
    cache = tmp_path / "cache"
    conn = open_gold(gold_path, None)
    migrate(conn)
    conn.execute(
        """
        INSERT INTO gold_runs (
            run_id, seed, created_at, population_sql_sha, db_snapshot, params, stats
        ) VALUES (
            'run', 'seed', '2026-11-06T00:00:00+00:00', 'x', NULL,
            '{"extractor_version": "0.1.0", "extractor_commit": "abc123"}', '{}'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO gold_samples (
            run_id, rcept_no, dcm_no, period, stratum, stratum_weight, sample_hash,
            mode, role, queue_order, status, meta
        ) VALUES (
            'run', 'R100', 'D100', 'P7', 'listed', 1, 'h', 'prefill', 'main', 1, 'todo', '{}'
        )
        """
    )
    payload = {
        "extractor_version": "0.1.0",
        "commit": "abc123",
        "rcept_no": "R100",
        "dcm_no": "D100",
        "extraction": {
            "company_name": {"status": "found", "value": "골드주식회사"},
            "opinion": {"status": "found", "value": "적정"},
            "going_concern": {"status": "found", "value": 0},
        },
    }
    conn.execute(
        """
        INSERT INTO extractor_snapshots (
            extractor_version, rcept_no, dcm_no, payload, captured_at
        ) VALUES ('0.1.0', 'R100', 'D100', ?, '2026-11-06T00:00:00+00:00')
        """,
        (json.dumps(payload, ensure_ascii=False),),
    )
    conn.commit()
    conn.close()
    return ReviewApplication(catalog, gold_path, cache)


def _write_cache(tmp_path: Path, page: str) -> None:
    folder = tmp_path / "cache" / "R100"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "main.html").write_text(page, encoding="utf-8")


def _post(
    app: ReviewApplication,
    path: str,
    fields: dict[str, str],
    host: str = "localhost:80",
) -> tuple[str, dict[str, str], bytes]:
    document = "/" + "/".join(path.strip("/").split("/")[:3])
    _status, _headers, page = _request(app, "GET", document)
    match = re.search(r'name="token" value="([^"]*)"', page.decode())
    assert match is not None
    payload = dict(fields)
    payload["token"] = match.group(1)
    raw = urlencode(payload).encode("utf-8")
    environ = {
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "REQUEST_METHOD": "POST",
        "CONTENT_TYPE": "application/x-www-form-urlencoded",
        "CONTENT_LENGTH": str(len(raw)),
        "HTTP_HOST": host,
        "SERVER_PORT": "80",
    }
    setup_testing_defaults(environ)
    environ["REQUEST_METHOD"] = "POST"
    environ["CONTENT_TYPE"] = "application/x-www-form-urlencoded"
    environ["CONTENT_LENGTH"] = str(len(raw))
    environ["HTTP_HOST"] = host
    environ["SERVER_PORT"] = "80"
    environ["wsgi.input"] = io.BytesIO(raw)
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]], exc_info=None) -> None:
        del exc_info
        captured["status"] = status
        captured["headers"] = {key: value for key, value in headers}

    body = b"".join(app(environ, start_response))
    return str(captured["status"]), dict(captured["headers"]), body


def _capture(tmp_path: Path, bundle: str, subject: str) -> sqlite3.Row | None:
    conn = sqlite3.connect(tmp_path / "gold.db")
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT bundle, subject, status, value, evidence
        FROM gold_captures
        WHERE rcept_no = ? AND dcm_no = ? AND bundle = ? AND subject = ?
        """,
        ("R100", "D100", bundle, subject),
    ).fetchone()
    conn.close()
    return row


def test_document_page_is_capture_without_an_iframe(tmp_path: Path) -> None:
    app = _build(tmp_path)
    _write_cache(
        tmp_path,
        "<script>alert(1)</script><iframe src=\"x\"></iframe><td id=\"n\">19,506</td>",
    )
    _status, _headers, body = _request(app, "GET", "/doc/R100/D100")
    page = body.decode()
    assert "<iframe" not in page.lower()
    assert "alert(1)" not in page
    assert "19,506" in page
    assert "자산총계 · 당기" in page
    assert "R100" in page and "D100" in page
    assert 'name="verdict"' not in page
    assert "event.preventDefault()" in page
    assert page.count('<select name="unit_scale"><option value="" selected></option>') == 2
    app.close()


def test_click_saves_when_a_row_and_unit_are_chosen(tmp_path: Path) -> None:
    app = _build(tmp_path)
    _post(app, "/doc/R100/D100/unit", {"unit_group": "bs", "unit_scale": "1000000"})
    status, _headers, _body = _post(
        app,
        "/doc/R100/D100/capture",
        {
            "bundle": "accounts",
            "subject": "total_asset@current",
            "text": "19,506",
        },
    )
    assert status.startswith("303")
    row = _capture(tmp_path, "accounts", "total_asset@current")
    assert json.loads(row["value"])["unit_scale"] == 1_000_000
    missed, headers, _body = _post(
        app,
        "/doc/R100/D100/capture",
        {"bundle": "accounts", "subject": "current_asset@current", "text": "없음"},
    )
    assert missed.startswith("303")
    assert "miss_subject=current_asset%40current" in headers["Location"]
    assert _capture(tmp_path, "accounts", "current_asset@current") is None
    location = headers["Location"]
    path, _, query = location.partition("?")
    _status, _headers, again = _request(app, "GET", path, query)
    assert "읽을 수 없습니다" in again.decode()
    app.close()


def test_unusable_unit_scale_is_a_bad_request(tmp_path: Path) -> None:
    app = _build(tmp_path)
    blank, _headers, _body = _post(
        app,
        "/doc/R100/D100/unit",
        {"unit_group": "bs", "unit_scale": ""},
    )
    assert blank.startswith("400")
    bad, _headers, _body = _post(
        app,
        "/doc/R100/D100/unit",
        {"unit_group": "bs", "unit_scale": "²"},
    )
    assert bad.startswith("400")
    conn = sqlite3.connect(tmp_path / "gold.db")
    count = conn.execute("SELECT count(*) FROM gold_capture_units").fetchone()[0]
    conn.close()
    assert count == 0
    app.close()


def test_absent_clear_and_rejected_requests(tmp_path: Path) -> None:
    app = _build(tmp_path)
    _post(
        app,
        "/doc/R100/D100/capture",
        {"bundle": "subsidiary", "subject": "value", "status": "not_applicable"},
    )
    assert _capture(tmp_path, "subsidiary", "value")["status"] == "not_applicable"
    _post(
        app,
        "/doc/R100/D100/capture",
        {"bundle": "subsidiary", "subject": "value", "status": "clear"},
    )
    assert _capture(tmp_path, "subsidiary", "value") is None
    host, _headers, host_body = _post(
        app,
        "/doc/R100/D100/capture",
        {"bundle": "company_name", "subject": "value", "text": "가나다"},
        host="evil.test:80",
    )
    assert host.startswith("403")
    assert app.token not in host_body.decode()
    bad, _headers, _body = _post(
        app,
        "/doc/R100/D100/capture",
        {"bundle": "accounts", "subject": "table", "text": "1"},
    )
    assert bad.startswith("400")
    missing, _headers, _body = _request(app, "GET", "/doc/R100/D100/source")
    assert missing.startswith("404")
    app.close()
