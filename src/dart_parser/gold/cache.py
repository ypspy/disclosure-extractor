"""표본 원문 캐시. 로컬 파일과 박스 미러만 보고 네트워크는 쓰지 않는다."""

from __future__ import annotations

import csv
import json
import re
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

CACHE_ROOT = Path(r"C:\dev\dart-wrapper\data\gold_cache")

_CHARSET_RE = re.compile(rb"charset\s*=\s*[\"']?\s*([A-Za-z0-9_\-]+)", re.IGNORECASE)
_KOREAN_CHARSETS = {
    "cp949": "cp949",
    "ms949": "cp949",
    "windows-949": "cp949",
    "euc-kr": "euc-kr",
    "euc_kr": "euc-kr",
    "ks_c_5601-1987": "euc-kr",
}


@dataclass(frozen=True)
class CachedHtml:
    """캐시 HTML과, 인코딩을 확정하지 못했는지."""

    text: str
    encoding_uncertain: bool


def read_cached_html(path: Path) -> CachedHtml:
    """UTF-8로 읽고, 실패하면 meta charset의 cp949/euc-kr로 다시 읽는다."""
    data = Path(path).read_bytes()
    try:
        return CachedHtml(data.decode("utf-8"), False)
    except UnicodeDecodeError:
        encoding = _korean_charset(data)
        if encoding is not None:
            try:
                return CachedHtml(data.decode(encoding), False)
            except UnicodeDecodeError:
                pass
        return CachedHtml(data.decode("utf-8", errors="replace"), True)


def _korean_charset(data: bytes) -> str | None:
    """앞부분 meta charset이 cp949 또는 euc-kr이면 그 인코딩 이름을 돌려준다."""
    match = _CHARSET_RE.search(data[:8192])
    if match is None:
        return None
    name = match.group(1).decode("ascii", errors="ignore").lower()
    return _KOREAN_CHARSETS.get(name)


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


def _document_folder(root: Path, rcept_no: str, dcm_no: str | None) -> Path:
    """접수번호 폴더. dcm_no 하위 폴더가 있으면 그 문서를 고른다."""
    folder = cache_dir(root, rcept_no)
    if dcm_no and (folder / dcm_no).is_dir():
        return folder / dcm_no
    return folder


def load_section_html(
    root: Path,
    rcept_no: str,
    entry: dict[str, object],
    dcm_no: str | None = None,
) -> CachedHtml | None:
    """캐시에 있는 섹션 HTML만 읽는다. 파일이 없으면 None."""
    folder = _document_folder(root, rcept_no, dcm_no)
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
            raw = toc.get(ele_id)
            if raw is None:
                sections = toc.get("sections")
                raw = sections.get(ele_id) if isinstance(sections, dict) else None
            if isinstance(raw, str):
                filename = raw
            elif isinstance(raw, dict):
                marker = str(raw.get("dcm_no") or "")
                if dcm_no and marker and marker != dcm_no:
                    filename = ""
                else:
                    filename = str(raw.get("file") or "")
        if filename:
            section = (folder / filename).resolve()
            if section.is_file() and section.is_relative_to(folder.resolve()):
                return read_cached_html(section)
    if ele_id:
        needle = f'data-ele-id="{ele_id}"'
        for path in sorted(folder.glob("*.html")):
            loaded = read_cached_html(path)
            if needle in loaded.text or f"eleId={ele_id}" in loaded.text:
                return loaded
    main = folder / "main.html"
    if main.is_file() and not ele_id:
        return read_cached_html(main)
    return None


def write_missing_list(plan: CachePlan, path: Path) -> None:
    """없는 접수번호를 CSV로 남긴다. 수집은 하지 않는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rcept_no"])
        for rcept_no in plan.missing:
            writer.writerow([rcept_no])
