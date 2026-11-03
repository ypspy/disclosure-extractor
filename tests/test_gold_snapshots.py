"""스냅샷은 캐시 HTML을 추출기에 넣은 StandardExtraction이다."""

from __future__ import annotations

from dart_parser.gold.db import migrate, open_gold
from dart_parser.gold.snapshots import capture, load_snapshot

_HTML = """
<p class="section-1">표지</p>
주식회사 골드샘플
<h2>감사보고서</h2>
<p>제 10 기</p>
<p class="section-1">독립된 감사인의 감사보고서</p>
<p>한영회계법인 대표이사</p>
<p>삼일회계법인의 감사의견으로는 재무제표가 한국채택국제회계기준에 따라
적정하게 표시하고 있습니다.</p>
<p>2024년 3월 15일</p>
"""


def _sample(tmp_path, html: str | None):
    conn = open_gold(tmp_path / "gold.db", None)
    migrate(conn)
    conn.execute(
        """
        INSERT INTO gold_runs (
            run_id, seed, created_at, population_sql_sha, db_snapshot, params, stats
        ) VALUES ('run', 'seed', '2026-11-01T00:00:00+00:00', 'x', '{}', '{}', '{}')
        """
    )
    conn.execute(
        """
        INSERT INTO gold_samples (
            run_id, rcept_no, dcm_no, period, stratum, stratum_weight, sample_hash,
            mode, role, queue_order, status, meta
        ) VALUES ('run', 'R100', 'D100', 'P7', 's', 1, 'h', 'prefill', 'main', 1, 'todo', '{}')
        """
    )
    conn.commit()
    if html is not None:
        folder = tmp_path / "cache" / "R100"
        folder.mkdir(parents=True)
        (folder / "main.html").write_text(html, encoding="utf-8")
    return conn


def test_capture_runs_pipeline_on_cached_html(tmp_path, monkeypatch) -> None:
    def _blocked(*_args, **_kwargs):
        raise AssertionError("slm")

    monkeypatch.setattr("dart_parser.pipeline.extract_with_slm", _blocked)
    conn = _sample(tmp_path, _HTML)
    saved = capture(
        conn,
        "run",
        tmp_path / "cache",
        version="0.1.0",
        commit="abc123",
    )
    assert saved == 1
    payload = load_snapshot(conn, "0.1.0", "R100", "D100")
    assert payload is not None
    assert payload["commit"] == "abc123"
    assert payload["extractor_version"] == "0.1.0"
    extraction = payload["extraction"]
    assert extraction["rcept_no"] == "R100"
    assert extraction["document_title"]["value"] == "감사보고서"
    assert extraction["opinion"]["value"] in {"적정", "한정", "부적정", "거절"}
    assert capture(conn, "run", tmp_path / "cache", version="0.1.0", commit="abc123") == 0
