"""재입수 화면. 1차 값은 숨기고, 2차 테이블만 바꾼다."""

from __future__ import annotations

import io
import json
import socket
import sqlite3
import urllib.request
from pathlib import Path
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

import pytest

from dart_parser.gold.capture import capture_rows
from dart_parser.gold.scoring import wilson
from test_gold_capture_app import _build, _post, _request


def _raw_post(
    app,
    path: str,
    fields: dict[str, str],
    *,
    host: str = "localhost:80",
    origin: str | None = None,
) -> tuple[str, dict[str, str], bytes]:
    raw = urlencode(fields).encode("utf-8")
    environ = {
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "REQUEST_METHOD": "POST",
        "CONTENT_TYPE": "application/x-www-form-urlencoded",
        "CONTENT_LENGTH": str(len(raw)),
        "HTTP_HOST": host,
        "SERVER_PORT": "80",
    }
    if origin is not None:
        environ["HTTP_ORIGIN"] = origin
    setup_testing_defaults(environ)
    environ["REQUEST_METHOD"] = "POST"
    environ["CONTENT_TYPE"] = "application/x-www-form-urlencoded"
    environ["CONTENT_LENGTH"] = str(len(raw))
    environ["HTTP_HOST"] = host
    environ["SERVER_PORT"] = "80"
    if origin is not None:
        environ["HTTP_ORIGIN"] = origin
    environ["wsgi.input"] = io.BytesIO(raw)
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]], exc_info=None) -> None:
        del exc_info
        captured["status"] = status
        captured["headers"] = {key: value for key, value in headers}

    body = b"".join(app(environ, start_response))
    return str(captured["status"]), dict(captured["headers"]), body


_FIRST_PASS_TABLES = (
    "SELECT * FROM gold_captures ORDER BY rcept_no, dcm_no, bundle, subject",
    "SELECT * FROM gold_samples ORDER BY run_id, rcept_no, dcm_no",
    "SELECT * FROM gold_capture_units ORDER BY rcept_no, dcm_no, unit_group",
    "SELECT * FROM gold_capture_history ORDER BY rowid",
)
_RECAPTURE_TABLES = (
    "SELECT * FROM gold_recaptures ORDER BY rcept_no, dcm_no, bundle, subject",
    "SELECT * FROM gold_recapture_units ORDER BY rcept_no, dcm_no, unit_group",
    "SELECT * FROM gold_recapture_history ORDER BY rowid",
    "SELECT * FROM gold_recapture_status ORDER BY run_id, rcept_no, dcm_no",
)


def _stored(path: Path, queries: tuple[str, ...]) -> tuple[list[tuple[object, ...]], ...]:
    conn = sqlite3.connect(path)
    try:
        return tuple([tuple(row) for row in conn.execute(query)] for query in queries)
    finally:
        conn.close()


def _open_status(conn: sqlite3.Connection, rcept: str = "R100", dcm: str = "D100") -> None:
    conn.execute(
        """
        INSERT INTO gold_recapture_status (
            run_id, rcept_no, dcm_no, status, started_at, finished_at
        ) VALUES ('run', ?, ?, 'in_progress', 't', NULL)
        """,
        (rcept, dcm),
    )


def test_ineligible_document_rejects_recapture_get_and_post(tmp_path: Path) -> None:
    app = _build(tmp_path)
    status, headers, body = _request(app, "GET", "/recapture/R100/D100")
    assert status.startswith("409")
    assert "재입수 대상이 아닙니다." in body.decode()
    assert "Content-Security-Policy" in headers
    posted, _headers, _posted_body = _raw_post(
        app,
        "/recapture/R100/D100/capture",
        {
            "token": app.token,
            "bundle": "company_name",
            "subject": "value",
            "text": "가나",
            "confirmed": json.dumps("가나"),
        },
    )
    assert posted.startswith("409")
    conn = sqlite3.connect(tmp_path / "gold.db")
    assert conn.execute("SELECT count(*) FROM gold_recaptures").fetchone()[0] == 0
    conn.close()
    app.close()


