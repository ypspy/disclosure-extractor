"""입수 화면. 클릭과 상태 버튼이 gold_captures에 남는다."""

from __future__ import annotations

import io
import json
import re
import socket
import sqlite3
import urllib.request
from pathlib import Path
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

import pytest

from dart_parser.gold.app import ReviewApplication
from dart_parser.gold.capture import capture_rows
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


def test_desk_is_a_reading_room_with_ten_sections(tmp_path: Path) -> None:
    app = _build(tmp_path)
    _status, _headers, body = _request(app, "GET", "/doc/R100/D100")
    page = body.decode()
    for name in (
        "표지",
        "의견",
        "재무상태표",
        "손익계산서",
        "주석 목차",
        "감사시간",
        "실시내용",
        "커뮤니케이션",
        "내부회계",
        "종속기업",
    ):
        assert f'data-section="{name}"' in page
    assert page.count("<section ") == 10
    assert 'id="sections"' in page
    assert 'id="confirm"' in page
    assert "--mark:#e7b008" in page.replace(" ", "")
    assert "--bar:#243028" in page.replace(" ", "")
    assert "fonts.googleapis.com" not in page
    assert "<iframe" not in page.lower()
    data = json.loads(
        re.search(r'id="capture-data"[^>]*>(.*?)</script>', page, re.DOTALL).group(1)
    )
    assert data["previewUrl"] == "/doc/R100/D100/preview"
    assert data["sections"]["손익계산서"] == ["손익계산서", "포괄손익계산서"]
    assert data["sections"]["표지"] == []
    app.close()


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
    assert '<script src="/static/capture.js">' in page
    assert "function (" not in page
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
            "confirmed": json.dumps(19506),
        },
    )
    assert status.startswith("303")
    row = _capture(tmp_path, "accounts", "total_asset@current")
    assert json.loads(row["value"])["unit_scale"] == 1_000_000
    missed, headers, _body = _post(
        app,
        "/doc/R100/D100/capture",
        {
            "bundle": "accounts",
            "subject": "current_asset@current",
            "text": "없음",
            "confirmed": json.dumps("없음"),
        },
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
        {
            "bundle": "company_name",
            "subject": "value",
            "text": "가나다",
            "confirmed": json.dumps("가나다"),
        },
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


def test_html_responses_send_a_content_security_policy(tmp_path: Path) -> None:
    app = _build(tmp_path)
    _status, headers, body = _request(app, "GET", "/doc/R100/D100")
    policy = headers["Content-Security-Policy"]
    assert "default-src 'none'" in policy
    assert "script-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy
    assert headers["Referrer-Policy"] == "no-referrer"
    page = body.decode()
    assert '<script src="/static/capture.js">' in page
    assert "function (" not in page
    status, script_headers, script = _request(app, "GET", "/static/capture.js")
    assert status == "200 OK"
    assert script_headers["Content-Type"] == "text/javascript"
    assert script_headers["X-Content-Type-Options"] == "nosniff"
    assert b"event.preventDefault()" in script
    missing, _headers, _body = _request(app, "GET", "/static/other.js")
    assert missing.startswith("404")
    app.close()


def test_pages_do_not_download_sample_or_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args, **_kwargs):
        raise AssertionError("network or sampling")

    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setattr("dart_parser.gold.sampler.build_sample", boom)
    monkeypatch.setattr("dart_parser.gold.sampler.oversample", boom)
    monkeypatch.setattr("dart_parser.gold.snapshots.capture", boom)
    app = _build(tmp_path)
    list_status, _headers, _body = _request(app, "GET", "/")
    doc_status, _headers, _body = _request(app, "GET", "/doc/R100/D100")
    post_status, _headers, _body = _post(
        app,
        "/doc/R100/D100/capture",
        {
            "bundle": "company_name",
            "subject": "value",
            "text": "가나",
            "confirmed": json.dumps("가나"),
        },
    )
    assert list_status == "200 OK"
    assert doc_status == "200 OK"
    assert post_status.startswith("303")
    assert not (tmp_path / "cache" / "R100").exists()
    app.close()


def test_missing_cache_is_marked_and_not_downloaded(tmp_path: Path) -> None:
    app = _build(tmp_path)
    status, _headers, body = _request(app, "GET", "/doc/R100/D100")
    page = body.decode()
    assert status == "200 OK"
    assert 'id="cache-missing"' in page
    assert not (tmp_path / "cache" / "R100").exists()
    app.close()


