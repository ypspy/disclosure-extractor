from dart_parser.normalizer.table_grid import extract_tables
from dart_parser.parser.rule_engine import RuleEngine, TableSpec


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