def test_recapture_page_hides_the_first_pass(tmp_path: Path) -> None:
    app = _build(tmp_path)
    conn = sqlite3.connect(tmp_path / "gold.db")
    conn.execute(
        """
        INSERT INTO gold_captures (
            rcept_no, dcm_no, bundle, subject, status, value, evidence, updated_at
        ) VALUES (
            'R100', 'D100', 'company_name', 'value', 'found', ?, 'PASS1-EVIDENCE-ZZ', 't'
        )
        """,
        (json.dumps("PASS1-VALUE-ZZ", ensure_ascii=False),),
    )
    conn.execute(
        """
        INSERT INTO gold_capture_units (rcept_no, dcm_no, unit_group, unit_scale)
        VALUES ('R100', 'D100', 'bs', 1000)
        """
    )
    conn.execute(
        """
        INSERT INTO gold_capture_history (
            rcept_no, dcm_no, bundle, subject, status, value, evidence,
            updated_at, action, superseded_at
        ) VALUES (
            'R100', 'D100', 'company_name', 'value', 'found', '"PASS1-HISTORY-ZZ"',
            'PASS1-EVIDENCE-ZZ', 't', 'update', 't'
        )
        """
    )
    _open_status(conn)
    conn.commit()
    conn.close()
    status, headers, body = _request(app, "GET", "/recapture/R100/D100")
    page = body.decode()
    assert status == "200 OK"
    assert "PASS1-VALUE-ZZ" not in page
    assert "PASS1-EVIDENCE-ZZ" not in page
    assert "PASS1-HISTORY-ZZ" not in page
    assert 'value="1000" selected' not in page
    assert 'action="/recapture/R100/D100/capture"' in page
    assert 'action="/recapture/R100/D100/unit"' in page
    assert 'action="/recapture/R100/D100/complete"' in page
    assert '"captureUrl": "/recapture/R100/D100/capture"' in page
    assert 'href="/recapture/next?period=P7"' in page
    assert 'id="period-progress">재입수 완료 0/1' in page
    assert "function (" not in page
    assert "onclick=" not in page
    assert '<script src="/static/capture.js">' in page
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    blocked, _blocked_headers, blocked_body = _request(app, "GET", "/doc/R100/D100")
    assert blocked.startswith("409")
    assert "재입수 중" in blocked_body.decode()
    assert b"PASS1-VALUE-ZZ" not in blocked_body
    assert b"PASS1-EVIDENCE-ZZ" not in blocked_body
    app.close()


def test_second_pass_write_does_not_touch_the_first_pass(tmp_path: Path) -> None:
    app = _build(tmp_path)
    conn = sqlite3.connect(tmp_path / "gold.db")
    _open_status(conn)
    conn.commit()
    conn.close()
    status, headers, _body = _post(
        app,
        "/recapture/R100/D100/capture",
        {
            "bundle": "company_name",
            "subject": "value",
            "text": "2차회사",
            "confirmed": json.dumps("2차회사"),
        },
    )
    assert status.startswith("303")
    assert headers["Location"] == "/recapture/R100/D100"
    conn = sqlite3.connect(tmp_path / "gold.db")
    assert conn.execute("SELECT count(*) FROM gold_captures").fetchone()[0] == 0
    assert conn.execute("SELECT status FROM gold_samples").fetchone()[0] == "todo"
    value = conn.execute("SELECT value FROM gold_recaptures").fetchone()[0]
    assert json.loads(value) == "2차회사"
    assert conn.execute("SELECT status FROM gold_recapture_status").fetchone()[0] == "in_progress"
    conn.close()
    app.close()


