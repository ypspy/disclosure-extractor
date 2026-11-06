"""원문 캐시 계획. 네트워크는 쓰지 않는다."""

from __future__ import annotations

import socket

from dart_parser.gold.cache import load_section_html, plan_cache, read_cached_html
from gold_fixtures import first_rcept, run_sample


def _mk_box_doc(box, year: str, rcept_no: str) -> None:
    doc = box / year / rcept_no
    doc.mkdir(parents=True)
    (doc / "main.html").write_text("<html><body>원문</body></html>", encoding="utf-8")
    (doc / "toc.json").write_text("{}", encoding="utf-8")


def test_plan_classifies(tmp_path) -> None:
    conn, run_id = run_sample(tmp_path, "x")
    box = tmp_path / "box"
    rcept_no = first_rcept(conn)
    _mk_box_doc(box, "2019", rcept_no)
    plan = plan_cache(conn, run_id, tmp_path / "cache", box)
    assert rcept_no in plan.from_box
    assert plan.missing


def test_read_cached_html_decodes_euc_kr(tmp_path) -> None:
    path = tmp_path / "page.html"
    path.write_bytes('<meta charset="euc-kr"><p>한글주식회사</p>'.encode("euc-kr"))
    loaded = read_cached_html(path)
    assert "한글주식회사" in loaded.text
    assert loaded.encoding_uncertain is False


def test_read_cached_html_marks_undecodable_bytes(tmp_path) -> None:
    path = tmp_path / "bad.html"
    path.write_bytes(b'<meta charset="euc-kr"><p>\xff\xff</p>')
    loaded = read_cached_html(path)
    assert loaded.encoding_uncertain is True
    assert loaded.text


def test_load_section_html_reads_euc_kr_from_the_section_file(tmp_path) -> None:
    folder = tmp_path / "R1"
    folder.mkdir()
    (folder / "toc.json").write_text('{"4": "bs.html"}', encoding="utf-8")
    (folder / "bs.html").write_bytes('<meta charset="euc-kr"><p>재무상태표</p>'.encode("euc-kr"))
    (folder / "main.html").write_text("<p>메인만</p>", encoding="utf-8")
    loaded = load_section_html(tmp_path, "R1", {"ele_id": "4"})
    assert loaded is not None
    assert "재무상태표" in loaded.text
    assert "메인만" not in loaded.text
    assert loaded.encoding_uncertain is False


def test_load_section_html_uses_the_dcm_directory(tmp_path) -> None:
    first = tmp_path / "R1" / "D1"
    second = tmp_path / "R1" / "D2"
    first.mkdir(parents=True)
    second.mkdir()
    (first / "toc.json").write_text('{"4": "bs.html"}', encoding="utf-8")
    (first / "bs.html").write_text("<p>디씨엠본문</p>", encoding="utf-8")
    (second / "bs.html").write_text("<p>다른본문</p>", encoding="utf-8")
    loaded = load_section_html(tmp_path, "R1", {"ele_id": "4"}, dcm_no="D1")
    assert loaded is not None
    assert "디씨엠본문" in loaded.text
    assert "다른본문" not in loaded.text


def test_load_section_offline(tmp_path, monkeypatch) -> None:
    def _blocked(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr(socket, "socket", _blocked)
    assert load_section_html(tmp_path / "cache", "000", {"ele_id": "1"}) is None
