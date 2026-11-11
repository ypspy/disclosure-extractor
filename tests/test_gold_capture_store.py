"""입수 행은 gold_captures에만 쌓인다."""

from __future__ import annotations

import json
import sqlite3

import pytest

from dart_parser.gold.capture_store import (
    clear_capture,
    load_captures,
    load_units,
    save_capture,
    set_capture_status,
    set_unit,
)
from dart_parser.gold.db import migrate, open_gold


def _conn(tmp_path):
    conn = open_gold(tmp_path / "gold.db", None)
    migrate(conn)
    return conn


def test_click_stores_an_amount_and_ignores_an_unreadable_cell(tmp_path) -> None:
    conn = _conn(tmp_path)
    assert set_unit(conn, "R", "D", "bs", 1_000_000)
    assert save_capture(conn, "R", "D", "accounts", "total_asset@current", "19,506")
    assert not save_capture(conn, "R", "D", "accounts", "current_asset@current", "없음")
    row = load_captures(conn, "R", "D")[("accounts", "total_asset@current")]
    assert row["status"] == "found"
    assert json.loads(row["value"])["value_won"] == 19_506_000_000.0
    assert row["evidence"] == "19,506"
    assert ("accounts", "current_asset@current") not in load_captures(conn, "R", "D")
    assert conn.execute("SELECT count(*) FROM gold_labels").fetchone()[0] == 0


def test_amount_click_before_a_unit_does_not_insert(tmp_path) -> None:
    conn = _conn(tmp_path)
    assert not save_capture(conn, "R", "D", "accounts", "revenue@current", "10")
    assert load_captures(conn, "R", "D") == {}


def test_changing_the_unit_recomputes_only_scale_and_won(tmp_path) -> None:
    conn = _conn(tmp_path)
    set_unit(conn, "R", "D", "is", 1_000)
    save_capture(conn, "R", "D", "accounts", "revenue@current", "10")
    set_unit(conn, "R", "D", "bs", 1)
    save_capture(conn, "R", "D", "accounts", "total_asset@current", "5")
    assert set_unit(conn, "R", "D", "is", 1_000_000)
    revenue = json.loads(load_captures(conn, "R", "D")[("accounts", "revenue@current")]["value"])
    asset = json.loads(load_captures(conn, "R", "D")[("accounts", "total_asset@current")]["value"])
    assert revenue["value"] == 10.0
    assert revenue["unit_scale"] == 1_000_000
    assert revenue["value_won"] == 10_000_000.0
    assert asset["unit_scale"] == 1
    assert load_units(conn, "R", "D") == {"is": 1_000_000, "bs": 1}


def test_changed_icfr_engagement_drops_the_opinion(tmp_path) -> None:
    conn = _conn(tmp_path)
    assert save_capture(conn, "R", "D", "icfr", "engagement", "내부회계관리제도 검토")
    assert save_capture(conn, "R", "D", "icfr", "opinion", "한정")
    assert not save_capture(conn, "R", "D", "icfr", "engagement", "감사 및 검토")
    assert ("icfr", "opinion") in load_captures(conn, "R", "D")
    assert save_capture(conn, "R", "D", "icfr", "engagement", "내부회계관리제도 검토")
    assert ("icfr", "opinion") in load_captures(conn, "R", "D")
    assert save_capture(conn, "R", "D", "icfr", "engagement", "내부회계관리제도 감사")
    saved = load_captures(conn, "R", "D")
    assert json.loads(saved[("icfr", "engagement")]["value"]) == "audit"
    assert ("icfr", "opinion") not in saved


def test_absent_status_and_clear(tmp_path) -> None:
    conn = _conn(tmp_path)
    assert set_capture_status(conn, "R", "D", "subsidiary", "value", "not_applicable")
    row = load_captures(conn, "R", "D")[("subsidiary", "value")]
    assert row["status"] == "not_applicable"
    assert row["value"] is None
    clear_capture(conn, "R", "D", "subsidiary", "value")
    assert load_captures(conn, "R", "D") == {}
    assert not set_capture_status(conn, "R", "D", "subsidiary", "value", "found")