def test_next_resumes_in_progress_then_the_eligible_document(tmp_path: Path) -> None:
    app = _build(tmp_path)
    conn = sqlite3.connect(tmp_path / "gold.db")
    conn.execute(
        """
        INSERT INTO gold_samples (
            run_id, rcept_no, dcm_no, period, stratum, stratum_weight, sample_hash,
            mode, role, queue_order, status, meta, finished_at
        ) VALUES (
            'run', 'E0', 'D', 'P1', 's', 1, 'he', 'blind', 'main', 1, 'done', '{}',
            '2026-01-01T00:00:00+00:00'
        )
        """
    )
    for index in range(20):
        conn.execute(
            """
            INSERT INTO gold_samples (
                run_id, rcept_no, dcm_no, period, stratum, stratum_weight, sample_hash,
                mode, role, queue_order, status, meta, finished_at
            ) VALUES (
                'run', ?, 'D', 'P1', 's', 1, ?, 'blind', 'main', ?, 'done', '{}',
                '2026-06-01T00:00:00+00:00'
            )
            """,
            (f"L{index}", f"hl{index}", 10 + index),
        )
    conn.execute(
        """
        INSERT INTO gold_samples (
            run_id, rcept_no, dcm_no, period, stratum, stratum_weight, sample_hash,
            mode, role, queue_order, status, meta, finished_at
        ) VALUES (
            'run', 'RESUME', 'D', 'P1', 's', 1, 'hr', 'prefill', 'main', 50, 'done', '{}',
            '2026-07-01T00:00:00+00:00'
        )
        """
    )
    _open_status(conn, "RESUME", "D")
    conn.commit()
    before_samples = conn.execute(
        "SELECT rcept_no, status, finished_at FROM gold_samples ORDER BY rcept_no"
    ).fetchall()
    before_status = conn.execute(
        "SELECT rcept_no, status, finished_at FROM gold_recapture_status"
    ).fetchall()
    conn.close()
    status, headers, _body = _request(app, "GET", "/recapture/next", "period=P1")
    assert status.startswith("303")
    assert headers["Location"] == "/recapture/RESUME/D"
    conn = sqlite3.connect(tmp_path / "gold.db")
    assert conn.execute(
        "SELECT rcept_no, status, finished_at FROM gold_samples ORDER BY rcept_no"
    ).fetchall() == before_samples
    assert conn.execute(
        "SELECT rcept_no, status, finished_at FROM gold_recapture_status"
    ).fetchall() == before_status
    conn.execute(
        """
        UPDATE gold_recapture_status
        SET status = 'done', finished_at = '2026-07-02T00:00:00+00:00'
        WHERE rcept_no = 'RESUME'
        """
    )
    conn.commit()
    conn.close()
    status, headers, _body = _request(app, "GET", "/recapture/next", "period=P1")
    assert status.startswith("303")
    assert headers["Location"] == "/recapture/E0/D"
    conn = sqlite3.connect(tmp_path / "gold.db")
    assert conn.execute(
        "SELECT count(*) FROM gold_recapture_status WHERE rcept_no = 'E0'"
    ).fetchone()[0] == 0
    conn.close()
    app.close()


def test_complete_lists_missing_rows_then_marks_the_recapture_done(tmp_path: Path) -> None:
    app = _build(tmp_path)
    conn = sqlite3.connect(tmp_path / "gold.db")
    _open_status(conn)
    conn.commit()
    conn.close()
    status, _headers, body = _post(app, "/recapture/R100/D100/complete", {})
    assert status.startswith("400")
    assert 'id="missing-rows"' in body.decode()
    assert "회사명" in body.decode()
    conn = sqlite3.connect(tmp_path / "gold.db")
    for row in capture_rows():
        conn.execute(
            """
            INSERT INTO gold_recaptures (
                rcept_no, dcm_no, bundle, subject, status, value, evidence, updated_at
            ) VALUES ('R100', 'D100', ?, ?, 'not_applicable', NULL, '', 't')
            """,
            (row.bundle, row.subject),
        )
    conn.commit()
    conn.close()
    done, _headers, _body = _post(app, "/recapture/R100/D100/complete", {})
    assert done.startswith("303")
    conn = sqlite3.connect(tmp_path / "gold.db")
    assert conn.execute("SELECT status FROM gold_samples").fetchone()[0] == "todo"
    assert conn.execute("SELECT status FROM gold_recapture_status").fetchone()[0] == "done"
    assert conn.execute(
        "SELECT finished_at FROM gold_recapture_status"
    ).fetchone()[0]
    conn.close()
    app.close()