def test_encoding_and_ambiguous_document_warnings(tmp_path: Path) -> None:
    app = _build(tmp_path)
    folder = tmp_path / "cache" / "R100"
    folder.mkdir(parents=True)
    (folder / "main.html").write_bytes(b"\xff\xfe<p>\xb0\xa1</p>")
    (folder / "toc.json").write_text("{}", encoding="utf-8")
    _status, _headers, body = _request(app, "GET", "/doc/R100/D100")
    page = body.decode()
    assert 'id="encoding-check"' in page
    assert 'id="dcm-warning"' not in page
    conn = sqlite3.connect(tmp_path / "gold.db")
    conn.execute(
        """
        INSERT INTO gold_samples (
            run_id, rcept_no, dcm_no, period, stratum, stratum_weight, sample_hash,
            mode, role, queue_order, status, meta
        ) VALUES (
            'run', 'R100', 'D200', 'P7', 'listed', 1, 'h2', 'prefill', 'main', 2, 'todo', '{}'
        )
        """
    )
    conn.commit()
    conn.close()
    _status, _headers, warned = _request(app, "GET", "/doc/R100/D100")
    assert 'id="dcm-warning"' in warned.decode()
    status, _headers, _body = _post(
        app,
        "/doc/R100/D100/capture",
        {
            "bundle": "company_name",
            "subject": "value",
            "text": "가나",
            "confirmed": json.dumps("가나"),
        },
    )
    assert status.startswith("409")
    unit, _headers, _body = _post(
        app, "/doc/R100/D100/unit", {"unit_group": "bs", "unit_scale": "1"}
    )
    assert unit.startswith("409")
    done, _headers, _body = _post(app, "/doc/R100/D100/complete", {})
    assert done.startswith("409")
    conn = sqlite3.connect(tmp_path / "gold.db")
    assert conn.execute("SELECT count(*) FROM gold_captures").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM gold_capture_units").fetchone()[0] == 0
    assert conn.execute(
        "SELECT status FROM gold_samples WHERE dcm_no = 'D100'"
    ).fetchone()[0] == "todo"
    conn.close()
    app.close()


def test_full_filing_is_shown_without_the_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args, **_kwargs):
        raise AssertionError("evidence")

    monkeypatch.setattr("dart_parser.gold.evidence.evidence_for", boom)
    app = _build(tmp_path)
    folder = tmp_path / "cache" / "R100"
    folder.mkdir(parents=True)
    (folder / "main.html").write_text(
        "<h2>주석</h2><p>표지 밖 고유문장</p>", encoding="utf-8"
    )
    _status, _headers, body = _request(app, "GET", "/doc/R100/D100")
    page = body.decode()
    assert "표지 밖 고유문장" in page
    assert "골드주식회사" not in page
    assert "0.1.0" not in page
    assert "abc123" not in page
    assert 'id="filing-toc"' in page
    assert "주석" in page
    assert "data-scroll=" in page
    app.close()


def test_complete_lists_missing_rows_then_marks_done(tmp_path: Path) -> None:
    app = _build(tmp_path)
    status, _headers, body = _post(app, "/doc/R100/D100/complete", {})
    assert status.startswith("400")
    page = body.decode()
    assert 'id="missing-rows"' in page
    assert "회사명" in page
    conn = sqlite3.connect(tmp_path / "gold.db")
    for row in capture_rows():
        conn.execute(
            """
            INSERT INTO gold_captures (
                rcept_no, dcm_no, bundle, subject, status, value, evidence, updated_at
            ) VALUES ('R100', 'D100', ?, ?, 'not_applicable', NULL, '', 't')
            """,
            (row.bundle, row.subject),
        )
    conn.commit()
    conn.close()
    done, _headers, _body = _post(app, "/doc/R100/D100/complete", {})
    assert done.startswith("303")
    conn = sqlite3.connect(tmp_path / "gold.db")
    row = conn.execute(
        "SELECT status, finished_at FROM gold_samples WHERE dcm_no = 'D100'"
    ).fetchone()
    assert row[0] == "done"
    assert row[1]
    conn.close()
    app.close()


