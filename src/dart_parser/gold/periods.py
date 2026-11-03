"""접수일·결산월·정정 여부로 서식 기간(P1–P7)을 정한다."""

from __future__ import annotations

# 서식 변화가 커서 풀링 결과와 따로 보고하는 기간.
FLAGGED_PERIODS = frozenset({"P1a", "P2", "P5", "P7"})
# P1은 P1a를 포함하므로 기간 행 플래그에 함께 쓴다.
FLAGGED_SAMPLE_PERIODS = frozenset({"P1", "P2", "P5", "P7"})


def _digits(value: str | None) -> str:
    """숫자만 남긴다."""
    if not value:
        return ""
    return "".join(ch for ch in value if ch.isdigit())


def _fye_key(fye: str | None) -> int | None:
    """``2018.12`` 또는 ``(2018.12)``를 201812로 만든다."""
    digits = _digits(fye)
    if len(digits) < 6:
        return None
    return int(digits[:6])


def layout_era(fye: str | None) -> str | None:
    """결산월이 2018.12 미만이면 구서식, 이후면 신서식."""
    key = _fye_key(fye)
    if key is None:
        return None
    if key >= 201812:
        return "new"
    return "old"


def period_dtd_mismatch(period: str, dtd: str | None) -> bool:
    """P7은 dart4, 그 외는 dart4가 아니면 불일치로 본다. dtd가 없으면 판단하지 않는다."""
    if not dtd:
        return False
    is_dart4 = "dart4" in dtd.lower()
    if period == "P7":
        return not is_dart4
    return is_dart4


def assign_period(
    rcept_dt: str,
    fye: str | None,
    dtd: str | None,
    is_correction: bool = False,
) -> tuple[str, str | None]:
    """기간과 하위 기간을 돌려준다. 2000년 미만은 ``OUT``.

    ``dtd``는 기간 경계에 쓰지 않고, 불일치는 ``period_dtd_mismatch``에서 따로 본다.
    정정은 접수일이 2019-01-01 이후이고 결산이 2018.12 미만이어도 P6에 둔다.
    """
    del dtd
    digits = _digits(rcept_dt)
    day = int(digits[:8])
    year = day // 10000
    if year < 2000:
        return ("OUT", None)
    if day >= 20240229:
        return ("P7", None)
    if year <= 2007:
        sub = "P1a" if year <= 2001 else "P1b"
        return ("P1", sub)
    if year == 2008:
        return ("P2", None)
    if year <= 2011:
        return ("P3", None)
    if year <= 2014:
        sub = "P4a" if year == 2012 else "P4b"
        return ("P4", sub)
    if is_correction and day >= 20190101:
        return ("P6", None)
    key = _fye_key(fye)
    if key is not None and key >= 201812:
        return ("P6", None)
    return ("P5", None)