def test_recapture_post_requires_token_origin_and_a_clear_document(tmp_path: Path) -> None:
    app = _build(tmp_path)
    conn = sqlite3.connect(tmp_path / "gold.db")
    _open_status(conn)
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
    folder = tmp_path / "cache" / "R100"
    folder.mkdir(parents=True)
    (folder / "main.html").write_text("<p>본문</p>", encoding="utf-8")
    (folder / "toc.json").write_text("{}", encoding="utf-8")
    missing, _headers, missing_body = _raw_post(
        app,
        "/recapture/R100/D100/capture",
        {
            "bundle": "company_name",
            "subject": "value",
            "text": "가나",
            "confirmed": json.dumps("가나"),
        },
    )
    assert missing.startswith("403")
    assert app.token not in missing_body.decode()
    foreign, _headers, _foreign_body = _raw_post(
        app,
        "/recapture/R100/D100/capture",
        {
            "token": app.token,
            "bundle": "company_name",
            "subject": "value",
            "text": "가나",
            "confirmed": json.dumps("가나"),
        },
        origin="http://evil.test",
    )
    assert foreign.startswith("403")
    conflict, conflict_headers, _conflict_body = _raw_post(
        app,
        "/recapture/R100/D100/capture",
        {
            "token": app.token,
            "bundle": "company_name",
            "subject": "value",
            "text": "가나",
            "confirmed": json.dumps("가나"),
        },
    )
    assert conflict.startswith("409")
    assert "Content-Security-Policy" in conflict_headers
    conn = sqlite3.connect(tmp_path / "gold.db")
    assert conn.execute("SELECT count(*) FROM gold_recaptures").fetchone()[0] == 0
    conn.close()
    app.close()


