"""골드 리뷰 앱 뼈대. 임시 DB와 HTML만 쓰고 네트워크는 열지 않는다."""

from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path
from wsgiref.util import setup_testing_defaults

import pytest

from dart_parser.gold.app import (
    LOOPBACK,
    ReviewApplication,
    _filing_meta,
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
        ) VALUES (
            'run', 'seed', '2026-11-06T00:00:00+00:00', 'x', NULL,
            '{"extractor_version": "0.1.0", "extractor_commit": "abc123"}', '{}'
        )
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


def _catalog_names(conn: sqlite3.Connection) -> set[str]:
    return {str(row[1]) for row in conn.execute("PRAGMA database_list")}


def _catalog_is_open(catalog: Path) -> bool:
    """이 프로세스가 카탈로그 파일을 아직 열고 있으면 True."""
    fd_dir = Path("/proc/self/fd")
    if not fd_dir.is_dir():
        return False
    target = catalog.resolve()
    for entry in fd_dir.iterdir():
        try:
            linked = entry.readlink()
        except OSError:
            continue
        if linked == target:
            return True
    return False


def _insert_filing(catalog: Path, rcept_no: str) -> None:
    conn = sqlite3.connect(catalog)
    try:
        conn.execute(
            """
            INSERT INTO disclosures (rcept_no, corp_code, report_nm, rcept_dt)
            VALUES (?, 'C0001', '감사보고서', '20240315')
            """,
            (rcept_no,),
        )
        conn.commit()
    finally:
        conn.close()


def test_app_reads_catalog_meta_without_attaching_it(tmp_path: Path) -> None:
    catalog, gold_path, cache = _seed(tmp_path)
    _insert_filing(catalog, "R100")
    app = ReviewApplication(catalog, gold_path, cache)
    try:
        assert "cat" not in _catalog_names(app.store.conn)
        status, _headers, body = _request(app, "/doc/R100/D100")
        page = body.decode()
        assert status == "200 OK"
        assert "표본" in page
        assert "감사보고서" in page
        assert "20240315" in page
        company, report, filed = _filing_meta(app.store, "R100")
        assert (company, report, filed) == ("표본", "감사보고서", "20240315")
        assert "cat" not in _catalog_names(app.store.conn)
        assert not _catalog_is_open(catalog)
    finally:
        app.close()


def test_catalog_write_succeeds_while_the_app_is_open(tmp_path: Path) -> None:
    catalog, gold_path, cache = _seed(tmp_path)
    _insert_filing(catalog, "R100")
    app = ReviewApplication(catalog, gold_path, cache)
    try:
        status, _headers, body = _request(app, "/doc/R100/D100")
        assert status == "200 OK"
        assert "표본" in body.decode()
        assert "cat" not in _catalog_names(app.store.conn)
        assert not _catalog_is_open(catalog)
        writer = sqlite3.connect(catalog, timeout=1.0)
        try:
            writer.execute("BEGIN IMMEDIATE")
            writer.execute(
                "INSERT INTO disclosures (rcept_no, corp_code) VALUES ('write-ok', 'C0001')"
            )
            writer.execute("COMMIT")
            found = writer.execute(
                "SELECT rcept_no FROM disclosures WHERE rcept_no = 'write-ok'"
            ).fetchone()
        finally:
            writer.close()
        assert found is not None
        assert not _catalog_is_open(catalog)
    finally:
        app.close()


def test_catalog_connection_closes_after_the_request(tmp_path: Path) -> None:
    catalog, gold_path, cache = _seed(tmp_path)
    app = ReviewApplication(catalog, gold_path, cache)
    try:
        company, _report, filed = _filing_meta(app.store, "20240101000001")
        assert (company, filed) == ("표본", "20240315")
        assert "cat" not in _catalog_names(app.store.conn)
        assert not _catalog_is_open(catalog)
        app.store.catalog_path = tmp_path / "missing-catalog.db"
        assert _filing_meta(app.store, "20240101000001") == ("", "", "")
        assert not _catalog_is_open(app.store.catalog_path)
    finally:
        app.close()
    with pytest.raises(sqlite3.ProgrammingError):
        app.store.conn.execute("SELECT 1")


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


def test_cli_takes_catalog_and_gold_as_arguments() -> None:
    args = parse_args(["--catalog", r"C:\tmp\catalog.db", "--gold", r"C:\tmp\gold.db"])
    assert args.catalog == Path(r"C:\tmp\catalog.db")
    assert args.gold == Path(r"C:\tmp\gold.db")
    with pytest.raises(SystemExit):
        parse_args([])