def test_next_resumes_in_progress_without_writing(tmp_path: Path) -> None:
    app = _build(tmp_path)
    conn = sqlite3.connect(tmp_path / "gold.db")
    conn.execute(
        """
        INSERT INTO gold_samples (
            run_id, rcept_no, dcm_no, period, stratum, stratum_weight, sample_hash,
            mode, role, queue_order, status, meta
        ) VALUES
            ('run', 'R200', 'D200', 'P7', 'listed', 1, 'h2', 'prefill', 'main', 0, 'todo', '{}'),
            ('run', 'R300', 'D300', 'P7', 'listed', 1, 'h3', 'prefill', 'main', 2,
             'in_progress', '{}'),
            ('run', 'R400', 'D400', 'P7', 'listed', 1, 'h4', 'prefill', 'reserve', 3, 'todo', '{}'),
            ('run', 'R500', 'D500', 'P7', 'listed', 1, 'h5', 'prefill', 'main', 4, 'done', '{}')
        """
    )
    conn.commit()
    before = conn.execute(
        "SELECT rcept_no, status, started_at FROM gold_samples ORDER BY rcept_no"
    ).fetchall()
    conn.close()
    status, headers, _body = _request(app, "GET", "/next", "period=P7")
    assert status.startswith("303")
    assert headers["Location"] == "/doc/R300/D300"
    conn = sqlite3.connect(tmp_path / "gold.db")
    after = conn.execute(
        "SELECT rcept_no, status, started_at FROM gold_samples ORDER BY rcept_no"
    ).fetchall()
    conn.close()
    assert after == before
    app.close()


def test_first_capture_marks_the_sample_in_progress(tmp_path: Path) -> None:
    app = _build(tmp_path)
    _post(
        app,
        "/doc/R100/D100/capture",
        {
            "bundle": "company_name",
            "subject": "value",
            "text": "가나",
            "confirmed": json.dumps("가나"),
        },
    )
    conn = sqlite3.connect(tmp_path / "gold.db")
    status, started = conn.execute(
        "SELECT status, started_at FROM gold_samples WHERE dcm_no = 'D100'"
    ).fetchone()
    assert status == "in_progress"
    assert started
    _post(
        app,
        "/doc/R100/D100/capture",
        {
            "bundle": "company_name",
            "subject": "value",
            "text": "다라",
            "confirmed": json.dumps("다라"),
        },
    )
    again = conn.execute(
        "SELECT started_at FROM gold_samples WHERE dcm_no = 'D100'"
    ).fetchone()[0]
    conn.close()
    assert again == started
    app.close()


def _submit(
    app: ReviewApplication,
    path: str,
    fields: dict[str, str],
    host: str = "localhost:80",
) -> tuple[str, dict[str, str], bytes]:
    payload = dict(fields)
    payload["token"] = app.token
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


def _sample_status(tmp_path: Path) -> tuple[str, str | None]:
    conn = sqlite3.connect(tmp_path / "gold.db")
    row = conn.execute(
        "SELECT status, finished_at FROM gold_samples WHERE dcm_no = 'D100'"
    ).fetchone()
    conn.close()
    return str(row[0]), row[1]


