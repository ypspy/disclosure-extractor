"""Korean aliases for the `standard` extraction task.

Keys match `docs/standard-extraction-items.md`. Aliases are matched via
`parser.anchor_matcher` after `normalize_text` / `canonical`.
"""

from __future__ import annotations

ACCOUNT_ALIASES: dict[str, list[str]] = {
    "total_asset": ["자산총계"],
    "current_asset": ["유동자산"],
    "inventory": ["재고자산", "재고"],
    "receivable": ["매출채권"],
    "long_term_receivable": ["장기매출채권"],
    "contract_asset": ["계약자산"],
    "unbilled": ["미청구공사"],
    "total_liability": ["부채총계"],
    "current_liability": ["유동부채"],
    "total_equity": ["자본총계"],
    "revenue": ["매출액", "매출"],
    "operating_income": ["영업이익", "영업손실"],
    "net_income": ["당기순이익", "당기순손실", "당기순손익"],
}

HOUR_ROLE_ALIASES: dict[str, list[str]] = {
    "eqcr": ["품질관리검토자"],
    "engagement_partner": ["업무수행이사"],
    "cpa": ["등록공인회계사"],
    "trainee": ["수습공인회계사"],
    "construction_expert": ["수주산업·건설계약 전문가", "수주산업 전문가"],
    "specialist": ["전산·가치평가·세무 전문가"],
    "total": ["합계"],
    "other": ["기타"],
}

HOUR_METRIC_ALIASES: dict[str, list[str]] = {
    "headcount": ["투입인원수"],
    "audit_hours": ["감사시간"],
    "interim_review": ["분·반기검토", "분반기검토"],
    "total": ["합계"],
}

HOUR_PERIOD_ALIASES: dict[str, list[str]] = {
    "current": ["당기"],
    "prior": ["전기"],
}

ACTIVITY_ALIASES: dict[str, list[str]] = {
    "planning": ["전반감사계획"],
    "fieldwork": ["현장감사"],
    "inventory_observation": ["재고자산 실사", "재고자산실사"],
    "financial_asset_observation": ["금융자산 실사", "금융자산실사"],
    "external_confirmations": ["외부조회"],
    "tcwg_communication": ["지배기구와의 커뮤니케이션", "지배기구 커뮤니케이션"],
    "expert": ["외부전문가"],
}

GAAP_ALIASES: dict[str, list[str]] = {
    "K-IFRS": ["한국채택국제회계기준", "K-IFRS", "KIFRS", "IFRS"],
    "K-GAAP": ["일반기업회계기준", "K-GAAP", "KGAAP"],
}

OPINION_ALIASES: dict[str, list[str]] = {
    "적정": ["적정"],
    "부적정": ["부적정"],
    "거절": ["거절", "의견거절"],
}

# Labels that must not be taken as the research accounts (see the standard items doc).
ACCOUNT_REJECT_SUBSTRINGS: dict[str, tuple[str, ...]] = {
    "*": ("부채와자본총계", "부채및자본총계"),
    "inventory": ("충당",),
    "revenue": ("매출원가", "계속", "중단", "귀속"),
    "operating_income": ("영업외", "계속", "중단", "귀속"),
    "net_income": ("계속", "중단", "귀속", "지배", "비지배", "총포괄"),
    "current_asset": ("비유동", "기타"),
    "current_liability": ("비유동", "기타", "유동화"),
    "receivable": ("비유동", "장기"),
}
