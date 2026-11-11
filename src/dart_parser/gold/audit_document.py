"""감사보고서 문서명 판정.

파이썬과 SQLite 조건이 같은 순서로 접두를 지우고 같은 부분 문자열을 본다.
"""

from __future__ import annotations

from typing import Literal

from dart_parser.normalizer.cleaner import normalize_text

AuditScope = Literal["separate", "consolidated"]

_TAGS = ("[기재정정]", "[첨부정정]", "[정정]")
# normalize_text가 공백으로 바꾸거나 지우는 문자. SQL은 그 함수를 호출하지 않는다.
_SQL_STRIP = (
    " ",
    "\t",
    "\r",
    "\n",
    "\u00a0",
    "\u3000",
    "\u200b",
    "\u200c",
    "\u200d",
    "\u2060",
    "\ufeff",
    "\u2002",
    "\u2003",
    "\u2009",
    "\u200a",
    "\u202f",
    "\u205f",
    "\f",
    "\v",
)


def _prepare(name: str | None) -> str:
    """비교용 문서명. 비어 있으면 빈 문자열."""
    text = normalize_text(name).replace(" ", "")
    for tag in _TAGS:
        text = text.replace(tag, "")
    return text


def classify_audit_document(name: str | None) -> AuditScope | None:
    """감사보고서 문서면 별도·연결을, 아니면 None을 돌려준다."""
    text = _prepare(name)
    if "감사의감사" in text or "감사보고서" not in text:
        return None
    if "연결" in text:
        return "consolidated"
    return "separate"


def _ident(column: str) -> str:
    """`document_name` 또는 `e.document_name`만 허용한다."""
    parts = column.split(".")
    if not 1 <= len(parts) <= 2 or not all(part.isidentifier() for part in parts):
        raise ValueError(f"document name column: {column}")
    return column


def normalized_document_sql(column: str) -> str:
    """문서명에서 공백과 정정 접두를 뺀 SQL 식."""
    expr = f"IFNULL({_ident(column)}, '')"
    for ch in _SQL_STRIP:
        expr = f"REPLACE({expr}, char({ord(ch)}), '')"
    for tag in _TAGS:
        expr = f"REPLACE({expr}, '{tag}', '')"
    return expr


def audit_document_predicate_sql(column: str) -> str:
    """감사보고서 문서면 참인 SQL 식."""
    norm = normalized_document_sql(column)
    return f"(INSTR({norm}, '감사의감사') = 0 AND INSTR({norm}, '감사보고서') > 0)"


def audit_document_consolidated_sql(column: str) -> str:
    """통과한 문서명에 `연결`이 있으면 참인 SQL 식."""
    norm = normalized_document_sql(column)
    return f"({audit_document_predicate_sql(column)} AND INSTR({norm}, '연결') > 0)"