def test_each_saved_line_has_a_remove_button(tmp_path: Path) -> None:
    app = _build(tmp_path)
    _post(
        app,
        "/doc/R100/D100/capture",
        {
            "bundle": "notes_toc",
            "subject": "value",
            "text": "일반사항",
            "confirmed": json.dumps("일반사항"),
        },
    )
    _post(
        app,
        "/doc/R100/D100/capture",
        {
            "bundle": "notes_toc",
            "subject": "value",
            "text": "재고자산",
            "confirmed": json.dumps("재고자산"),
        },
    )
    _post(
        app,
        "/doc/R100/D100/capture",
        {
            "bundle": "communications",
            "subject": "items",
            "text": "2017년 3월 2일 회의",
            "confirmed": json.dumps({"raw": "2017년 3월 2일 회의", "date": "2017-03-02"}),
        },
    )
    _post(
        app,
        "/doc/R100/D100/capture",
        {
            "bundle": "communications",
            "subject": "items",
            "text": "둘째 회의",
            "confirmed": json.dumps({"raw": "둘째 회의"}),
        },
    )
    _status, _headers, body = _request(app, "GET", "/doc/R100/D100")
    page = body.decode()
    assert page.count('name="status" value="remove_title"') == 2
    assert page.count('name="status" value="remove_item"') == 2
    assert page.count(f'name="token" value="{app.token}"') >= 2
    assert set(re.findall(r'name="token" value="([^"]*)"', page)) == {app.token}
    assert 'name="index" value="0"' in page
    assert 'name="index" value="1"' in page
    removed, _headers, _body = _post(
        app,
        "/doc/R100/D100/capture",
        {
            "bundle": "notes_toc",
            "subject": "value",
            "status": "remove_title",
            "index": "0",
        },
    )
    assert removed.startswith("303")
    conn = sqlite3.connect(tmp_path / "gold.db")
    notes = json.loads(
        conn.execute(
            "SELECT value FROM gold_captures WHERE bundle = 'notes_toc'"
        ).fetchone()[0]
    )
    assert notes["titles"] == ["재고자산"]
    history = conn.execute(
        """
        SELECT value, action FROM gold_capture_history
        WHERE bundle = 'notes_toc'
        ORDER BY rowid
        """
    ).fetchall()
    assert json.loads(history[-1][0])["titles"] == ["일반사항", "재고자산"]
    assert history[-1][1] == "update"
    dropped, _headers, _body = _post(
        app,
        "/doc/R100/D100/capture",
        {
            "bundle": "communications",
            "subject": "items",
            "status": "remove_item",
            "index": "0",
        },
    )
    assert dropped.startswith("303")
    items = json.loads(
        conn.execute(
            "SELECT value FROM gold_captures WHERE bundle = 'communications'"
        ).fetchone()[0]
    )
    assert [item["raw"] for item in items] == ["둘째 회의"]
    rounds = conn.execute(
        """
        SELECT value, action FROM gold_capture_history
        WHERE bundle = 'communications' AND subject = 'items'
        ORDER BY rowid
        """
    ).fetchall()
    assert json.loads(rounds[-1][0])[0]["raw"] == "2017년 3월 2일 회의"
    assert rounds[-1][1] == "update"
    conn.close()
    _status, _headers, again = _request(app, "GET", "/doc/R100/D100")
    shown = again.decode()
    assert "일반사항" not in shown
    assert "재고자산" in shown
    assert "2017년 3월 2일 회의" not in shown
    assert "둘째 회의" in shown
    assert shown.count('name="status" value="remove_title"') == 1
    assert shown.count('name="status" value="remove_item"') == 1
    app.close()


def test_non_decimal_remove_index_is_a_bad_request(tmp_path: Path) -> None:
    app = _build(tmp_path)
    status, _headers, _body = _post(
        app,
        "/doc/R100/D100/capture",
        {
            "bundle": "notes_toc",
            "subject": "value",
            "status": "remove_title",
            "index": "²",
        },
    )
    assert status.startswith("400")
    app.close()


def test_done_document_reopens_when_a_cell_is_cleared_or_its_status_changes(
    tmp_path: Path,
) -> None:
    app = _build(tmp_path)
    conn = sqlite3.connect(tmp_path / "gold.db")
    for row in capture_rows():
        conn.execute(
            """
            INSERT INTO gold_captures (
                rcept_no, dcm_no, bundle, subject, status, value, evidence, updated_at
            ) VALUES ('R100', 'D100', ?, ?, 'not_applicable', NULL, '', 't')
            """,
            (row.bundle, row.subject),
        )
    conn.execute(
        """
        UPDATE gold_samples
        SET status = 'done', finished_at = '2026-11-11T00:00:00+00:00'
        WHERE dcm_no = 'D100'
        """
    )
    conn.commit()
    conn.close()
    cleared, _headers, _body = _post(
        app,
        "/doc/R100/D100/capture",
        {"bundle": "company_name", "subject": "value", "status": "clear"},
    )
    assert cleared.startswith("303")
    assert _sample_status(tmp_path) == ("in_progress", None)
    conn = sqlite3.connect(tmp_path / "gold.db")
    conn.execute(
        """
        UPDATE gold_samples
        SET status = 'done', finished_at = '2026-11-11T00:00:00+00:00'
        WHERE dcm_no = 'D100'
        """
    )
    conn.commit()
    conn.close()
    changed, _headers, _body = _post(
        app,
        "/doc/R100/D100/capture",
        {"bundle": "opinion", "subject": "value", "status": "not_in_regime"},
    )
    assert changed.startswith("303")
    assert _sample_status(tmp_path) == ("in_progress", None)
    app.close()


