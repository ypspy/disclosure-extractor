from dart_parser.parser.anchor_matcher import (
    canonical,
    find_header_row,
    find_rows,
    map_columns,
    match_anchor,
)


def test_canonical_strips_spaces_and_punctuation() -> None:
    assert canonical("자 산 총 계") == "자산총계"
    assert canonical("당기순이익.") == "당기순이익"


def test_match_anchor_accepts_near_miss() -> None:
    hit = match_anchor("자산 총계", ["자산총계", "부채총계"])
    assert hit is not None
    assert hit.matched == "자산총계"
    assert hit.score >= 80


def test_match_anchor_rejects_unrelated() -> None:
    assert match_anchor("영업외수익", ["자산총계"], threshold=90) is None


def test_find_header_row_and_map_columns() -> None:
    grid = [
        ["과목", "제5기", "제4기"],
        ["자산총계", "1,200", "1,000"],
    ]
    assert find_header_row(grid, ["제5기", "제4기"]) == 0
    cols = map_columns(grid[0], {"current": ["제5기"], "prior": ["제4기"]})
    assert cols == {"current": 1, "prior": 2}


def test_map_columns_stacks_multi_row_headers() -> None:
    headers = [
        ["과목", "제5기", "제5기", "제4기", "제4기"],
        ["과목", "금액", "비고", "금액", "비고"],
    ]
    cols = map_columns(headers, {"current": ["제5기 금액"], "prior": ["제4기 금액"]})
    assert cols["current"] == 1
    assert cols["prior"] == 3


def test_find_rows_maps_account_labels() -> None:
    grid = [
        ["과목", "당기"],
        ["자산총계", "100"],
        ["부채총계", "60"],
        ["자본총계", "40"],
    ]
    anchors = {
        "total_asset": ["자산총계"],
        "total_liability": ["부채총계"],
        "total_equity": ["자본총계"],
    }
    rows = find_rows(grid, anchors, start_row=1)
    assert rows == {"total_asset": 1, "total_liability": 2, "total_equity": 3}