def test_report_is_read_only_and_adjudication_records_history(tmp_path: Path) -> None:
    app = _build(tmp_path)
    conn = sqlite3.connect(tmp_path / "gold.db")
    conn.execute(
        """
        UPDATE gold_samples
        SET mode = 'blind', status = 'done', finished_at = '2026-01-01T00:00:00+00:00'
        WHERE rcept_no = 'R100'
        """
    )
    conn.execute(
        """
        INSERT INTO gold_recapture_status (
            run_id, rcept_no, dcm_no, status, started_at, finished_at
        ) VALUES ('run', 'R100', 'D100', 'done', 't', 't')
        """
    )
    conn.execute(
        """
        INSERT INTO gold_captures (
            rcept_no, dcm_no, bundle, subject, status, value, evidence, updated_at
        ) VALUES ('R100', 'D100', 'auditor', 'value', 'found', ?, 'ev1', 't')
        """,
        (json.dumps("REPORT-SECRET-ZZ", ensure_ascii=False),),
    )
    conn.execute(
        """
        INSERT INTO gold_recaptures (
            rcept_no, dcm_no, bundle, subject, status, value, evidence, updated_at
        ) VALUES ('R100', 'D100', 'auditor', 'value', 'found', ?, 'ev2', 't')
        """,
        (json.dumps("REPORT-SECRET-ZZ", ensure_ascii=False),),
    )
    conn.execute(
        """
        INSERT INTO gold_captures (
            rcept_no, dcm_no, bundle, subject, status, value, evidence, updated_at
        ) VALUES ('R100', 'D100', 'hours', 'total|audit_hours|current', 'found', '120.0', '', 't')
        """
    )
    conn.execute(
        """
        INSERT INTO gold_captures (
            rcept_no, dcm_no, bundle, subject, status, value, evidence, updated_at
        ) VALUES ('R100', 'D100', 'hours', 'total|headcount|current', 'found', '6.0', '', 't')
        """
    )
    conn.execute(
        """
        INSERT INTO gold_recaptures (
            rcept_no, dcm_no, bundle, subject, status, value, evidence, updated_at
        ) VALUES (
            'R100', 'D100', 'hours', 'total|audit_hours|current', 'found', '120.0', '', 't'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO gold_recaptures (
            rcept_no, dcm_no, bundle, subject, status, value, evidence, updated_at
        ) VALUES ('R100', 'D100', 'hours', 'total|headcount|current', 'found', '7.0', '', 't')
        """
    )
    conn.commit()
    conn.close()
    status, _headers, body = _request(app, "GET", "/recapture/report", "run=run")
    page = body.decode()
    assert status == "200 OK"
    assert 'id="consistency-report"' in page
    assert "<form" not in page
    assert "REPORT-SECRET-ZZ" not in page
    assert "OTHER-SECRET-ZZ" not in page
    assert f"{wilson(0, 1)[0]:.10f}" in page
    judge, _headers, judge_body = _request(app, "GET", "/recapture/adjudication", "run=run")
    assert judge == "200 OK"
    form = judge_body.decode()
    assert "6.0" in form
    assert "7.0" in form
    assert "function (" not in form
    assert 'action="/recapture/adjudicate"' in form
    saved, saved_headers, _saved = _raw_post(
        app,
        "/recapture/adjudicate",
        {
            "token": app.token,
            "run_id": "run",
            "rcept_no": "R100",
            "dcm_no": "D100",
            "bundle": "hours",
            "subject": "table",
            "chosen_pass": "2",
            "note": "인원을 따른다",
        },
    )
    assert saved.startswith("303")
    assert saved_headers["Location"] == "/recapture/adjudication?run=run"
    conn = sqlite3.connect(tmp_path / "gold.db")
    assert conn.execute("SELECT chosen_pass, note FROM gold_adjudications").fetchone() == (
        2,
        "인원을 따른다",
    )
    conn.close()
    again, _headers, again_body = _request(app, "GET", "/recapture/adjudication", "run=run")
    assert again == "200 OK"
    assert "인원을 따른다" not in again_body.decode()
    assert 'id="adjudication-empty"' in again_body.decode()
    rejected, _headers, _rejected = _raw_post(
        app,
        "/recapture/adjudicate",
        {
            "token": app.token,
            "run_id": "run",
            "rcept_no": "R100",
            "dcm_no": "D100",
            "bundle": "auditor",
            "subject": "value",
            "chosen_pass": "1",
            "note": "일치인데 판정",
        },
    )
    assert rejected.startswith("400")
    revised, _headers, _revised = _raw_post(
        app,
        "/recapture/adjudicate",
        {
            "token": app.token,
            "run_id": "run",
            "rcept_no": "R100",
            "dcm_no": "D100",
            "bundle": "hours",
            "subject": "table",
            "chosen_pass": "1",
            "note": "1차로 되돌린다",
        },
    )
    assert revised.startswith("303")
    conn = sqlite3.connect(tmp_path / "gold.db")
    history = conn.execute(
        "SELECT chosen_pass, note FROM gold_adjudication_history"
    ).fetchone()
    assert history == (2, "인원을 따른다")
    current = conn.execute("SELECT chosen_pass FROM gold_adjudications").fetchone()[0]
    assert current == 1
    conn.close()
    app.close()