def test_notes_and_rounds_append(tmp_path) -> None:
    conn = _conn(tmp_path)
    save_capture(conn, "R", "D", "notes_toc", "value", "일반사항")
    save_capture(conn, "R", "D", "notes_toc", "value", "재고자산")
    notes = json.loads(load_captures(conn, "R", "D")[("notes_toc", "value")]["value"])
    assert notes == {"count": 2, "titles": ["일반사항", "재고자산"]}
    save_capture(conn, "R", "D", "communications", "items", "2017년 3월 2일 회의")
    save_capture(conn, "R", "D", "communications", "items", "둘째 회의")
    items = json.loads(load_captures(conn, "R", "D")[("communications", "items")]["value"])
    assert [item["round"] for item in items] == [1, 2]
    assert items[0]["date"] == "2017-03-02"


def test_notes_reject_a_duplicate_and_drop_one_title(tmp_path) -> None:
    conn = _conn(tmp_path)
    save_capture(conn, "R", "D", "notes_toc", "value", "일반사항")
    assert save_capture(conn, "R", "D", "notes_toc", "value", "  일반사항 ")
    save_capture(conn, "R", "D", "notes_toc", "value", "재고자산")
    notes = json.loads(load_captures(conn, "R", "D")[("notes_toc", "value")]["value"])
    assert notes == {"count": 2, "titles": ["일반사항", "재고자산"]}
    from dart_parser.gold.capture_store import remove_list_item

    assert remove_list_item(conn, "R", "D", "notes_toc", "value", 0)
    notes = json.loads(load_captures(conn, "R", "D")[("notes_toc", "value")]["value"])
    assert notes == {"count": 1, "titles": ["재고자산"]}
    history = conn.execute(
        "SELECT value, action FROM gold_capture_history ORDER BY rowid"
    ).fetchall()
    assert json.loads(history[-1][0])["titles"] == ["일반사항", "재고자산"]
    assert history[-1][1] == "update"


def test_communication_rounds_skip_duplicates_and_renumber(tmp_path) -> None:
    conn = _conn(tmp_path)
    save_capture(conn, "R", "D", "communications", "items", "2017년 3월 2일 회의")
    assert save_capture(conn, "R", "D", "communications", "items", "  2017년 3월 2일 회의 ")
    save_capture(conn, "R", "D", "communications", "items", "둘째 회의")
    from dart_parser.gold.capture_store import remove_list_item

    assert remove_list_item(conn, "R", "D", "communications", "items", 0)
    items = json.loads(load_captures(conn, "R", "D")[("communications", "items")]["value"])
    assert [item["round"] for item in items] == [1]
    assert items[0]["raw"] == "둘째 회의"


def test_overwrite_and_clear_keep_history(tmp_path) -> None:
    conn = _conn(tmp_path)
    save_capture(conn, "R", "D", "company_name", "value", "가나")
    save_capture(conn, "R", "D", "company_name", "value", "다라")
    clear_capture(conn, "R", "D", "company_name", "value")
    history = conn.execute(
        "SELECT value, action FROM gold_capture_history ORDER BY rowid"
    ).fetchall()
    assert [json.loads(row[0]) for row in history] == ["가나", "다라"]
    assert [row[1] for row in history] == ["update", "clear"]
    assert load_captures(conn, "R", "D") == {}


def test_failed_overwrite_rolls_back_capture_and_history(tmp_path) -> None:
    conn = _conn(tmp_path)
    save_capture(conn, "R", "D", "company_name", "value", "가나")
    conn.execute(
        """
        CREATE TRIGGER boom BEFORE UPDATE ON gold_captures
        BEGIN
            SELECT RAISE(ABORT, 'boom');
        END
        """
    )
    with pytest.raises(sqlite3.Error):
        save_capture(conn, "R", "D", "company_name", "value", "다라")
    row = load_captures(conn, "R", "D")[("company_name", "value")]
    assert json.loads(row["value"]) == "가나"
    assert conn.execute("SELECT count(*) FROM gold_capture_history").fetchone()[0] == 0