def test_post_checks_ambiguity_without_loading_the_filing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = _build(tmp_path)

    def boom(*_args, **_kwargs):
        raise AssertionError("load_disclosure")

    monkeypatch.setattr(app.store, "load_disclosure", boom)
    saved, _headers, _body = _submit(
        app,
        "/doc/R100/D100/capture",
        {
            "bundle": "company_name",
            "subject": "value",
            "text": "가나",
            "confirmed": json.dumps("가나"),
        },
    )
    assert saved.startswith("303")
    unit, _headers, _body = _submit(
        app, "/doc/R100/D100/unit", {"unit_group": "bs", "unit_scale": "1"}
    )
    assert unit.startswith("303")
    done, _headers, _body = _submit(app, "/doc/R100/D100/complete", {})
    assert done.startswith("400")
    app.close()


def test_toc_ids_missing_from_html_use_heading_titles(tmp_path: Path) -> None:
    app = _build(tmp_path)
    folder = tmp_path / "cache" / "R100"
    folder.mkdir(parents=True)
    (folder / "main.html").write_text(
        '<h2 id="keep-me">고유헤더</h2><p>본문</p>', encoding="utf-8"
    )
    (folder / "toc.json").write_text(
        json.dumps(
            [
                {"id": "keep-me", "title": "있는제목"},
                {"id": "missing-id", "title": "없는목차"},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _status, _headers, body = _request(app, "GET", "/doc/R100/D100")
    page = body.decode()
    assert "없는목차" not in page
    assert "있는제목" not in page
    assert "고유헤더" in page
    assert 'data-scroll="keep-me"' in page
    (folder / "toc.json").write_text(
        json.dumps([{"id": "keep-me", "title": "캐시목차"}], ensure_ascii=False),
        encoding="utf-8",
    )
    _status, _headers, kept = _request(app, "GET", "/doc/R100/D100")
    shown = kept.decode()
    assert 'data-scroll="keep-me"' in shown
    assert "캐시목차" in shown
    app.close()


def test_going_concern_rule_is_on_the_row(tmp_path: Path) -> None:
    app = _build(tmp_path)
    _status, _headers, body = _request(app, "GET", "/doc/R100/D100")
    page = body.decode()
    assert "의견 근거만 있거나, 전기 인용만 있거나, 청산기준 강조만 있으면 0입니다." in page
    assert 'id="doc-progress">기록 0/' in page
    assert 'id="period-progress">완료 0/1' in page
    app.close()


def test_preview_proposes_a_value_without_writing(tmp_path: Path) -> None:
    app = _build(tmp_path)
    before = _request(app, "GET", "/doc/R100/D100")
    status, headers, body = _post(
        app,
        "/doc/R100/D100/preview",
        {"bundle": "opinion", "subject": "value", "text": "한정의견을 표명합니다"},
    )
    assert status.startswith("200")
    assert headers["Content-Type"].startswith("application/json")
    payload = json.loads(body)
    assert payload["proposal"] == "한정"
    assert payload["kind"] == "enum"
    assert payload["blocked"] == ""
    assert ("한정",) in [(item["value"],) for item in payload["options"]]
    after = _request(app, "GET", "/doc/R100/D100")
    assert before[2] == after[2]
    app.close()


def test_capture_without_confirmed_does_not_write(tmp_path: Path) -> None:
    app = _build(tmp_path)
    status, headers, _body = _post(
        app,
        "/doc/R100/D100/capture",
        {"bundle": "company_name", "subject": "value", "text": "가나"},
    )
    assert status.startswith("303")
    assert "miss_subject=value" in headers["Location"]
    assert _capture(tmp_path, "company_name", "value") is None
    app.close()


def test_capture_script_drags_and_confirms(tmp_path: Path) -> None:
    app = _build(tmp_path)
    _status, _headers, body = _request(app, "GET", "/static/capture.js")
    script = body.decode()
    assert "getSelection" in script
    assert "previewUrl" in script
    assert "confirmed" in script
    assert "event.target.textContent" not in script
    assert "fonts.googleapis.com" not in script
    assert 'addEventListener("change"' in script
    assert "켜진 칸이 없다" in script
    assert "드래그 글자가 비어 있다" in script
    assert "response.text()" in script.split("confirm-save", 1)[1]
    save = script.split('getElementById("confirm-save")', 1)[1].split(
        'getElementById("confirm-cancel")', 1
    )[0]
    assert "miss_bundle=" in save
    assert "miss_subject=" in save
    assert 'showReason("읽을 수 없습니다.")' in save
    assert "showRejection" not in save
    assert "pending = null" not in save
    assert save.index("miss_bundle=") < save.index("window.location.assign(response.url)")
    assert save.index("sessionStorage.setItem") < save.index(
        "window.location.assign(response.url)"
    )
    assert "response.text()" in save
    boot = script.split('root.addEventListener("click"', 1)[0]
    assert 'sessionStorage.getItem("gold-open-section")' in boot
    assert 'sessionStorage.removeItem("gold-open-section")' in boot
    assert "restoreOpenSection()" in boot
    assert 'setAttribute("data-active", "1")' in boot
    assert 'removeAttribute("data-active")' in boot
    assert 'setAttribute("aria-pressed"' in boot
    assert "hideBar()" not in boot
    assert ".checked" not in boot
    preview = script.split("confirm-save", 1)[0]
    before_pending = preview.split("response.text()", 1)[1].split("pending =", 1)[0]
    assert "requestToken !== previewToken" in before_pending
    assert before_pending.index("requestToken !== previewToken") < before_pending.index("return")
    assert 'a[data-scroll]' in script
    toc = script.split('a[data-scroll]', 1)[1]
    assert "data-scroll" in toc
    assert "scrollIntoView" in toc
    assert toc.index("preventDefault()") < toc.index("getElementById")
    app.close()


def _request_host(
    app: ReviewApplication,
    path: str,
    host: str,
    port: str = "80",
) -> tuple[str, dict[str, str], bytes]:
    environ = {"PATH_INFO": path, "QUERY_STRING": "", "REQUEST_METHOD": "GET"}
    setup_testing_defaults(environ)
    environ["HTTP_HOST"] = host
    environ["SERVER_PORT"] = port
    environ["wsgi.input"] = io.BytesIO()
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]], exc_info=None) -> None:
        del exc_info
        captured["status"] = status
        captured["headers"] = {key: value for key, value in headers}

    body = b"".join(app(environ, start_response))
    return str(captured["status"]), dict(captured["headers"]), body


