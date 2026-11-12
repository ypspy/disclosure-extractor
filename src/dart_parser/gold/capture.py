"""클릭한 공시 글자를 골드 칸 값으로 바꾼다."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any, Literal

from dart_parser.fallback.schemas import ACCOUNT_KEYS, Amount
from dart_parser.gold.subjects import going_concern_value
from dart_parser.normalizer.cleaner import normalize_text
from dart_parser.normalizer.numeric import to_number
from dart_parser.parser.lexicon import HOUR_METRIC_ALIASES, HOUR_ROLE_ALIASES

BS_ACCOUNTS: tuple[str, ...] = ACCOUNT_KEYS[:10]
IS_ACCOUNTS: tuple[str, ...] = ACCOUNT_KEYS[10:]
SCALES = frozenset({1, 1000, 1_000_000, 100_000_000})
_OPINIONS = ("부적정", "한정", "거절", "적정")
_GAAP = ("K-IFRS", "K-GAAP")
_DATE_RE = re.compile(r"(\d{4})\s*(?:년|[.\-])\s*(\d{1,2})\s*(?:월|[.\-])\s*(\d{1,2})\s*일?")
_ACTIVITY_LABELS = {
    "planning": "전반감사계획",
    "fieldwork": "현장감사",
    "tcwg_communication": "지배기구와의 커뮤니케이션",
    "expert": "외부전문가",
    "inventory_observation.date": "재고자산 실사 · 시기",
    "inventory_observation.place": "재고자산 실사 · 장소",
    "inventory_observation.target": "재고자산 실사 · 대상",
    "financial_asset_observation.date": "금융자산 실사 · 시기",
    "financial_asset_observation.place": "금융자산 실사 · 장소",
    "financial_asset_observation.target": "금융자산 실사 · 대상",
    "external_confirmations.financial": "외부조회 · 금융거래",
    "external_confirmations.receivables_payables": "외부조회 · 채권채무",
    "external_confirmations.legal": "외부조회 · 변호사",
    "external_confirmations.other": "외부조회 · 기타",
}
_ACCOUNT_LABELS = {
    "total_asset": "자산총계",
    "current_asset": "유동자산",
    "inventory": "재고",
    "receivable": "매출채권",
    "long_term_receivable": "장기매출채권",
    "contract_asset": "계약자산",
    "unbilled": "미청구공사",
    "total_liability": "부채총계",
    "current_liability": "유동부채",
    "total_equity": "자본총계",
    "revenue": "매출액",
    "operating_income": "영업이익",
    "net_income": "당기순손익",
}
_COVER = (
    ("company_name", "회사명"),
    ("document_title", "문서 제목"),
    ("fiscal_term", "기수"),
    ("current_period", "보고기간"),
    ("auditor", "감사인"),
)
_OPINION = (
    ("opinion", "감사의견"),
    ("gaap", "회계기준"),
    ("audit_report_date", "감사보고서일"),
)


@dataclass(frozen=True)
class CaptureRow:
    group: str
    bundle: str
    subject: str
    label: str


def money_group(bundle: str, subject: str) -> Literal["bs", "is"] | None:
    account, separator, period = subject.partition("@")
    if bundle != "accounts" or separator != "@" or period not in {"current", "prior"}:
        return None
    if account in BS_ACCOUNTS:
        return "bs"
    if account in IS_ACCOUNTS:
        return "is"
    return None


def known_subject(bundle: str, subject: str) -> bool:
    return any(row.bundle == bundle and row.subject == subject for row in capture_rows())


def capture_rows() -> tuple[CaptureRow, ...]:
    rows: list[CaptureRow] = [
        CaptureRow("표지", bundle, "value", label) for bundle, label in _COVER
    ]
    rows.extend(CaptureRow("의견", bundle, "value", label) for bundle, label in _OPINION)
    rows.append(CaptureRow("의견", "going_concern", "value", "계속기업"))
    for account in BS_ACCOUNTS:
        for period, when in (("current", "당기"), ("prior", "전기")):
            rows.append(
                CaptureRow(
                    "재무상태표",
                    "accounts",
                    f"{account}@{period}",
                    f"{_ACCOUNT_LABELS[account]} · {when}",
                )
            )
    for account in IS_ACCOUNTS:
        for period, when in (("current", "당기"), ("prior", "전기")):
            rows.append(
                CaptureRow(
                    "손익계산서",
                    "accounts",
                    f"{account}@{period}",
                    f"{_ACCOUNT_LABELS[account]} · {when}",
                )
            )
    rows.append(CaptureRow("주석 목차", "notes_toc", "value", "주석 목차"))
    for role, role_names in HOUR_ROLE_ALIASES.items():
        for metric, metric_names in HOUR_METRIC_ALIASES.items():
            for period, when in (("current", "당기"), ("prior", "전기")):
                rows.append(
                    CaptureRow(
                        "감사시간",
                        "hours",
                        f"{role}|{metric}|{period}",
                        f"{role_names[0]} · {metric_names[0]} · {when}",
                    )
                )
    rows.extend(
        CaptureRow("실시내용", "activities", subject, label)
        for subject, label in _ACTIVITY_LABELS.items()
    )
    rows.append(CaptureRow("커뮤니케이션", "communications", "has_audit_committee", "감사위원회"))
    rows.append(CaptureRow("커뮤니케이션", "communications", "items", "회차"))
    rows.append(CaptureRow("내부회계", "icfr", "engagement", "인증수준"))
    rows.append(CaptureRow("내부회계", "icfr", "opinion", "내부회계 의견"))
    rows.append(CaptureRow("종속기업", "subsidiary", "value", "종속기업 수"))
    return tuple(rows)


def section_jumps() -> dict[str, tuple[str, ...]]:
    return {
        "표지": (),
        "의견": ("감사의견",),
        "재무상태표": ("재무상태표", "대차대조표"),
        "손익계산서": ("손익계산서", "포괄손익계산서"),
        "주석 목차": ("주석",),
        "감사시간": ("감사시간",),
        "실시내용": ("감사실시내용",),
        "커뮤니케이션": ("커뮤니케이션",),
        "내부회계": ("내부회계",),
        "종속기업": ("종속기업",),
    }


@dataclass(frozen=True)
class FieldControl:
    kind: str
    options: tuple[tuple[str, str], ...] = ()
    blocked: str = ""


def field_control(
    bundle: str,
    subject: str,
    *,
    icfr_engagement: str | None = None,
) -> FieldControl:
    if not known_subject(bundle, subject):
        return FieldControl("text")
    if bundle == "document_title":
        return FieldControl(
            "enum",
            (("감사보고서", "감사보고서"), ("연결감사보고서", "연결감사보고서")),
        )
    if bundle == "opinion":
        return FieldControl(
            "enum",
            tuple((item, item) for item in ("적정", "한정", "부적정", "거절")),
        )
    if bundle == "gaap":
        return FieldControl("enum", (("K-IFRS", "K-IFRS"), ("K-GAAP", "K-GAAP")))
    if bundle == "icfr" and subject == "engagement":
        return FieldControl("enum", (("audit", "감사"), ("review", "검토")))
    if bundle == "icfr" and subject == "opinion":
        if icfr_engagement == "audit":
            options = ("적정", "부적정", "거절")
        elif icfr_engagement == "review":
            options = ("적정", "한정", "거절", "중요한 취약점")
        else:
            return FieldControl("enum", blocked="인증수준을 먼저 저장하세요")
        return FieldControl("enum", tuple((item, item) for item in options))
    if bundle == "going_concern":
        return FieldControl("enum", (("1", "불확실성 있음"), ("0", "불확실성 없음")))
    if bundle == "communications" and subject == "has_audit_committee":
        return FieldControl("enum", (("true", "있음"), ("false", "없음")))
    if bundle == "audit_report_date":
        return FieldControl("date")
    if bundle == "current_period":
        return FieldControl("period")
    if money_group(bundle, subject) is not None:
        return FieldControl("amount")
    if bundle in {"hours", "subsidiary"}:
        return FieldControl("number")
    if bundle == "notes_toc":
        return FieldControl("note")
    if bundle == "communications" and subject == "items":
        return FieldControl("round")
    return FieldControl("text")


def confirm_value(
    bundle: str,
    subject: str,
    evidence: str,
    confirmed: Any,
    *,
    unit_scale: int | None = None,
    icfr_engagement: str | None = None,
) -> Any | None:
    if not known_subject(bundle, subject):
        return None
    if not normalize_text(evidence):
        return None
    control = field_control(bundle, subject, icfr_engagement=icfr_engagement)
    if control.kind == "enum":
        return _confirm_enum(bundle, subject, control, confirmed)
    if control.kind in {"text", "note"}:
        return _confirmed_text(confirmed)
    if control.kind == "date":
        return _iso_date(confirmed)
    if control.kind == "period":
        return _confirm_period(confirmed)
    if control.kind == "amount":
        return _confirm_amount(evidence, confirmed, unit_scale)
    if control.kind == "number":
        return _finite_number(confirmed)
    if control.kind == "round":
        return _confirm_round(confirmed)
    return None


def parse_click(
    bundle: str,
    subject: str,
    text: str,
    *,
    unit_scale: int | None = None,
    icfr_engagement: str | None = None,
) -> Any | None:
    cleaned = normalize_text(text)
    if not cleaned or not known_subject(bundle, subject):
        return None
    if bundle == "accounts":
        return _amount(text, unit_scale)
    if bundle in {"hours", "subsidiary"}:
        return to_number(text)
    if bundle == "opinion":
        return _one(_hits(cleaned, _OPINIONS))
    if bundle == "gaap":
        return _one(_hits(cleaned, _GAAP))
    if bundle == "document_title":
        if "연결감사보고서" in cleaned:
            return "연결감사보고서"
        if "감사보고서" in cleaned:
            return "감사보고서"
        return None
    if bundle == "audit_report_date":
        return _one(_dates(cleaned))
    if bundle == "current_period":
        found = _dates(cleaned)
        if len(found) != 2:
            return None
        return {"start": found[0], "end": found[1]}
    if bundle == "icfr" and subject == "engagement":
        return _icfr_engagement(cleaned)
    if bundle == "icfr" and subject == "opinion":
        allowed = {
            "audit": ("부적정", "거절", "적정"),
            "review": ("중요한 취약점", "한정", "거절", "적정"),
        }.get(icfr_engagement or "")
        if allowed is None:
            return None
        return _one(_hits(cleaned, allowed))
    if bundle == "communications" and subject == "has_audit_committee":
        chosen = _one(_hits(cleaned, ("있음", "없음")))
        if chosen == "있음":
            return True
        if chosen == "없음":
            return False
        return None
    if bundle == "communications" and subject == "items":
        found = _dates(cleaned)
        item: dict[str, Any] = {"raw": cleaned}
        if len(found) == 1:
            item["date"] = found[0]
        return item
    if bundle == "going_concern":
        return going_concern_value(text)
    if bundle == "notes_toc" or bundle in {"company_name", "fiscal_term", "auditor", "activities"}:
        return cleaned
    return None


def _amount(text: str, unit_scale: int | None) -> dict[str, Any] | None:
    if unit_scale not in SCALES:
        return None
    amount = Amount.from_cell(text, unit_scale)
    if amount.value is None:
        return None
    return {
        "raw": amount.raw,
        "value": amount.value,
        "unit_scale": amount.unit_scale,
        "value_won": amount.value_won,
    }


def _dates(text: str) -> list[str]:
    found: list[str] = []
    for year, month, day in _DATE_RE.findall(text):
        try:
            parsed = dt.date(int(year), int(month), int(day))
        except ValueError:
            continue
        found.append(parsed.isoformat())
    return found


def _hits(text: str, phrases: tuple[str, ...]) -> list[str]:
    occupied = [False] * len(text)
    hits: list[str] = []
    for phrase in sorted(phrases, key=len, reverse=True):
        start = 0
        while True:
            index = text.find(phrase, start)
            if index < 0:
                break
            span = range(index, index + len(phrase))
            if not any(occupied[pos] for pos in span):
                for pos in span:
                    occupied[pos] = True
                hits.append(phrase)
            start = index + len(phrase)
    return hits


def _icfr_engagement(text: str) -> str | None:
    """감사인·감사보고서·감사위원회 안의 감사는 업무로 세지 않는다."""
    masked = text
    for token in ("감사위원회", "감사보고서", "감사인"):
        masked = masked.replace(token, " ")
    chosen = _one(_hits(masked, ("검토", "감사")))
    return {"감사": "audit", "검토": "review"}.get(chosen or "")


def _one(found: list[str]) -> str | None:
    if len(found) != 1:
        return None
    return found[0]


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        return None
    return number


def _iso_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.date.fromisoformat(value).isoformat()
    except ValueError:
        return None
    if parsed != value:
        return None
    return parsed


def _confirm_enum(
    bundle: str,
    subject: str,
    control: FieldControl,
    confirmed: Any,
) -> Any | None:
    if control.blocked:
        return None
    if bundle == "going_concern":
        if type(confirmed) is int and confirmed in {0, 1}:
            return confirmed
        return None
    if bundle == "communications" and subject == "has_audit_committee":
        if confirmed is True or confirmed is False:
            return confirmed
        return None
    allowed = {value for value, _label in control.options}
    if isinstance(confirmed, str) and confirmed in allowed:
        return confirmed
    return None


def _confirmed_text(confirmed: Any) -> str | None:
    if not isinstance(confirmed, str):
        return None
    cleaned = normalize_text(confirmed)
    if not cleaned:
        return None
    return cleaned


def _confirm_period(confirmed: Any) -> dict[str, str] | None:
    if not isinstance(confirmed, dict):
        return None
    start = _iso_date(confirmed.get("start"))
    end = _iso_date(confirmed.get("end"))
    if start is None or end is None:
        return None
    return {"start": start, "end": end}


def _confirm_amount(
    evidence: str,
    confirmed: Any,
    unit_scale: int | None,
) -> dict[str, Any] | None:
    if unit_scale not in SCALES:
        return None
    number = _finite_number(confirmed)
    if number is None:
        return None
    return {
        "raw": evidence,
        "value": number,
        "unit_scale": unit_scale,
        "value_won": number * unit_scale,
    }


def _confirm_round(confirmed: Any) -> dict[str, str] | None:
    if not isinstance(confirmed, dict):
        return None
    raw = confirmed.get("raw")
    if not isinstance(raw, str):
        return None
    cleaned = normalize_text(raw)
    if not cleaned:
        return None
    item = {"raw": cleaned}
    date = confirmed.get("date")
    if "date" not in confirmed or date in {"", None}:
        return item
    parsed = _iso_date(date)
    if parsed is None:
        return None
    item["date"] = parsed
    return item
