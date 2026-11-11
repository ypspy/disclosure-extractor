"""공시 HTML과 입수 행을 한 페이지로 만든다."""

from __future__ import annotations

import html
import json
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote

from dart_parser.gold.capture import CaptureRow, money_group
from dart_parser.gold.capture_html import prepare_disclosure_html

_SCALES: tuple[tuple[int, str], ...] = (
    (1, "1 원"),
    (1000, "1000 천원"),
    (1_000_000, "1000000 백만원"),
    (100_000_000, "100000000 억원"),
)
_UNIT_NAMES = dict(_SCALES)
_UNIT_GROUP = {"재무상태표": "bs", "손익계산서": "is"}


def render_capture_page(
    rcept_no: str,
    dcm_no: str,
    token: str,
    filing_html: str,
    rows: Sequence[CaptureRow],
    saved: Mapping[tuple[str, str], Any],
    units: Mapping[str, int],
    company: str,
    report: str,
    filed: str,
    *,
    miss_bundle: str = "",
    miss_subject: str = "",
) -> str:
    """왼쪽은 공시 shadow root, 오른쪽은 입수 행이다."""
    title = _title(rcept_no, dcm_no, company, report, filed)
    capture_url = _path(rcept_no, dcm_no, "capture")
    row_column = _rows(
        rows,
        saved,
        units,
        token,
        capture_url,
        rcept_no,
        dcm_no,
        miss_bundle,
        miss_subject,
    )
    header = (
        "<header>"
        '<p><a href="/">목록</a></p>'
        f"<p>{html.escape(company)}</p>"
        f"<p>{html.escape(report)}</p>"
        f"<p>{html.escape(filed)}</p>"
        f"<p>{html.escape(rcept_no)}</p>"
        f"<p>{html.escape(dcm_no)}</p>"
        f"<p>표시 {len(saved)}건</p>"
        "</header>"
    )
    body = (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title>"
        "<style>"
        "body{margin:0;font-family:sans-serif}"
        "header{padding:0.5rem 1rem}"
        ".layout{display:grid;grid-template-columns:1fr 24rem;height:calc(100vh - 5rem)}"
        "#filing,.rows{overflow:auto;height:100%}"
        "form{border-top:1px solid #ccc;padding:0.4rem}"
        "</style></head><body>"
        f"{header}"
        '<div class="layout">'
        '<div id="filing"></div>'
        f'<div class="rows">{row_column}</div>'
        "</div>"
        f"{_script(capture_url, prepare_disclosure_html(filing_html))}"
        "</body></html>"
    )
    return body


def _title(rcept_no: str, dcm_no: str, company: str, report: str, filed: str) -> str:
    if not company and not report and not filed:
        return f"{rcept_no}/{dcm_no}"
    named = " ".join(part for part in (company, report) if part)
    return named or f"{rcept_no}/{dcm_no}"


def _rows(
    rows: Sequence[CaptureRow],
    saved: Mapping[tuple[str, str], Any],
    units: Mapping[str, int],
    token: str,
    capture_url: str,
    rcept_no: str,
    dcm_no: str,
    miss_bundle: str,
    miss_subject: str,
) -> str:
    parts: list[str] = []
    current = ""
    for row in rows:
        if row.group != current:
            if current:
                parts.append("</section>")
            current = row.group
            parts.append("<section>")
            parts.append(f"<h2>{html.escape(row.group)}</h2>")
            unit_group = _UNIT_GROUP.get(row.group)
            if unit_group is not None:
                parts.append(
                    _unit_form(rcept_no, dcm_no, token, unit_group, units.get(unit_group))
                )
        missed = bool(miss_bundle) and row.bundle == miss_bundle and row.subject == miss_subject
        parts.append(
            _row_form(
                row,
                saved.get((row.bundle, row.subject)),
                token,
                capture_url,
                missed=missed,
            )
        )
    if current:
        parts.append("</section>")
    return "".join(parts)


def _unit_form(
    rcept_no: str,
    dcm_no: str,
    token: str,
    unit_group: str,
    chosen: int | None,
) -> str:
    options: list[str] = []
    for scale, name in _SCALES:
        selected = " selected" if chosen == scale else ""
        options.append(f'<option value="{scale}"{selected}>{html.escape(name)}</option>')
    action = html.escape(_path(rcept_no, dcm_no, "unit"), quote=True)
    return (
        f'<form method="post" action="{action}">'
        f'<input type="hidden" name="token" value="{html.escape(token, quote=True)}">'
        f'<input type="hidden" name="unit_group" value="{html.escape(unit_group, quote=True)}">'
        f'<select name="unit_scale">{"".join(options)}</select>'
        '<button type="submit">적용</button>'
        "</form>"
    )


