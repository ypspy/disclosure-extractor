"""골드 리뷰 앱 뼈대. 임시 DB와 HTML만 쓰고 네트워크는 열지 않는다."""

from __future__ import annotations

import io
import json
import socket
import sqlite3
from pathlib import Path
from wsgiref.util import setup_testing_defaults

import pytest

from dart_parser.gold.app import (
    LOOPBACK,
    ReviewApplication,
    bind_host,
    make_loopback_server,
    parse_args,
)
from dart_parser.gold.db import migrate, open_gold
from gold_fixtures import make_catalog


def _request(
    app: ReviewApplication,
    path: str,
    query: str = "",
    method: str = "GET",
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


def _seed(tmp_path: Path) -> tuple[Path, Path, Path]:
    catalog = make_catalog(tmp_path)
    gold_path = tmp_path / "gold.db"
    cache = tmp_path / "cache"
    conn = open_gold(gold_path, None)
    migrate(conn)
    conn.execute(
        """
        INSERT INTO gold_runs (
            run_id, seed, created_at, population_sql_sha, db_snapshot, params, stats
        ) VALUES ('run', 'seed', '2026-11-06T00:00:00+00:00', 'x', NULL, '{}', '{}')
        """
    )
    rows = [
        ("R100", "D100", "P7", "listed", "todo", 1),
        ("R200", "D200", "P1", "unlisted", "done", 2),
    ]
    for rcept_no, dcm_no, period, stratum, status, order in rows:
        conn.execute(
            """
            INSERT INTO gold_samples (
                run_id, rcept_no, dcm_no, period, stratum, stratum_weight, sample_hash,
                mode, role, queue_order, status, meta
            ) VALUES ('run', ?, ?, ?, ?, 1, 'h', 'prefill', 'main', ?, ?, '{}')
            """,
            (rcept_no, dcm_no, period, stratum, order, status),
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
    folder = cache / "R100"
    folder.mkdir(parents=True)
    (folder / "main.html").write_text(
        "<p>표지 골드주식회사</p><p>독립된감사인의 감사보고서</p><script>fetch('https://example.test')</script>",
        encoding="utf-8",
    )
    return catalog, gold_path, cache


def test_bind_host_is_loopback_only() -> None:
    assert bind_host("127.0.0.1") == LOOPBACK
    with pytest.raises(ValueError):
        bind_host("0.0.0.0")
    with pytest.raises(ValueError):
        bind_host("192.168.0.2")


def test_server_socket_is_loopback(tmp_path: Path) -> None:
    app = ReviewApplication(make_catalog(tmp_path), tmp_path / "gold.db", tmp_path / "cache")
    server = make_loopback_server(app, 0)
    try:
        host, _port = server.server_address[:2]
        assert host == "127.0.0.1"
    finally:
        server.server_close()


def test_catalog_attached_read_only(tmp_path: Path) -> None:
    catalog, gold_path, cache = _seed(tmp_path)
    app = ReviewApplication(catalog, gold_path, cache)
    assert app.store.conn.execute("SELECT count(*) FROM cat.disclosures").fetchone()[0] > 0
    with pytest.raises(sqlite3.OperationalError):
        app.store.conn.execute("DELETE FROM cat.disclosures")
    app.close()


def test_empty_list_explains_that_sampling_does_not_run(tmp_path: Path) -> None:
    app = ReviewApplication(make_catalog(tmp_path), tmp_path / "gold.db", tmp_path / "cache")
    status, _headers, body = _request(app, "/")
    page = body.decode()
    assert status == "200 OK"
    assert "샘플이 없습니다" in page
    assert "샘플링" in page
    app.close()


def test_list_shows_samples_by_period_stratum_and_status(tmp_path: Path) -> None:
    catalog, gold_path, cache = _seed(tmp_path)
    app = ReviewApplication(catalog, gold_path, cache)
    _status, _headers, body = _request(app, "/")
    page = body.decode()
    assert "P7" in page and "listed" in page and "todo" in page
    assert "P1" in page and "unlisted" in page and "done" in page
    assert 'href="/doc/R100/D100"' in page
    filtered, _headers, narrow = _request(app, "/", "period=P1")
    text = narrow.decode()
    assert filtered == "200 OK"
    assert "R200" in text
    assert "R100" not in text
    app.close()


def test_document_page_is_read_only_snapshot(tmp_path: Path) -> None:
    catalog, gold_path, cache = _seed(tmp_path)
    app = ReviewApplication(catalog, gold_path, cache)
    status, _headers, body = _request(app, "/doc/R100/D100")
    page = body.decode()
    assert status == "200 OK"
    assert page.index("company_name") < page.index("going_concern") < page.index("notes_toc")
    assert page.count('data-subject="') == 42
    assert "골드주식회사" in page
    assert "적정" in page
    assert "0.1.0" in page
    assert "abc123" in page
    assert 'href="/doc/R100/D100/source#win-cover"' in page
    slot = page.split('id="judgment-slot"', 1)[1].split("</aside>", 1)[0]
    assert "<" not in slot
    assert "<form" not in page
    assert "<button" not in page
    assert "<input" not in page
    app.close()


def test_source_is_sandboxed_and_blocks_external_resources(tmp_path: Path) -> None:
    catalog, gold_path, cache = _seed(tmp_path)
    app = ReviewApplication(catalog, gold_path, cache)
    _status, _headers, parent = _request(app, "/doc/R100/D100")
    page = parent.decode()
    assert 'sandbox=""' in page
    assert "fetch('https://example.test')" not in page
    status, headers, body = _request(app, "/doc/R100/D100/source")
    assert status == "200 OK"
    policy = headers["Content-Security-Policy"]
    assert "default-src 'none'" in policy
    assert "script-src" not in policy or "'none'" in policy
    source = body.decode()
    assert 'id="win-cover"' in source
    assert 'id="win-opinion_letter"' in source
    app.close()


def test_missing_cache_is_marked_and_not_downloaded(tmp_path: Path) -> None:
    catalog, gold_path, cache = _seed(tmp_path)
    app = ReviewApplication(catalog, gold_path, cache)
    status, _headers, body = _request(app, "/doc/R200/D200")
    page = body.decode()
    assert status == "200 OK"
    assert "캐시 없음" in page
    assert "<iframe" not in page
    missing, _headers, payload = _request(app, "/doc/R200/D200/source")
    assert missing == "404 Not Found"
    assert "캐시 없음" in payload.decode()
    assert not (cache / "R200").exists()
    app.close()


def test_pages_do_not_touch_network_sampler_or_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_args, **_kwargs):
        raise AssertionError("network or sampling")

    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr("urllib.request.urlopen", boom)
    monkeypatch.setattr("dart_parser.gold.sampler.build_sample", boom)
    monkeypatch.setattr("dart_parser.gold.snapshots.capture", boom)
    catalog, gold_path, cache = _seed(tmp_path)
    app = ReviewApplication(catalog, gold_path, cache)
    list_status, _headers, _body = _request(app, "/")
    doc_status, _headers, _body = _request(app, "/doc/R100/D100")
    source_status, _headers, _body = _request(app, "/doc/R100/D100/source")
    post_status, _headers, _body = _request(app, "/doc/R100/D100", method="POST")
    assert list_status == "200 OK"
    assert doc_status == "200 OK"
    assert source_status == "200 OK"
    assert post_status.startswith("405")
    app.close()


def test_cli_takes_catalog_and_gold_as_arguments() -> None:
    args = parse_args(["--catalog", r"C:\tmp\catalog.db", "--gold", r"C:\tmp\gold.db"])
    assert args.catalog == Path(r"C:\tmp\catalog.db")
    assert args.gold == Path(r"C:\tmp\gold.db")
    with pytest.raises(SystemExit):
        parse_args([])