def test_first_pass_posts_stay_409_while_recapture_is_in_progress(tmp_path: Path) -> None:
    app = _build(tmp_path)
    conn = sqlite3.connect(tmp_path / "gold.db")
    conn.execute(
        """
        INSERT INTO gold_captures (
            rcept_no, dcm_no, bundle, subject, status, value, evidence, updated_at
        ) VALUES (
            'R100', 'D100', 'company_name', 'value', 'found', ?, 'PASS1-EVIDENCE-ZZ', 't'
        )
        """,
        (json.dumps("PASS1-CELL-ZZ", ensure_ascii=False),),
    )
    _open_status(conn)
    conn.commit()
    conn.close()
    before = _stored(tmp_path / "gold.db", _FIRST_PASS_TABLES)
    posts = (
        (
            "/doc/R100/D100/capture",
            {
                "bundle": "company_name",
                "subject": "value",
                "text": "다른회사",
                "confirmed": json.dumps("다른회사"),
            },
        ),
        (
            "/doc/R100/D100/unit",
            {"unit_group": "bs", "unit_scale": "1000"},
        ),
        ("/doc/R100/D100/complete", {}),
    )
    for path, fields in posts:
        status, _headers, body = _raw_post(app, path, {"token": app.token, **fields})
        text = body.decode()
        assert status.startswith("409")
        assert text == "재입수 중"
        assert "missing-rows" not in text
        assert "PASS1-CELL-ZZ" not in text
        assert "PASS1-EVIDENCE-ZZ" not in text
        assert _stored(tmp_path / "gold.db", _FIRST_PASS_TABLES) == before
    app.close()


def test_finished_recapture_unlocks_doc_and_locks_second_pass_writes(tmp_path: Path) -> None:
    app = _build(tmp_path)
    conn = sqlite3.connect(tmp_path / "gold.db")
    conn.execute(
        """
        INSERT INTO gold_captures (
            rcept_no, dcm_no, bundle, subject, status, value, evidence, updated_at
        ) VALUES (
            'R100', 'D100', 'company_name', 'value', 'found', ?, 'PASS1-EVIDENCE-ZZ', 't'
        )
        """,
        (json.dumps("PASS1-CELL-ZZ", ensure_ascii=False),),
    )
    conn.execute(
        """
        INSERT INTO gold_captures (
            rcept_no, dcm_no, bundle, subject, status, value, evidence, updated_at
        ) VALUES ('R100', 'D100', 'auditor', 'value', 'found', ?, '', 't')
        """,
        (json.dumps("1차감사인", ensure_ascii=False),),
    )
    _open_status(conn)
    notes = json.dumps({"count": 2, "titles": ["NOTE-A", "NOTE-B"]}, ensure_ascii=False)
    rounds = json.dumps(
        [{"raw": "첫째 회의", "round": 1}, {"raw": "둘째 회의", "round": 2}],
        ensure_ascii=False,
    )
    for row in capture_rows():
        if (row.bundle, row.subject) == ("auditor", "value"):
            status_name, value = "found", json.dumps("2차감사인", ensure_ascii=False)
        elif (row.bundle, row.subject) == ("notes_toc", "value"):
            status_name, value = "found", notes
        elif (row.bundle, row.subject) == ("communications", "items"):
            status_name, value = "found", rounds
        else:
            status_name, value = "not_applicable", None
        conn.execute(
            """
            INSERT INTO gold_recaptures (
                rcept_no, dcm_no, bundle, subject, status, value, evidence, updated_at
            ) VALUES ('R100', 'D100', ?, ?, ?, ?, '', 't')
            """,
            (row.bundle, row.subject, status_name, value),
        )
    conn.execute(
        """
        INSERT INTO gold_recapture_units (rcept_no, dcm_no, unit_group, unit_scale)
        VALUES ('R100', 'D100', 'bs', 1000)
        """
    )
    conn.commit()
    conn.close()
    done, _headers, _body = _post(app, "/recapture/R100/D100/complete", {})
    assert done.startswith("303")
    opened, _headers, page = _request(app, "GET", "/doc/R100/D100")
    assert opened == "200 OK"
    assert "PASS1-CELL-ZZ" in page.decode()
    before = _stored(tmp_path / "gold.db", _RECAPTURE_TABLES)
    writes = (
        (
            "/recapture/R100/D100/capture",
            {
                "bundle": "company_name",
                "subject": "value",
                "text": "바꾼회사",
                "confirmed": json.dumps("바꾼회사"),
            },
        ),
        (
            "/recapture/R100/D100/unit",
            {"unit_group": "bs", "unit_scale": "1000000"},
        ),
        ("/recapture/R100/D100/complete", {}),
        (
            "/recapture/R100/D100/capture",
            {
                "bundle": "notes_toc",
                "subject": "value",
                "status": "remove_title",
                "index": "0",
            },
        ),
        (
            "/recapture/R100/D100/capture",
            {
                "bundle": "communications",
                "subject": "items",
                "status": "remove_item",
                "index": "0",
            },
        ),
    )
    for path, fields in writes:
        status, _headers, body = _raw_post(app, path, {"token": app.token, **fields})
        text = body.decode()
        assert status.startswith("409")
        assert "missing-rows" not in text
        assert "PASS1-CELL-ZZ" not in text
        assert "1차감사인" not in text
        assert "NOTE-A" not in text
        assert _stored(tmp_path / "gold.db", _RECAPTURE_TABLES) == before
    judged, judged_headers, _judged = _raw_post(
        app,
        "/recapture/adjudicate",
        {
            "token": app.token,
            "run_id": "run",
            "rcept_no": "R100",
            "dcm_no": "D100",
            "bundle": "auditor",
            "subject": "value",
            "chosen_pass": "2",
            "note": "2차를 고른다",
        },
    )
    assert judged.startswith("303")
    assert judged_headers["Location"] == "/recapture/adjudication?run=run"
    assert _stored(tmp_path / "gold.db", _RECAPTURE_TABLES) == before
    conn = sqlite3.connect(tmp_path / "gold.db")
    assert conn.execute("SELECT chosen_pass, note FROM gold_adjudications").fetchone() == (
        2,
        "2차를 고른다",
    )
    assert conn.execute("SELECT status FROM gold_samples").fetchone()[0] == "todo"
    conn.close()
    app.close()