def _row_form(
    row: CaptureRow,
    record: Any,
    token: str,
    capture_url: str,
    *,
    missed: bool,
) -> str:
    action = html.escape(capture_url, quote=True)
    shown = _block(_saved_text(row, record))
    miss = "<p>읽을 수 없습니다</p>" if missed else ""
    return (
        f'<form class="capture-row" method="post" action="{action}">'
        f'<input type="hidden" name="token" value="{html.escape(token, quote=True)}">'
        f'<input type="hidden" name="bundle" value="{html.escape(row.bundle, quote=True)}">'
        f'<input type="hidden" name="subject" value="{html.escape(row.subject, quote=True)}">'
        f'<label><input type="radio" name="row"> {html.escape(row.label)}</label>'
        '<button type="submit" name="status" value="not_applicable">해당 없음</button>'
        '<button type="submit" name="status" value="not_in_regime">제도상 없음</button>'
        '<button type="submit" name="status" value="clear">지우기</button>'
        f"{shown}{miss}"
        "</form>"
    )


def _saved_text(row: CaptureRow, record: Any) -> str:
    if record is None:
        return ""
    status = str(record["status"])
    if status == "not_applicable":
        return "해당 없음"
    if status == "not_in_regime":
        return "제도상 없음"
    if status != "found" or not record["value"]:
        return ""
    try:
        parsed = json.loads(record["value"])
    except (TypeError, json.JSONDecodeError):
        return ""
    if money_group(row.bundle, row.subject) is not None and isinstance(parsed, dict):
        return _money(parsed)
    if row.bundle == "notes_toc" and isinstance(parsed, dict):
        titles = parsed.get("titles") or []
        return "\n".join(str(title) for title in titles)
    if row.bundle == "communications" and row.subject == "items" and isinstance(parsed, list):
        lines = [
            f"{item.get('round')} {item.get('raw')}"
            for item in parsed
            if isinstance(item, dict)
        ]
        return "\n".join(lines)
    if isinstance(parsed, (dict, list)):
        return json.dumps(parsed, ensure_ascii=False)
    return _plain(parsed)


def _money(parsed: dict[str, Any]) -> str:
    scale = parsed.get("unit_scale")
    name = _UNIT_NAMES.get(scale, "") if isinstance(scale, int) else ""
    return f"{_plain(parsed.get('value'))} {name}".strip()


def _plain(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if value is None:
        return ""
    return str(value)


def _block(text: str) -> str:
    if not text:
        return ""
    return "<p>" + "<br>".join(html.escape(line) for line in text.split("\n")) + "</p>"


def _path(rcept_no: str, dcm_no: str, action: str) -> str:
    return f"/doc/{quote(rcept_no)}/{quote(dcm_no)}/{action}"


def _script(capture_url: str, filing_html: str) -> str:
    payload = json.dumps(filing_html, ensure_ascii=False).replace("<", "\\u003c")
    url = json.dumps(capture_url)
    return (
        "<script>\n"
        f"const captureUrl = {url};\n"
        f"const filingHtml = {payload};\n"
        "const host = document.getElementById('filing');\n"
        "const root = host.attachShadow({mode: 'open'});\n"
        "root.innerHTML = filingHtml;\n"
        "root.addEventListener('click', function (event) {\n"
        "  const chosen = selectedRow();\n"
        "  if (!chosen) return;\n"
        "  const body = new URLSearchParams();\n"
        "  body.set('token', chosen.token.value);\n"
        "  body.set('bundle', chosen.bundle.value);\n"
        "  body.set('subject', chosen.subject.value);\n"
        "  body.set('text', event.target.textContent || '');\n"
        "  fetch(captureUrl, {\n"
        "    method: 'POST',\n"
        "    headers: {'Content-Type': 'application/x-www-form-urlencoded'},\n"
        "    body: body\n"
        "  }).then(function (response) {\n"
        "    window.location.assign(response.url || captureUrl);\n"
        "  });\n"
        "});\n"
        "function selectedRow() {\n"
        "  const forms = document.querySelectorAll('form.capture-row');\n"
        "  for (let i = 0; i < forms.length; i++) {\n"
        "    if (forms[i].row && forms[i].row.checked) return forms[i];\n"
        "  }\n"
        "  return null;\n"
        "}\n"
        "document.addEventListener('change', function (event) {\n"
        "  if (!event.target || event.target.name !== 'row') return;\n"
        "  const forms = document.querySelectorAll('form.capture-row');\n"
        "  for (let i = 0; i < forms.length; i++) {\n"
        "    if (forms[i].row && forms[i].row !== event.target) forms[i].row.checked = false;\n"
        "  }\n"
        "});\n"
        "</script>"
    )
