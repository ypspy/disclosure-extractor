"""Pydantic v2 schemas for the `standard` extraction task.

Item keys and the three-way status (`missing` / `not_applicable` / `not_in_regime`)
are defined in `docs/standard-extraction-items.md`. Amounts always travel with
their scale; never store a scaled number without `unit_scale`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

from dart_parser.normalizer.numeric import to_number

T = TypeVar("T")

ACCOUNT_KEYS = (
    "total_asset",
    "current_asset",
    "inventory",
    "receivable",
    "long_term_receivable",
    "contract_asset",
    "unbilled",
    "total_liability",
    "current_liability",
    "total_equity",
    "revenue",
    "operating_income",
    "net_income",
)

ACTIVITY_KEYS = (
    "planning",
    "fieldwork",
    "inventory_observation",
    "financial_asset_observation",
    "external_confirmations",
    "tcwg_communication",
    "expert",
)


class ExtractionStatus(StrEnum):
    found = "found"
    missing = "missing"
    not_applicable = "not_applicable"
    not_in_regime = "not_in_regime"


class Amount(BaseModel):
    raw: str | None = None
    value: float | None = None
    unit_scale: int = 1
    value_won: float | None = None

    @classmethod
    def from_cell(cls, raw: str | None, unit_scale: int = 1) -> Amount:
        text = "" if raw is None else raw
        value = to_number(text)
        value_won = None if value is None else value * unit_scale
        return cls(raw=raw, value=value, unit_scale=unit_scale, value_won=value_won)


class Item(BaseModel, Generic[T]):
    status: ExtractionStatus = ExtractionStatus.missing
    value: T | None = None
    source: Literal["rule", "xbrl", "llm"] | None = None
    evidence: str | None = None


def found(
    value: T,
    *,
    source: Literal["rule", "xbrl", "llm"] = "rule",
    evidence: str | None = None,
) -> Item[T]:
    return Item(status=ExtractionStatus.found, value=value, source=source, evidence=evidence)


def item_missing() -> Item[None]:
    return Item(status=ExtractionStatus.missing)


def item_not_applicable() -> Item[None]:
    return Item(status=ExtractionStatus.not_applicable)


def item_not_in_regime() -> Item[None]:
    return Item(status=ExtractionStatus.not_in_regime)


class Period(BaseModel):
    start: str | None = None
    end: str | None = None
    raw: str | None = None


class Gaap(BaseModel):
    raw: str
    code: str | None = None


class HoursCell(BaseModel):
    role: str
    role_key: str | None = None
    metric: str
    metric_key: str | None = None
    period: Literal["current", "prior"] | None = None
    value: float | None = None
    unmapped: bool = False


class HoursTable(BaseModel):
    cells: list[HoursCell] = Field(default_factory=list)


class Observation(BaseModel):
    content: str | None = None
    date: str | None = None
    place: str | None = None
    target: str | None = None


class ExternalConfirmations(BaseModel):
    financial: str | None = None
    receivables_payables: str | None = None
    legal: str | None = None
    other: str | None = None


class Activities(BaseModel):
    planning: str | None = None
    fieldwork: str | None = None
    inventory_observation: Observation | None = None
    financial_asset_observation: Observation | None = None
    external_confirmations: ExternalConfirmations | None = None
    tcwg_communication: str | None = None
    expert: str | None = None


class CommunicationItem(BaseModel):
    round: int | None = None
    date: str | None = None
    raw: str | None = None


class Communications(BaseModel):
    has_audit_committee: bool | None = None
    items: list[CommunicationItem] = Field(default_factory=list)


class AccountLine(BaseModel):
    current: Amount | None = None
    prior: Amount | None = None


class Accounts(BaseModel):
    total_asset: AccountLine | None = None
    current_asset: AccountLine | None = None
    inventory: AccountLine | None = None
    receivable: AccountLine | None = None
    long_term_receivable: AccountLine | None = None
    contract_asset: AccountLine | None = None
    unbilled: AccountLine | None = None
    total_liability: AccountLine | None = None
    current_liability: AccountLine | None = None
    total_equity: AccountLine | None = None
    revenue: AccountLine | None = None
    operating_income: AccountLine | None = None
    net_income: AccountLine | None = None


class Icfr(BaseModel):
    icfr_engagement: Literal["audit", "review"] | None = None
    icfr_opinion_code: str | None = None
    icfr_status: ExtractionStatus = ExtractionStatus.missing


class Subsidiary(BaseModel):
    subsidiary_status: ExtractionStatus = ExtractionStatus.missing
    subsidiary_count: int | None = None


class NotesToc(BaseModel):
    count: int = 0
    titles: list[str] = Field(default_factory=list)


class DARTTableExtraction(BaseModel):
    """Generic table fallback schema used by the SLM client."""

    title: str
    unit: str
    headers: list[str]
    rows: list[dict[str, str | float | None]]


class StandardExtraction(BaseModel):
    model_config = {"extra": "forbid"}

    rcept_no: str | None = None
    fs_scope: Literal["separate", "consolidated"] | None = None
    source: Literal["rule", "xbrl", "hybrid", "llm"] | None = None

    company_name: Item[str] = Field(default_factory=Item)
    document_title: Item[str] = Field(default_factory=Item)
    fiscal_term: Item[str] = Field(default_factory=Item)

    auditor: Item[str] = Field(default_factory=Item)
    opinion: Item[str] = Field(default_factory=Item)
    gaap: Item[Gaap] = Field(default_factory=Item)
    audit_report_date: Item[str] = Field(default_factory=Item)
    current_period: Item[Period] = Field(default_factory=Item)
    hours: Item[HoursTable] = Field(default_factory=Item)
    activities: Item[Activities] = Field(default_factory=Item)
    communications: Item[Communications] = Field(default_factory=Item)
    accounts: Item[Accounts] = Field(default_factory=Item)
    icfr: Icfr = Field(default_factory=Icfr)
    going_concern: Item[int] = Field(default_factory=Item)
    subsidiary: Subsidiary = Field(default_factory=Subsidiary)
    notes_toc: Item[NotesToc] = Field(default_factory=Item)


def empty_standard(*, rcept_no: str | None = None) -> StandardExtraction:
    return StandardExtraction(rcept_no=rcept_no)