def test_recapture_routes_do_not_download_sample_or_capture(
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
    conn = sqlite3.connect(tmp_path / "gold.db")
    _open_status(conn)
    conn.commit()
    conn.close()
    listed, listed_headers, _body = _request(app, "GET", "/recapture/next", "period=P7")
    opened, _headers, _body = _request(app, "GET", "/recapture/R100/D100")
    posted, _headers, _body = _post(
        app,
        "/recapture/R100/D100/capture",
        {
            "bundle": "company_name",
            "subject": "value",
            "text": "가나",
            "confirmed": json.dumps("가나"),
        },
    )
    report, _headers, _body = _request(app, "GET", "/recapture/report", "run=run")
    assert listed.startswith("303")
    assert listed_headers["Location"] == "/recapture/R100/D100"
    assert opened == "200 OK"
    assert posted.startswith("303")
    assert report == "200 OK"
    app.close()


_PASS_TABLES = (
    "SELECT * FROM gold_captures ORDER BY rcept_no, dcm_no, bundle, subject",
    "SELECT * FROM gold_samples ORDER BY run_id, rcept_no, dcm_no",
)


def test_preview_rejects_a_missing_token_or_a_foreign_origin(tmp_path: Path) -> None:
    app = _build(tmp_path)
    before = _stored(tmp_path / "gold.db", _PASS_TABLES)
    fields = {"bundle": "opinion", "subject": "value", "text": "한정의견을 표명합니다"}
    missing, _headers, missing_body = _raw_post(app, "/doc/R100/D100/preview", fields)
    foreign, _headers, foreign_body = _raw_post(
        app,
        "/doc/R100/D100/preview",
        {"token": app.token, **fields},
        origin="https://evil.example",
    )
    assert missing.startswith("403")
    assert foreign.startswith("403")
    assert app.token not in missing_body.decode()
    assert app.token not in foreign_body.decode()
    assert _stored(tmp_path / "gold.db", _PASS_TABLES) == before
    app.close()


def test_first_pass_preview_stays_locked_while_recapture_is_open(tmp_path: Path) -> None:
    app = _build(tmp_path)
    conn = sqlite3.connect(tmp_path / "gold.db")
    conn.execute(
        """
        INSERT INTO gold_captures (
            rcept_no, dcm_no, bundle, subject, status, value, evidence, updated_at
        ) VALUES (
            'R100', 'D100', 'company_name', 'value', 'found', ?, 'PASS1-EVIDENCE-ZZ', 't'
        )
        """,
        (json.dumps("PASS1-CELL-ZZ", ensure_ascii=False),),
    )
    _open_status(conn)
    conn.commit()
    conn.close()
    before = _stored(tmp_path / "gold.db", _PASS_TABLES)
    status, _headers, body = _raw_post(
        app,
        "/doc/R100/D100/preview",
        {
            "token": app.token,
            "bundle": "opinion",
            "subject": "value",
            "text": "한정의견을 표명합니다",
        },
    )
    text = body.decode()
    assert status.startswith("409")
    assert json.loads(text) == {"error": "재입수 중"}
    assert "PASS1-CELL-ZZ" not in text
    assert "PASS1-EVIDENCE-ZZ" not in text
    assert "missing-rows" not in text
    assert "빠진" not in text
    assert _stored(tmp_path / "gold.db", _PASS_TABLES) == before
    app.close()


def test_finished_recapture_locks_the_second_pass_preview(tmp_path: Path) -> None:
    app = _build(tmp_path)
    conn = sqlite3.connect(tmp_path / "gold.db")
    _open_status(conn)
    conn.execute(
        """
        UPDATE gold_recapture_status
        SET status = 'done', finished_at = '2026-07-02T00:00:00+00:00'
        WHERE rcept_no = 'R100'
        """
    )
    conn.execute(
        """
        INSERT INTO gold_recaptures (
            rcept_no, dcm_no, bundle, subject, status, value, evidence, updated_at
        ) VALUES (
            'R100', 'D100', 'company_name', 'value', 'found', ?, 'PASS2-EVIDENCE-ZZ', 't'
        )
        """,
        (json.dumps("PASS2-CELL-ZZ", ensure_ascii=False),),
    )
    conn.commit()
    conn.close()
    before = _stored(tmp_path / "gold.db", _RECAPTURE_TABLES)
    status, _headers, body = _raw_post(
        app,
        "/recapture/R100/D100/preview",
        {
            "token": app.token,
            "bundle": "opinion",
            "subject": "value",
            "text": "한정의견을 표명합니다",
        },
    )
    text = body.decode()
    assert status.startswith("409")
    assert json.loads(text) == {"error": "재입수가 끝났습니다"}
    assert "PASS2-CELL-ZZ" not in text
    assert _stored(tmp_path / "gold.db", _RECAPTURE_TABLES) == before
    app.close()


def test_recapture_page_points_preview_at_the_second_pass(tmp_path: Path) -> None:
    app = _build(tmp_path)
    conn = sqlite3.connect(tmp_path / "gold.db")
    _open_status(conn)
    conn.commit()
    conn.close()
    status, _headers, body = _request(app, "GET", "/recapture/R100/D100")
    page = body.decode()
    assert status == "200 OK"
    raw = page.split('id="capture-data"', 1)[1]
    raw = raw.split(">", 1)[1].split("</script>", 1)[0]
    assert json.loads(raw)["previewUrl"] == "/recapture/R100/D100/preview"
    app.close()
