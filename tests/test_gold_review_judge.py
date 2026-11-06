"""판정 저장. 임시 DB와 가짜 HTML만 쓰고 네트워크는 열지 않는다."""

from __future__ import annotations

import io
import json
import socket
import sqlite3
from pathlib import Path
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

import pytest

from dart_parser.gold.app import ReviewApplication
from dart_parser.gold.db import migrate, open_gold
from dart_parser.gold.evidence import section_windows
from gold_fixtures import make_catalog


def _call(
    app: ReviewApplication,
    method: str,
    path: str,
    body: bytes = b"",
    *,
    host: str = "127.0.0.1:80",
    port: str = "80",
    origin: str | None = None,
    referer: str | None = None,
) -> tuple[str, dict[str, str], bytes]:
    environ: dict[str, object] = {"PATH_INFO": path, "QUERY_STRING": "", "REQUEST_METHOD": method}
    setup_testing_defaults(environ)
    environ["REQUEST_METHOD"] = method
    environ["SERVER_PORT"] = port
    environ["HTTP_HOST"] = host
    environ["wsgi.input"] = io.BytesIO(body)
    environ["CONTENT_LENGTH"] = str(len(body))
    if origin is not None:
        environ["HTTP_ORIGIN"] = origin
    if referer is not None:
        environ["HTTP_REFERER"] = referer
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]], exc_info=None) -> None:
        del exc_info
        captured["status"] = status
        captured["headers"] = {key: value for key, value in headers}

    payload = b"".join(app(environ, start_response))
    return str(captured["status"]), dict(captured["headers"]), payload


def _post(
    app: ReviewApplication,
    rcept_no: str,
    dcm_no: str,
    fields: dict[str, str],
    **kwargs: str | None,
) -> tuple[str, dict[str, str], bytes]:
    body = urlencode(fields).encode()
    return _call(app, "POST", f"/doc/{rcept_no}/{dcm_no}/label", body, **kwargs)


def _extraction() -> dict[str, object]:
    return {
        "company_name": {"status": "found", "value": "골드주식회사"},
        "opinion": {"status": "found", "value": "적정"},
        "going_concern": {"status": "found", "value": 0},
        "notes_toc": {"status": "found", "value": {"count": 2, "titles": ["일반", "재고"]}},
        "hours": {"status": "found", "value": {"cells": [["10"]]}},
        "accounts": {
            "status": "found",
            "value": {
                "revenue": {
                    "current": {
                        "raw": "1,234",
                        "value": 1234,
                        "unit_scale": 1000,
                        "value_won": 1234000,
                    },
                    "prior": {"raw": "9", "value": 9, "unit_scale": 1, "value_won": 9},
                }
            },
        },
    }


