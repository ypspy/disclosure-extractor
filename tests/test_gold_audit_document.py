"""감사보고서 문서명 판정은 파이썬과 SQL이 같다."""

from __future__ import annotations

import sqlite3

from dart_parser.gold.audit_document import (
    audit_document_consolidated_sql,
    audit_document_predicate_sql,
    classify_audit_document,
)

_NAMES = (
    ("감사보고서", "separate"),
    ("[정정] 감사보고서", "separate"),
    ("연결감사보고서", "consolidated"),
    ("[정정] 연결감사보고서", "consolidated"),
    ("외국법인등의연결감사보고서", "consolidated"),
    ("사업보고서", None),
    ("정관", None),
    ("기업개황자료", None),
    ("영업보고서", None),
    ("감사의감사보고서", None),
    ("감사\u00a0보고서", "separate"),
    ("감사\u3000보고서", "separate"),
    ("감사\u200b보고서", "separate"),
    (None, None),
    ("", None),
)


def test_classify_audit_document_name_table() -> None:
    for name, expected in _NAMES:
        assert classify_audit_document(name) == expected


def test_sql_predicate_matches_python() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE docs (document_name TEXT)")
    predicate = audit_document_predicate_sql("document_name")
    consolidated = audit_document_consolidated_sql("document_name")
    for name, expected in _NAMES:
        conn.execute("DELETE FROM docs")
        conn.execute("INSERT INTO docs (document_name) VALUES (?)", (name,))
        hit, cons = conn.execute(
            f"SELECT {predicate}, {consolidated} FROM docs"
        ).fetchone()
        assert bool(hit) is (expected is not None)
        assert bool(cons) is (expected == "consolidated")
