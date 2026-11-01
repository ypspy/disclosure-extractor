"""원문 캐시 계획. 네트워크는 쓰지 않는다."""

from __future__ import annotations

import socket

from dart_parser.gold.cache import load_section_html, plan_cache
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


def test_load_section_offline(tmp_path, monkeypatch) -> None:
    def _blocked(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr(socket, "socket", _blocked)
    assert load_section_html(tmp_path / "cache", "000", {"ele_id": "1"}) is None
