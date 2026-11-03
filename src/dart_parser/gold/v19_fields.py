"""v19 facts 행을 읽던 이름.

표본 쿼리는 이 버전으로 거르지 않는다. ``status_attr``은 예전 스냅샷 claim에만 쓴다.
"""

from __future__ import annotations

EXTRACTOR_VERSION = "audit_opinion.v19"

_BUNDLE_ROWS: tuple[tuple[str, str], ...] = (
    ("auditor", "auditor_status"),
    ("opinion", "opinion_status"),
    ("gaap", "gaap_status"),
    ("audit_report_date", "audit_report_date_status"),
    ("current_period", "current_period_status"),
    ("hours", "hours_status"),
    ("activities", "activities_status"),
    ("communications", "communications_status"),
    ("accounts", "accounts_status"),
    ("icfr", "icfr_status"),
    ("going_concern", "going_concern_status"),
    ("subsidiary", "subsidiary_status"),
)


BUNDLE_KEYS: tuple[str, ...] = tuple(row[0] for row in _BUNDLE_ROWS)


def status_attr(bundle: str) -> str:
    """Facts status column for a v19 bundle key."""
    for key, attr in _BUNDLE_ROWS:
        if key == bundle:
            return attr
    raise KeyError(bundle)