def _post_json(
    app: ReviewApplication,
    path: str,
    fields: dict[str, str],
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
        "HTTP_HOST": "localhost:80",
        "SERVER_PORT": "80",
        "HTTP_ACCEPT": "application/json",
    }
    setup_testing_defaults(environ)
    environ["REQUEST_METHOD"] = "POST"
    environ["CONTENT_TYPE"] = "application/x-www-form-urlencoded"
    environ["CONTENT_LENGTH"] = str(len(raw))
    environ["HTTP_HOST"] = "localhost:80"
    environ["SERVER_PORT"] = "80"
    environ["HTTP_ACCEPT"] = "application/json"
    environ["wsgi.input"] = io.BytesIO(raw)
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]], exc_info=None) -> None:
        del exc_info
        captured["status"] = status
        captured["headers"] = {key: value for key, value in headers}

    body = b"".join(app(environ, start_response))
    return str(captured["status"]), dict(captured["headers"]), body


def test_desk_splits_the_filing_and_keeps_host_styles_outside(tmp_path: Path) -> None:
    app = _build(tmp_path)
    _status, headers, body = _request(app, "GET", "/doc/R100/D100")
    page = body.decode()
    compact = page.replace(" ", "")
    assert "--split:60%" in compact
    assert "position:sticky" in compact
    assert 'id="pane-resizer"' in page
    assert 'role="separator"' in page
    assert 'id="export-json"' in page
    assert 'href="/doc/R100/D100/export"' in page
    assert "JSON Export" in page
    assert 'id="auto-advance"' in page
    assert 'id="field-picker"' in page
    assert "<iframe" not in page.lower()
    assert "onclick=" not in page
    assert "function (" not in page
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    filing = page.split('id="filing"', 1)[1].split("</div>", 1)[0]
    assert "<style" not in filing
    style = page.split("<style>", 1)[1].split("</style>", 1)[0]
    assert "gold-source" not in style
    assert "gold-snap" not in style
    assert 'id="doc-progress"' in page
    script_status, _script_headers, script_body = _request(app, "GET", "/static/capture.js")
    assert script_status == "200 OK"
    script = script_body.decode()
    assert "attachShadow" in script
    assert 'root.innerHTML = "<style>' in script
    assert "gold-source" in script
    assert "::selection{background:#e7b008}" in script
    assert "normalizeText" in script
    assert 'closest("td, th, p")' in script
    assert "isCollapsed" in script
    assert "cell_click" in script
    assert "text_drag" in script
    assert "manual_edit" in script
    assert '"Accept": "application/json"' in script
    assert "proposalConfirmed" in script
    assert "payload.blocked" in script
    assert "gold-auto-advance" in script
    assert "nextEmpty" in script
    assert "sessionStorage.setItem(autoKey" in script
    assert "scrollToLocator" in script
    assert "scrollIntoView" in script
    assert "css_selector" in script
    assert "start_offset" in script
    assert "end_offset" in script
    assert "xpath" in script
    assert "field-picker" in script
    assert "켜진 칸이 없다" in script
    assert "undoStack" in script
    assert "ctrlKey" in script
    assert "metaKey" in script
    assert "selection_method" in script
    assert "exportUrl" in script
    assert "gold-split" in script
    app.close()


