from dart_parser.normalizer.table_grid import extract_tables
from dart_parser.parser.rule_engine import (
    RuleEngine,
    TableSpec,
    detect_period_columns,
    period_column_groups,
)


def test_rule_engine_extracts_amounts_from_labeled_grid(mock_bs_html: str) -> None:
    table = extract_tables(mock_bs_html)[0]
    spec = TableSpec(
        name="accounts",
        column_anchors={"current": ["제5기"], "prior": ["제4기"]},
        row_anchors={
            "total_asset": ["자산총계"],
            "total_liability": ["부채총계"],
            "total_equity": ["자본총계"],
        },
        header_row_count=2,
    )
    extracted = RuleEngine().extract(table, spec)

    current = extracted["total_asset"]["current"]
    assert current is not None
    assert current.value == 1200.0
    assert current.raw == "1,200"
    assert extracted["total_equity"]["prior"].value == 400.0


def test_detect_period_columns_parenthetical_dang_and_duplicate_amount_col() -> None:
    labels = [
        "과 목",
        "주석",
        "제 55 (당) 기",
        "제 55 (당) 기",
        "제 54 (전) 기",
        "제 54 (전) 기",
    ]
    grid = [
        labels,
        ["자산총계", "", "", "296,857,289", "", "260,083,750"],
    ]
    periods = detect_period_columns(labels, grid=grid, header_row_count=1)
    assert periods["current"] == 3
    assert periods["prior"] == 5


def test_period_groups_read_dang_without_gi() -> None:
    groups = period_column_groups(["과 목", "제21(당)", "제21(당)", "제20(전)기", "제20(전)기"])
    assert groups["current"] == [1, 2]
    assert groups["prior"] == [3, 4]
