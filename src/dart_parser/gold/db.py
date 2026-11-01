"""gold.db 연결과 스키마 마이그레이션.

카탈로그는 ``mode=ro`` URI로만 ATTACH 한다.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dart_parser.gold.schema import MIGRATIONS


def open_gold(gold_path: Path, catalog_path: Path | None) -> sqlite3.Connection:
    """gold.db를 열고, 카탈로그가 있으면 스키마 ``cat``으로 읽기 전용 연결한다."""
    path = Path(gold_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path.resolve().as_uri(), uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    if catalog_path is not None:
        catalog_uri = f"{Path(catalog_path).resolve().as_uri()}?mode=ro"
        conn.execute("ATTACH DATABASE ? AS cat", (catalog_uri,))
    return conn


def migrate(conn: sqlite3.Connection) -> int:
    """아직 적용하지 않은 DDL을 실행하고 user_version을 돌려준다."""
    current = int(conn.execute("PRAGMA user_version").fetchone()[0])
    for version, ddl in enumerate(MIGRATIONS, start=1):
        if version <= current:
            continue
        conn.executescript(ddl)
        conn.execute(f"PRAGMA user_version = {version}")
        conn.commit()
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def catalog_file(conn: sqlite3.Connection) -> Path | None:
    """ATTACH 된 카탈로그 파일 경로. 없으면 None."""
    for row in conn.execute("PRAGMA database_list"):
        if row[1] == "cat" and row[2]:
            return Path(row[2])
    return None