def test_export_lists_saved_rows_without_writing(tmp_path: Path) -> None:
    app = _build(tmp_path)
    empty_status, empty_headers, empty_body = _request(app, "GET", "/doc/R100/D100/export")
    assert empty_status == "200 OK"
    assert empty_headers["Content-Type"].startswith("application/json")
    assert json.loads(empty_body) == []
    _post(
        app,
        "/doc/R100/D100/capture",
        {
            "bundle": "company_name",
            "subject": "value",
            "text": "가나회사",
            "confirmed": json.dumps("가나회사"),
        },
    )
    conn = sqlite3.connect(tmp_path / "gold.db")
    before = conn.execute(
        "SELECT bundle, subject, status, value, evidence FROM gold_captures"
    ).fetchall()
    conn.close()
    status, headers, body = _request(app, "GET", "/doc/R100/D100/export")
    assert status == "200 OK"
    assert headers["Content-Type"].startswith("application/json")
    assert "attachment;" in headers["Content-Disposition"]
    rows = json.loads(body)
    assert len(rows) == 1
    assert rows[0]["doc_id"] == "R100/D100"
    assert rows[0]["field_key"] == "company_name/value"
    assert rows[0]["extracted_value"] == "가나회사"
    assert rows[0]["raw_text"] == "가나회사"
    assert rows[0]["locator"] is None
    assert rows[0]["selection_method"] is None
    conn = sqlite3.connect(tmp_path / "gold.db")
    after = conn.execute(
        "SELECT bundle, subject, status, value, evidence FROM gold_captures"
    ).fetchall()
    conn.close()
    assert after == before
    foreign, _headers, foreign_body = _request_host(app, "/doc/R100/D100/export", "evil.test:80")
    assert foreign.startswith("403")
    assert "가나회사".encode() not in foreign_body
    posted, _headers, _body = _request(app, "POST", "/doc/R100/D100/export")
    assert posted.startswith("405")
    app.close()


def test_json_accept_saves_in_place_and_still_requires_confirmed(tmp_path: Path) -> None:
    app = _build(tmp_path)
    status, headers, body = _post_json(
        app,
        "/doc/R100/D100/capture",
        {
            "bundle": "company_name",
            "subject": "value",
            "text": "가나회사",
            "confirmed": json.dumps("가나회사"),
        },
    )
    assert status.startswith("200")
    assert headers["Content-Type"].startswith("application/json")
    assert "Location" not in headers
    payload = json.loads(body)
    assert payload["ok"] is True
    assert payload["shown"] == "가나회사"
    assert payload["replay"] == "가나회사"
    assert payload["cleared"] is False
    assert payload["recorded"] == 1
    saved = _capture(tmp_path, "company_name", "value")
    assert saved is not None
    assert json.loads(saved["value"]) == "가나회사"
    rejected, _headers, rejected_body = _post_json(
        app,
        "/doc/R100/D100/capture",
        {"bundle": "auditor", "subject": "value", "text": "삼일"},
    )
    assert rejected.startswith("422")
    assert json.loads(rejected_body)["ok"] is False
    assert _capture(tmp_path, "auditor", "value") is None
    assert json.loads(_capture(tmp_path, "company_name", "value")["value"]) == "가나회사"
    app.close()


