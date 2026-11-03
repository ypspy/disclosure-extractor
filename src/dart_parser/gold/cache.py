"""표본 원문 캐시. 로컬 파일과 박스 미러만 보고 네트워크는 쓰지 않는다."""

from __future__ import annotations

import csv
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

CACHE_ROOT = Path(r"C:\dev\dart-wrapper\data\gold_cache")


def cache_dir(root: Path, rcept_no: str) -> Path:
    """접수번호 하나의 캐시 디렉터리."""
    return Path(root) / rcept_no


def _box_doc(box_mirror: Path, rcept_no: str) -> Path | None:
    """박스 미러에서 접수번호 폴더를 찾는다."""
    root = Path(box_mirror)
    if not root.exists():
        return None
    direct = list(root.glob(f"*/{rcept_no}"))
    for path in direct:
        if path.is_dir():
            return path
    return None


@dataclass
class CachePlan:
    """이미 있는 문서, 박스에서 복사할 문서, 없는 문서."""

    present: list[str]
    from_box: list[str]
    missing: list[str]
    root: Path
    box_mirror: Path


def plan_cache(
    conn: sqlite3.Connection,
    run_id: str,
    root: Path,
    box_mirror: Path,
) -> CachePlan:
    """표본 접수번호가 캐시·박스·누락 중 어디인지 나눈다."""
    rows = conn.execute(
        """
        SELECT DISTINCT rcept_no FROM gold_samples
        WHERE run_id = ?
        ORDER BY rcept_no
        """,
        (run_id,),
    ).fetchall()
    present: list[str] = []
    from_box: list[str] = []
    missing: list[str] = []
    for row in rows:
        rcept_no = row[0]
        if (cache_dir(root, rcept_no) / "main.html").is_file():
            present.append(rcept_no)
            continue
        if _box_doc(box_mirror, rcept_no) is not None:
            from_box.append(rcept_no)
            continue
        missing.append(rcept_no)
    return CachePlan(present, from_box, missing, Path(root), Path(box_mirror))


def import_from_box(plan: CachePlan) -> int:
    """박스에 있는 원문만 로컬 캐시로 복사한다."""
    copied = 0
    for rcept_no in plan.from_box:
        source = _box_doc(plan.box_mirror, rcept_no)
        if source is None:
            continue
        target = cache_dir(plan.root, rcept_no)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        copied += 1
    return copied


def load_section_html(
    root: Path, rcept_no: str, entry: dict[str, object]
) -> str | None:
    """캐시에 있는 섹션 HTML만 읽는다. 파일이 없으면 None."""
    folder = cache_dir(root, rcept_no)
    if not folder.is_dir():
        return None
    ele_id = str(entry.get("ele_id") or "")
    toc_path = folder / "toc.json"
    if toc_path.is_file() and ele_id:
        try:
            toc = json.loads(toc_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            toc = None
        filename = ""
        if isinstance(toc, dict):
            raw = toc.get(ele_id) or toc.get("sections", {}).get(ele_id)
            if isinstance(raw, str):
                filename = raw
            elif isinstance(raw, dict):
                filename = str(raw.get("file") or "")
        if filename:
            section = folder / filename
            if section.is_file():
                return section.read_text(encoding="utf-8")
    if ele_id:
        needle = f'data-ele-id="{ele_id}"'
        for path in sorted(folder.glob("*.html")):
            text = path.read_text(encoding="utf-8")
            if needle in text or f"eleId={ele_id}" in text:
                return text
    main = folder / "main.html"
    if main.is_file() and not ele_id:
        return main.read_text(encoding="utf-8")
    return None


def write_missing_list(plan: CachePlan, path: Path) -> None:
    """없는 접수번호를 CSV로 남긴다. 수집은 하지 않는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rcept_no"])
        for rcept_no in plan.missing:
            writer.writerow([rcept_no])
