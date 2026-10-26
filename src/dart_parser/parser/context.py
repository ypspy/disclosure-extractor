from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from dart_parser.normalizer.table_grid import Table

CorpForm = Literal["F001", "F002"]
FsScope = Literal["separate", "consolidated"]


@dataclass
class ExtractionContext:
    html: str
    rcept_no: str | None = None
    fs_scope: FsScope | None = None
    fiscal_year: int | None = None
    corp_form: CorpForm | None = None
    tables: list[Table] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)
