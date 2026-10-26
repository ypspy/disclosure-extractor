"""Open DART financial-statement / XBRL client. Preferred over HTML for accounts."""

from __future__ import annotations

from typing import Any

from dart_parser.fetcher.dart_client import OpenDartBase


class XbrlClient(OpenDartBase):
    def fetch_singl_acnt(
        self,
        corp_code: str,
        *,
        bsns_year: str,
        reprt_code: str,
        fs_div: str = "OFS",
    ) -> list[dict[str, Any]]:
        """Single-company major accounts (`fnlttSinglAcnt.json`)."""
        data = self._get_json(
            "fnlttSinglAcnt.json",
            {
                "corp_code": corp_code,
                "bsns_year": bsns_year,
                "reprt_code": reprt_code,
                "fs_div": fs_div,
            },
        )
        return list(data.get("list") or [])

    def download_xbrl(self, rcept_no: str, *, reprt_code: str) -> bytes:
        """Financial-statement XBRL ZIP (`fnlttXbrl.xml`)."""
        return self._get_bytes(
            "fnlttXbrl.xml",
            {"rcept_no": rcept_no, "reprt_code": reprt_code},
        )
