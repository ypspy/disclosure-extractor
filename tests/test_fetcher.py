from __future__ import annotations

import json

import httpx

from dart_parser.config.settings import Settings
from dart_parser.fetcher.dart_client import DartClient
from dart_parser.fetcher.xbrl_client import XbrlClient


def test_list_filings_parses_opendart_payload() -> None:
    payload = {
        "status": "000",
        "list": [
            {
                "corp_code": "00126380",
                "corp_name": "삼성전자",
                "rcept_no": "20240312000736",
                "report_nm": "감사보고서",
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "list.json" in str(request.url)
        assert request.url.params["crtfc_key"] == "test-key"
        return httpx.Response(200, json=payload)

    client = DartClient(
        settings=Settings(api_key="test-key"),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    rows = client.list_filings(corp_code="00126380", bgn_de="20240101", end_de="20241231")
    assert rows[0]["rcept_no"] == "20240312000736"


def test_download_document_returns_zip_bytes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "document.xml" in str(request.url)
        return httpx.Response(200, content=b"PK\x03\x04fake")

    client = DartClient(
        settings=Settings(api_key="test-key"),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert client.download_document("20240312000736").startswith(b"PK")


def test_xbrl_singl_acnt_parses_list() -> None:
    payload = {
        "status": "000",
        "list": [
            {
                "account_nm": "자산총계",
                "thstrm_amount": "455,760",
                "frmtrm_amount": "448,424",
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert "fnlttSinglAcnt.json" in str(request.url)
        return httpx.Response(200, content=json.dumps(payload).encode())

    client = XbrlClient(
        settings=Settings(api_key="test-key"),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    rows = client.fetch_singl_acnt(corp_code="00126380", bsns_year="2023", reprt_code="11011")
    assert rows[0]["account_nm"] == "자산총계"