def _capture_json_data(page: str) -> dict[str, object]:
    raw = page.split('id="capture-data"', 1)[1]
    raw = raw.split(">", 1)[1].split("</script>", 1)[0]
    loaded = json.loads(raw)
    assert isinstance(loaded, dict)
    return loaded


def _js_function(script: str, name: str) -> str:
    marker = f"function {name}"
    start = script.index(marker)
    rest = script[start + len(marker) :]
    nxt = rest.find("\n  function ")
    return rest if nxt < 0 else rest[:nxt]


def test_document_capture_data_names_pass_one(tmp_path: Path) -> None:
    app = _build(tmp_path)
    status, _headers, body = _request(app, "GET", "/doc/R100/D100")
    assert status == "200 OK"
    data = _capture_json_data(body.decode())
    assert data["pass"] == 1
    assert data["base"] == "doc"
    app.close()


def test_capture_script_scopes_storage_and_restores_lists_after_ok(tmp_path: Path) -> None:
    app = _build(tmp_path)
    status, _headers, body = _request(app, "GET", "/static/capture.js")
    assert status == "200 OK"
    script = body.decode()
    assert 'var mapKey = "gold-field-map:" + (data.docId || "");' not in script
    assert 'var undoKey = "gold-undo:" + (data.docId || "");' not in script
    map_line = next(line for line in script.splitlines() if "gold-field-map:" in line)
    undo_line = next(line for line in script.splitlines() if "gold-undo:" in line)
    assert "data.docId" in map_line
    assert "data.pass" in map_line or "data.base" in map_line
    assert "data.docId" in undo_line
    assert "data.pass" in undo_line or "data.base" in undo_line
    undo = _js_function(script, "undoLast")
    assert "undoStack.pop()" not in undo
    assert "sessionStorage.setItem(undoKey" not in undo
    assert "undoBusy" in undo
    assert "commitUndo()" in undo
    assert undo.index("if (!ok)") < undo.index("commitUndo()")
    commit = _js_function(script, "commitUndo")
    assert "undoStack.pop()" in commit
    assert "undoKey" in commit
    restore = _js_function(script, "restoreList")
    assert "postRemove" in restore
    assert "current.length - 1" in restore
    assert "replayList" in restore
    replay = _js_function(script, "replayLines")
    assert "postCapture" in replay
    assert "lineConfirmed" in replay
    assert "postRemove(form, current.length - 1" not in replay
    app.close()


def test_portless_loopback_host_requires_server_port_80(tmp_path: Path) -> None:
    app = _build(tmp_path)
    saved = "호스트분리값"
    _post(
        app,
        "/doc/R100/D100/capture",
        {
            "bundle": "company_name",
            "subject": "value",
            "text": saved,
            "confirmed": json.dumps(saved),
        },
    )
    for host in ("127.0.0.1", "localhost", "127.0.0.1:80", "localhost:80"):
        status, _headers, body = _request_host(app, "/doc/R100/D100/export", host, "80")
        assert status == "200 OK", host
        assert saved.encode() in body
    for host in ("127.0.0.1", "localhost"):
        status, _headers, body = _request_host(app, "/doc/R100/D100/export", host, "8000")
        assert status.startswith("403"), host
        assert body == "요청을 거절했습니다.".encode()
        assert saved.encode() not in body
    for host in ("evil.test", "evil.test:80"):
        status, _headers, body = _request_host(app, "/doc/R100/D100/export", host, "80")
        assert status.startswith("403"), host
        assert saved.encode() not in body
    empty, _headers, empty_body = _request_host(app, "/doc/R100/D100/export", "127.0.0.1", "")
    assert empty.startswith("403")
    assert empty_body == "요청을 거절했습니다.".encode()
    assert saved.encode() not in empty_body
    bare_local, _headers, bare_body = _request_host(app, "/doc/R100/D100/export", "localhost", "")
    assert bare_local.startswith("403")
    assert saved.encode() not in bare_body
    app.close()