def _build(
    tmp_path: Path,
    *,
    params: dict[str, object] | None = None,
    pin_row: tuple[str, str] | None = None,
    snapshots: list[tuple[str, dict[str, object], str]] | None = None,
    entries: list[tuple[str, str, str, str, str]] | None = None,
    extra_dcms: list[str] | None = None,
    rcept_no: str = "R100",
    dcm_no: str = "D100",
) -> tuple[ReviewApplication, Path]:
    catalog = make_catalog(tmp_path)
    if entries:
        catalog_conn = sqlite3.connect(catalog)
        catalog_conn.executemany(
            """
            INSERT INTO entries (
                entry_id, rcept_no, dcm_no, section_name, ele_id, dtd, viewer_url
            ) VALUES (?, ?, ?, ?, ?, '', '')
            """,
            entries,
        )
        catalog_conn.commit()
        catalog_conn.close()
    gold_path = tmp_path / "gold.db"
    cache = tmp_path / "cache"
    conn = open_gold(gold_path, None)
    migrate(conn)
    stored = {} if params is None else params
    conn.execute(
        """
        INSERT INTO gold_runs (
            run_id, seed, created_at, population_sql_sha, db_snapshot, params, stats
        ) VALUES ('run', 'seed', '2026-11-06T00:00:00+00:00', 'x', NULL, ?, '{}')
        """,
        (json.dumps(stored, ensure_ascii=False),),
    )
    conn.execute(
        """
        INSERT INTO gold_samples (
            run_id, rcept_no, dcm_no, period, stratum, stratum_weight, sample_hash,
            mode, role, queue_order, status, meta
        ) VALUES ('run', ?, ?, 'P7', 'listed', 1, 'h', 'prefill', 'main', 1, 'todo', '{}')
        """,
        (rcept_no, dcm_no),
    )
    for index, extra in enumerate(extra_dcms or [], start=2):
        conn.execute(
            """
            INSERT INTO gold_samples (
                run_id, rcept_no, dcm_no, period, stratum, stratum_weight, sample_hash,
                mode, role, queue_order, status, meta
            ) VALUES (
                'run', ?, ?, 'P7', 'listed', 1, ?, 'prefill', 'main', ?, 'todo', '{}'
            )
            """,
            (rcept_no, extra, f"h{index}", index),
        )
    if pin_row is not None:
        conn.execute(
            """
            INSERT INTO gold_run_extractors (run_id, extractor_version, extractor_commit)
            VALUES ('run', ?, ?)
            """,
            pin_row,
        )
    chosen = snapshots
    if chosen is None:
        chosen = [("0.1.0", _extraction(), "2026-11-06T00:00:00+00:00")]
    for version, extraction, captured in chosen:
        payload = {
            "extractor_version": version,
            "commit": "payload-commit",
            "rcept_no": rcept_no,
            "dcm_no": dcm_no,
            "extraction": extraction,
        }
        conn.execute(
            """
            INSERT INTO extractor_snapshots (
                extractor_version, rcept_no, dcm_no, payload, captured_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (version, rcept_no, dcm_no, json.dumps(payload, ensure_ascii=False), captured),
        )
    conn.commit()
    conn.close()
    folder = cache / rcept_no
    folder.mkdir(parents=True)
    (folder / "main.html").write_text("<p>표지 골드주식회사</p>", encoding="utf-8")
    app = ReviewApplication(catalog, gold_path, cache)
    return app, gold_path


def _rows(gold_path: Path, sql: str) -> list[sqlite3.Row]:
    conn = sqlite3.connect(gold_path)
    conn.row_factory = sqlite3.Row
    try:
        return list(conn.execute(sql))
    finally:
        conn.close()


def _fields(app: ReviewApplication, **extra: str) -> dict[str, str]:
    fields = {
        "token": app.token,
        "bundle": "company_name",
        "subject": "value",
        "verdict": "correct",
    }
    fields.update(extra)
    return fields


def test_save_copies_the_pinned_snapshot_and_starts_the_sample(tmp_path: Path) -> None:
    app, gold_path = _build(
        tmp_path,
        params={"extractor_version": "0.1.0", "extractor_commit": "abc123"},
    )
    status, headers, _body = _post(
        app,
        "R100",
        "D100",
        _fields(app),
        referer="http://127.0.0.1:80/doc/R100/D100",
    )
    assert status.startswith("303")
    assert headers["Location"] == "/doc/R100/D100"
    label = _rows(gold_path, "SELECT * FROM gold_labels")[0]
    assert label["verdict"] == "correct"
    assert json.loads(label["gold_value"]) == "골드주식회사"
    assert json.loads(label["shown_value"]) == "골드주식회사"
    assert label["shown_extractor_version"] == "0.1.0"
    assert label["labeled_at"]
    assert app.token.encode() not in gold_path.read_bytes()
    sample = _rows(gold_path, "SELECT status, started_at, finished_at FROM gold_samples")[0]
    assert sample["status"] == "in_progress"
    assert sample["started_at"]
    assert sample["finished_at"] is None
    app.close()


def test_rejudge_moves_the_previous_row_to_history(tmp_path: Path) -> None:
    app, gold_path = _build(
        tmp_path,
        params={"extractor_version": "0.1.0", "extractor_commit": "abc123"},
    )
    _post(app, "R100", "D100", _fields(app))
    status, _headers, _body = _post(
        app,
        "R100",
        "D100",
        _fields(app, verdict="wrong", gold_text="바른회사"),
    )
    assert status.startswith("303")
    current = _rows(gold_path, "SELECT verdict, gold_value FROM gold_labels")
    assert len(current) == 1
    assert current[0]["verdict"] == "wrong"
    assert json.loads(current[0]["gold_value"]) == "바른회사"
    history = _rows(gold_path, "SELECT verdict, superseded_at FROM gold_label_history")
    assert len(history) == 1
    assert history[0]["verdict"] == "correct"
    assert history[0]["superseded_at"]
    app.close()


def test_failed_rejudge_rolls_the_history_move_back(tmp_path: Path) -> None:
    app, gold_path = _build(
        tmp_path,
        params={"extractor_version": "0.1.0", "extractor_commit": "abc123"},
    )
    assert _post(app, "R100", "D100", _fields(app))[0].startswith("303")
    app.store.conn.execute(
        """
        CREATE TRIGGER abort_labels BEFORE INSERT ON gold_labels
        BEGIN
            SELECT RAISE(ABORT, 'fail insert');
        END
        """
    )
    app.store.conn.commit()
    status, _headers, body = _post(
        app, "R100", "D100", _fields(app, verdict="wrong", gold_text="바른회사")
    )
    assert status.startswith("500")
    assert app.token not in body.decode()
    current = list(app.store.conn.execute("SELECT verdict FROM gold_labels"))
    history = list(app.store.conn.execute("SELECT verdict FROM gold_label_history"))
    assert [row["verdict"] for row in current] == ["correct"]
    assert history == []
    app.close()


def test_page_shows_only_the_pinned_version(tmp_path: Path) -> None:
    older = _extraction()
    newer = _extraction()
    newer["company_name"] = {"status": "found", "value": "최신회사"}
    app, _gold = _build(
        tmp_path,
        params={"extractor_version": "0.1.0", "extractor_commit": "pincommit"},
        snapshots=[
            ("0.1.0", older, "2026-11-01T00:00:00+00:00"),
            ("0.2.0", newer, "2026-11-06T00:00:00+00:00"),
        ],
    )
    status, _headers, body = _call(app, "GET", "/doc/R100/D100")
    page = body.decode()
    assert status == "200 OK"
    assert "골드주식회사" in page
    assert "최신회사" not in page
    assert "pincommit" in page
    assert "payload-commit" not in page
    assert "0.2.0" not in page
    app.close()


def test_missing_pin_blocks_save_and_hides_snapshots(tmp_path: Path) -> None:
    app, gold_path = _build(tmp_path, params={})
    status, _headers, body = _call(app, "GET", "/doc/R100/D100")
    page = body.decode()
    assert status == "200 OK"
    assert "고정되어 있지 않습니다" in page
    assert "<form" not in page
    assert "골드주식회사" not in page
    saved, _headers, _payload = _post(app, "R100", "D100", _fields(app))
    assert saved.startswith("400")
    assert _rows(gold_path, "SELECT * FROM gold_labels") == []
    app.close()


def test_pin_table_is_used_when_params_omit_the_extractor(tmp_path: Path) -> None:
    pinned = _extraction()
    pinned["company_name"] = {"status": "found", "value": "표고정"}
    other = _extraction()
    other["company_name"] = {"status": "found", "value": "다른회사"}
    app, _gold = _build(
        tmp_path,
        params={},
        pin_row=("0.1.0", "tablecommit"),
        snapshots=[
            ("0.1.0", pinned, "2026-11-01T00:00:00+00:00"),
            ("0.2.0", other, "2026-11-06T00:00:00+00:00"),
        ],
    )
    _status, _headers, body = _call(app, "GET", "/doc/R100/D100")
    page = body.decode()
    assert "표고정" in page
    assert "다른회사" not in page
    assert "tablecommit" in page
    app.close()


def test_missing_pinned_snapshot_rejects_save(tmp_path: Path) -> None:
    app, gold_path = _build(
        tmp_path,
        params={"extractor_version": "0.9.0", "extractor_commit": "abc123"},
        snapshots=[("0.2.0", _extraction(), "2026-11-06T00:00:00+00:00")],
    )
    _status, _headers, body = _call(app, "GET", "/doc/R100/D100")
    page = body.decode()
    assert "스냅샷이 없습니다" in page
    assert "<form" not in page
    assert "골드주식회사" not in page
    saved, _headers, _payload = _post(app, "R100", "D100", _fields(app))
    assert saved.startswith("400")
    assert _rows(gold_path, "SELECT * FROM gold_labels") == []
    app.close()


def test_account_wrong_needs_display_value_and_unit_scale(tmp_path: Path) -> None:
    app, gold_path = _build(
        tmp_path,
        params={"extractor_version": "0.1.0", "extractor_commit": "abc123"},
    )
    page = _call(app, "GET", "/doc/R100/D100")[2].decode()
    assert 'value="revenue@current"' in page
    assert 'value="revenue@prior"' in page
    assert page.count('name="display_value"') == 26
    assert page.count('name="unit_scale"') == 26
    missing, _headers, _body = _post(
        app,
        "R100",
        "D100",
        _fields(
            app,
            bundle="accounts",
            subject="revenue@current",
            verdict="wrong",
            display_value="1,234",
        ),
    )
    assert missing.startswith("400")
    assert _rows(gold_path, "SELECT * FROM gold_labels") == []
    saved, _headers, _body = _post(
        app,
        "R100",
        "D100",
        _fields(
            app,
            bundle="accounts",
            subject="revenue@prior",
            verdict="wrong",
            display_value="1,234",
            unit_scale="1000",
        ),
    )
    assert saved.startswith("303")
    label = _rows(gold_path, "SELECT subject, gold_value FROM gold_labels")[0]
    assert label["subject"] == "revenue@prior"
    assert json.loads(label["gold_value"]) == {"value": 1234, "unit_scale": 1000}
    app.close()


def test_notes_toc_is_one_judgment_of_count_and_titles(tmp_path: Path) -> None:
    app, gold_path = _build(
        tmp_path,
        params={"extractor_version": "0.1.0", "extractor_commit": "abc123"},
    )
    page = _call(app, "GET", "/doc/R100/D100")[2].decode()
    assert 'name="toc_count"' in page
    assert "일반" in page and "재고" in page
    missing, _headers, _body = _post(
        app,
        "R100",
        "D100",
        _fields(app, bundle="notes_toc", subject="value", verdict="wrong", toc_count="1"),
    )
    assert missing.startswith("400")
    saved, _headers, _body = _post(
        app,
        "R100",
        "D100",
        _fields(
            app,
            bundle="notes_toc",
            subject="value",
            verdict="wrong",
            toc_count="2",
            toc_titles="일반사항\n재고자산",
        ),
    )
    assert saved.startswith("303")
    stored = json.loads(_rows(gold_path, "SELECT gold_value FROM gold_labels")[0]["gold_value"])
    assert stored == {"count": 2, "titles": ["일반사항", "재고자산"]}
    app.close()


def test_table_wrong_requires_a_note(tmp_path: Path) -> None:
    app, gold_path = _build(
        tmp_path,
        params={"extractor_version": "0.1.0", "extractor_commit": "abc123"},
    )
    page = _call(app, "GET", "/doc/R100/D100")[2].decode()
    assert page.count('name="note"') == 3
    assert "의견 근거만" in page
    assert "전기 인용만" in page
    assert "청산기준" in page
    missing, _headers, body = _post(
        app,
        "R100",
        "D100",
        _fields(app, bundle="hours", subject="table", verdict="wrong"),
    )
    assert missing.startswith("400")
    assert "메모" in body.decode()
    assert _rows(gold_path, "SELECT * FROM gold_labels") == []
    saved, _headers, _body = _post(
        app,
        "R100",
        "D100",
        _fields(app, bundle="activities", subject="table", verdict="wrong", note="행이 빠졌습니다"),
    )
    assert saved.startswith("303")
    label = _rows(gold_path, "SELECT gold_value, note FROM gold_labels")[0]
    assert json.loads(label["gold_value"]) == {"verdict": "wrong"}
    assert label["note"] == "행이 빠졌습니다"
    app.close()


def test_rejects_bad_host_origin_and_token(tmp_path: Path) -> None:
    app, gold_path = _build(
        tmp_path,
        params={"extractor_version": "0.1.0", "extractor_commit": "abc123"},
    )
    fields = _fields(app)
    host, _headers, host_body = _post(app, "R100", "D100", fields, host="evil.test:80")
    origin, _headers, origin_body = _post(
        app, "R100", "D100", fields, origin="http://evil.test"
    )
    token, _headers, token_body = _post(app, "R100", "D100", {**fields, "token": "nope"})
    assert host.startswith("403")
    assert origin.startswith("403")
    assert token.startswith("403")
    assert app.token not in host_body.decode()
    assert app.token not in origin_body.decode()
    assert app.token not in token_body.decode()
    assert _rows(gold_path, "SELECT * FROM gold_labels") == []
    allowed, _headers, _body = _post(app, "R100", "D100", fields, host="localhost:80")
    assert allowed.startswith("303")
    app.close()


def test_rejects_a_subject_outside_the_map(tmp_path: Path) -> None:
    app, gold_path = _build(
        tmp_path,
        params={"extractor_version": "0.1.0", "extractor_commit": "abc123"},
    )
    status, _headers, _body = _post(
        app, "R100", "D100", _fields(app, bundle="company_name", subject="table")
    )
    assert status.startswith("400")
    bad_id, _headers, _body = _call(
        app,
        "POST",
        "/doc/bad_id/D100/label",
        urlencode(_fields(app)).encode(),
    )
    assert bad_id.startswith("404")
    assert _rows(gold_path, "SELECT * FROM gold_labels") == []
    app.close()


def test_finishing_the_required_subject_marks_the_sample_done(tmp_path: Path) -> None:
    app, gold_path = _build(
        tmp_path,
        params={"extractor_version": "0.1.0", "extractor_commit": "abc123"},
    )
    app.store.conn.execute(
        """
        UPDATE gold_samples
        SET role = 'oversample', meta = ?
        WHERE rcept_no = 'R100'
        """,
        (json.dumps({"oversample_for": "opinion:value"}),),
    )
    app.store.conn.commit()
    status, _headers, _body = _post(
        app, "R100", "D100", _fields(app, bundle="opinion", subject="value", verdict="na")
    )
    assert status.startswith("303")
    sample = _rows(gold_path, "SELECT status, started_at, finished_at FROM gold_samples")[0]
    assert sample["status"] == "done"
    assert sample["started_at"]
    assert sample["finished_at"]
    label = _rows(gold_path, "SELECT gold_value, verdict FROM gold_labels")[0]
    assert label["verdict"] == "na"
    assert label["gold_value"] is None
    app.close()


def test_euc_kr_source_is_shown(tmp_path: Path) -> None:
    app, _gold = _build(
        tmp_path,
        params={"extractor_version": "0.1.0", "extractor_commit": "abc123"},
    )
    html_path = tmp_path / "cache" / "R100" / "main.html"
    html_path.write_bytes('<meta charset="euc-kr"><p>한글주식회사</p>'.encode("euc-kr"))
    parent = _call(app, "GET", "/doc/R100/D100")[2].decode()
    status, _headers, body = _call(app, "GET", "/doc/R100/D100/source")
    assert status == "200 OK"
    assert "한글주식회사" in body.decode()
    assert "인코딩 확인 필요" not in parent
    app.close()


def test_bad_encoding_warns_without_a_server_error(tmp_path: Path) -> None:
    app, _gold = _build(
        tmp_path,
        params={"extractor_version": "0.1.0", "extractor_commit": "abc123"},
    )
    html_path = tmp_path / "cache" / "R100" / "main.html"
    html_path.write_bytes(b'<meta charset="euc-kr"><p>\xff\xff</p>')
    parent_status, _headers, parent = _call(app, "GET", "/doc/R100/D100")
    source_status, _headers, _source = _call(app, "GET", "/doc/R100/D100/source")
    assert parent_status == "200 OK"
    assert "인코딩 확인 필요" in parent.decode()
    assert source_status == "200 OK"
    app.close()


def test_source_loads_the_section_for_that_dcm(tmp_path: Path) -> None:
    app, _gold = _build(
        tmp_path,
        params={"extractor_version": "0.1.0", "extractor_commit": "abc123"},
        entries=[("bs1", "R100", "D100", "재무상태표", "4")],
    )
    first = tmp_path / "cache" / "R100" / "D100"
    second = tmp_path / "cache" / "R100" / "D200"
    first.mkdir()
    second.mkdir()
    (first / "toc.json").write_text('{"4": "bs.html"}', encoding="utf-8")
    (first / "bs.html").write_text("<p>재무상태표 디씨엠본문</p>", encoding="utf-8")
    (second / "bs.html").write_text("<p>다른문서본문</p>", encoding="utf-8")
    (tmp_path / "cache" / "R100" / "main.html").write_text("<p>메인만</p>", encoding="utf-8")
    reopened = app
    status, headers, body = _call(reopened, "GET", "/doc/R100/D100/source")
    source = body.decode()
    assert status == "200 OK"
    assert "재무상태표 디씨엠본문" in source
    assert "다른문서본문" not in source
    assert "메인만" not in source
    assert 'sandbox=""' not in source
    parent = _call(reopened, "GET", "/doc/R100/D100")[2].decode()
    assert 'sandbox=""' in parent
    assert "default-src 'none'" in headers["Content-Security-Policy"]
    reopened.close()


def test_ambiguous_dcm_cache_shows_a_warning(tmp_path: Path) -> None:
    app, _gold_path = _build(
        tmp_path,
        params={"extractor_version": "0.1.0", "extractor_commit": "abc123"},
        extra_dcms=["D200"],
    )
    page = _call(app, "GET", "/doc/R100/D100")[2].decode()
    assert "문서 번호를 구분할 수 없습니다" in page
    app.close()


def test_anchor_goes_in_a_text_node_only(tmp_path: Path) -> None:
    app, _gold = _build(
        tmp_path,
        params={"extractor_version": "0.1.0", "extractor_commit": "abc123"},
        entries=[("cover1", "R100", "D100", "표지", "1")],
    )
    folder = tmp_path / "cache" / "R100"
    (folder / "toc.json").write_text('{"1": "body.html"}', encoding="utf-8")
    (folder / "body.html").write_text(
        "<html><head><title>표지</title></head><body>"
        '<nav id="toc">표지</nav>'
        '<p title="표지">다른문장</p>'
        "<p>표지 본문</p>"
        "</body></html>",
        encoding="utf-8",
    )
    reopened = app
    source = _call(reopened, "GET", "/doc/R100/D100/source")[2].decode()
    head = source.split("</head>", 1)[0]
    nav = source.split("<nav", 1)[1].split("</nav>", 1)[0]
    assert "win-cover" not in head
    assert "win-cover" not in nav
    assert 'title="표지"' in source
    assert source.count('id="win-cover"') == 1
    assert source.index('id="win-cover"') < source.index("표지 본문")
    assert source.index("다른문장") < source.index('id="win-cover"')
    reopened.close()


def test_empty_section_windows_do_not_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake(bundle: str) -> tuple[str, ...]:
        if bundle == "company_name":
            return ()
        return section_windows(bundle)

    monkeypatch.setattr("dart_parser.gold.app.section_windows", fake)
    app, _gold = _build(
        tmp_path,
        params={"extractor_version": "0.1.0", "extractor_commit": "abc123"},
    )
    status, _headers, body = _call(app, "GET", "/doc/R100/D100")
    assert status == "200 OK"
    assert "company_name" in body.decode()
    source_status, _headers, _source = _call(app, "GET", "/doc/R100/D100/source")
    assert source_status == "200 OK"
    app.close()


def test_save_does_not_sample_capture_or_use_the_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args, **_kwargs):
        raise AssertionError("network or sampling")

    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr("urllib.request.urlopen", boom)
    monkeypatch.setattr("dart_parser.gold.sampler.build_sample", boom)
    monkeypatch.setattr("dart_parser.gold.snapshots.capture", boom)
    app, _gold = _build(
        tmp_path,
        params={"extractor_version": "0.1.0", "extractor_commit": "abc123"},
    )
    status, _headers, _body = _post(app, "R100", "D100", _fields(app))
    assert status.startswith("303")
    app.close()
