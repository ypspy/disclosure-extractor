"""Open DART REST client (list / original document). No I/O at import time."""

from __future__ import annotations

from typing import Any

import httpx

from dart_parser.config.settings import Settings, get_settings


class DartApiError(RuntimeError):
    def __init__(self, status: str, message: str) -> None:
        super().__init__(f"Open DART error {status}: {message}")
        self.status = status
        self.message = message


class OpenDartBase:
    def __init__(
        self,
        settings: Settings | None = None,
        http: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._http = http
        self._owns_http = http is None

    def _client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=self.settings.http_timeout)
        return self._http

    def close(self) -> None:
        if self._owns_http and self._http is not None:
            self._http.close()
            self._http = None

    def _url(self, endpoint: str) -> str:
        return f"{self.settings.api_base_url.rstrip('/')}/{endpoint.lstrip('/')}"

    def _params(self, extra: dict[str, Any]) -> dict[str, Any]:
        return {"crtfc_key": self.settings.api_key, **extra}

    def _get_json(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self._client().get(self._url(endpoint), params=self._params(params))
        response.raise_for_status()
        data = response.json()
        status = data.get("status")
        if status not in (None, "000"):
            raise DartApiError(str(status), str(data.get("message", "")))
        return data

    def _get_bytes(self, endpoint: str, params: dict[str, Any]) -> bytes:
        response = self._client().get(self._url(endpoint), params=self._params(params))
        response.raise_for_status()
        return response.content


class DartClient(OpenDartBase):
    def list_filings(
        self,
        corp_code: str,
        *,
        bgn_de: str,
        end_de: str,
        page_no: int = 1,
        page_count: int = 100,
    ) -> list[dict[str, Any]]:
        data = self._get_json(
            "list.json",
            {
                "corp_code": corp_code,
                "bgn_de": bgn_de,
                "end_de": end_de,
                "page_no": page_no,
                "page_count": page_count,
            },
        )
        return list(data.get("list") or [])

    def download_document(self, rcept_no: str) -> bytes:
        """Return the original-document ZIP bytes for ``rcept_no``."""
        return self._get_bytes("document.xml", {"rcept_no": rcept_no})
