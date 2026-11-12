"""공시 HTML과 입수 행을 한 페이지로 만든다."""

from __future__ import annotations

import html
import json
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote

from dart_parser.gold.capture import CaptureRow, money_group, section_jumps
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
    encoding_uncertain: bool = False,
    dcm_ambiguous: bool = False,
    cache_missing: bool = False,
    recorded: int = 0,
    row_total: int = 0,
    period_done: int = 0,
    period_total: int = 0,
    period: str = "",
    toc: Sequence[tuple[str, str]] = (),
    base: str = "doc",
) -> str:
    """왼쪽은 공시 shadow root, 오른쪽은 입수 행이다."""
    if base not in {"doc", "recapture"}:
        raise ValueError("base는 doc 또는 recapture입니다.")
    title = _title(rcept_no, dcm_no, company, report, filed)
    capture_url = _path(rcept_no, dcm_no, "capture", base)
    preview_url = _path(rcept_no, dcm_no, "preview", base)
    cleaned = prepare_disclosure_html(filing_html)
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
        base,
    )
    progress = (
        f'<p id="period-progress">재입수 완료 {period_done}/{period_total}</p>'
        if base == "recapture"
        else f'<p id="period-progress">완료 {period_done}/{period_total}</p>'
    )
    header = (
        "<header>"
        '<p><a href="/">목록</a></p>'
        f"<p>{html.escape(company)}</p>"
        f"<p>{html.escape(report)}</p>"
        f"<p>{html.escape(filed)}</p>"
        f"<p>{html.escape(rcept_no)}</p>"
        f"<p>{html.escape(dcm_no)}</p>"
        f'<p id="doc-progress">기록 {recorded}/{row_total}</p>'
        f"{progress}"
        f"{_warnings(encoding_uncertain, dcm_ambiguous, cache_missing)}"
        f"{_complete_form(rcept_no, dcm_no, token, base)}"
        f"{_next_link(period, base)}"
        "</header>"
    )
    body = (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title>"
        "<style>"
        ":root{--desk:#e4dccb;--ink:#1c1915;--paper:#fbf7ef;--fields:#efe8d8;"
        "--rail:#d9d0bf;--mark:#e7b008;--bar:#243028;--bar-text:#f4efe4}"
        "body{margin:0;background:var(--desk);color:var(--ink);font-family:Batang,serif}"
        '#sections,.rows,button,select,input{font-family:"Malgun Gothic",sans-serif}'
        "#sections{display:flex;gap:0.4rem;padding:0.4rem 1rem;background:var(--rail)}"
        ".layout{display:grid;grid-template-columns:1fr 24rem;height:calc(100vh - 8rem)}"
        "#filing{background:var(--paper);overflow:auto;height:100%}"
        ".rows{background:var(--fields);overflow:auto;height:100%}"
        "section:not([data-active]){display:none}"
        "#confirm{display:flex;gap:0.5rem;align-items:center;padding:0.5rem 1rem;"
        "background:var(--bar);color:var(--bar-text)}"
        "#confirm[hidden]{display:none}"
        "header{background:var(--ink);color:var(--bar-text)}"
        "</style></head><body>"
        f"{header}"
        f"{_sections_nav()}"
        '<div id="confirm" hidden>'
        '<p id="confirm-evidence"></p>'
        '<div id="confirm-control"></div>'
        '<p id="confirm-reason"></p>'
        '<button type="button" id="confirm-save">저장</button>'
        '<button type="button" id="confirm-cancel">취소</button>'
        "</div>"
        f"{_toc_nav(toc)}"
        '<div class="layout">'
        '<div id="filing"></div>'
        f'<div class="rows">{row_column}</div>'
        "</div>"
        f"{_data(capture_url, preview_url, cleaned)}"
        '<script src="/static/capture.js"></script>'
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
    base: str,
) -> str:
    parts: list[str] = []
    current = ""
    first = True
    for row in rows:
        if row.group != current:
            if current:
                parts.append("</section>")
            current = row.group
            active = ' data-active="1"' if first else ""
            first = False
            parts.append(f'<section data-section="{html.escape(row.group)}"{active}>')
            parts.append(f"<h2>{html.escape(row.group)}</h2>")
            unit_group = _UNIT_GROUP.get(row.group)
            if unit_group is not None:
                parts.append(
                    _unit_form(rcept_no, dcm_no, token, unit_group, units.get(unit_group), base)
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
    base: str,
) -> str:
    blank = " selected" if chosen is None else ""
    options: list[str] = [f'<option value=""{blank}></option>']
    for scale, name in _SCALES:
        selected = " selected" if chosen == scale else ""
        options.append(f'<option value="{scale}"{selected}>{html.escape(name)}</option>')
    action = html.escape(_path(rcept_no, dcm_no, "unit", base), quote=True)
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
    lines = _list_lines(row, record)
    shown = "" if lines is not None else _block(_saved_text(row, record))
    miss = "<p>읽을 수 없습니다</p>" if missed else ""
    form = (
        f'<form class="capture-row" method="post" action="{action}">'
        f'<input type="hidden" name="token" value="{html.escape(token, quote=True)}">'
        f'<input type="hidden" name="bundle" value="{html.escape(row.bundle, quote=True)}">'
        f'<input type="hidden" name="subject" value="{html.escape(row.subject, quote=True)}">'
        f'<label><input type="radio" name="row"> {html.escape(row.label)}</label>'
        '<button type="submit" name="status" value="not_applicable">해당 없음</button>'
        '<button type="submit" name="status" value="not_in_regime">제도상 없음</button>'
        '<button type="submit" name="status" value="clear">지우기</button>'
        f"{shown}{miss}"
        f"{_hint(row)}"
        '<p class="row-error"></p>'
        "</form>"
    )
    if not lines:
        return form
    return form + _remove_forms(row, lines, token, capture_url)


def _list_lines(row: CaptureRow, record: Any) -> list[str] | None:
    parsed = _found_json(record)
    if row.bundle == "notes_toc" and row.subject == "value":
        if not isinstance(parsed, dict):
            return None
        titles = parsed.get("titles") or []
        return [str(title) for title in titles]
    if row.bundle == "communications" and row.subject == "items":
        if not isinstance(parsed, list):
            return None
        return [
            f"{item.get('round')} {item.get('raw')}"
            for item in parsed
            if isinstance(item, dict)
        ]
    return None


def _found_json(record: Any) -> Any:
    if record is None or str(record["status"]) != "found" or not record["value"]:
        return None
    try:
        return json.loads(record["value"])
    except (TypeError, json.JSONDecodeError):
        return None


def _remove_forms(
    row: CaptureRow,
    lines: list[str],
    token: str,
    capture_url: str,
) -> str:
    status = "remove_title" if row.bundle == "notes_toc" else "remove_item"
    action = html.escape(capture_url, quote=True)
    hidden_token = html.escape(token, quote=True)
    bundle = html.escape(row.bundle, quote=True)
    subject = html.escape(row.subject, quote=True)
    parts: list[str] = []
    for index, line in enumerate(lines):
        parts.append(
            f'<form method="post" action="{action}">'
            f'<input type="hidden" name="token" value="{hidden_token}">'
            f'<input type="hidden" name="bundle" value="{bundle}">'
            f'<input type="hidden" name="subject" value="{subject}">'
            f'<input type="hidden" name="index" value="{index}">'
            f"<span>{html.escape(line)}</span>"
            f'<button type="submit" name="status" value="{status}">지우기</button>'
            "</form>"
        )
    return "".join(parts)


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


def _hint(row: CaptureRow) -> str:
    if row.bundle != "going_concern":
        return ""
    return "<p>의견 근거만 있거나, 전기 인용만 있거나, 청산기준 강조만 있으면 0입니다.</p>"


def _warnings(encoding_uncertain: bool, dcm_ambiguous: bool, cache_missing: bool) -> str:
    parts: list[str] = []
    if encoding_uncertain:
        parts.append('<p id="encoding-check">인코딩을 확정하지 못했습니다.</p>')
    if dcm_ambiguous:
        parts.append('<p id="dcm-warning">문서번호를 구분할 수 없습니다.</p>')
    if cache_missing:
        parts.append('<p id="cache-missing">캐시가 없습니다.</p>')
    return "".join(parts)


def _complete_form(rcept_no: str, dcm_no: str, token: str, base: str) -> str:
    action = html.escape(_path(rcept_no, dcm_no, "complete", base), quote=True)
    return (
        f'<form method="post" action="{action}">'
        f'<input type="hidden" name="token" value="{html.escape(token, quote=True)}">'
        '<button type="submit">완료</button>'
        "</form>"
    )


def _next_link(period: str, base: str) -> str:
    if not period:
        return ""
    href = "/next" if base == "doc" else f"/{base}/next"
    return f'<p><a href="{href}?period={quote(period)}">다음 문서</a></p>'


def _sections_nav() -> str:
    buttons: list[str] = []
    for index, name in enumerate(section_jumps()):
        pressed = ' aria-pressed="true"' if index == 0 else ' aria-pressed="false"'
        buttons.append(
            f'<button type="button" data-section="{html.escape(name)}"{pressed}>'
            f"{html.escape(name)}</button>"
        )
    return f'<nav id="sections">{"".join(buttons)}</nav>'


def _toc_nav(toc: Sequence[tuple[str, str]]) -> str:
    if not toc:
        return ""
    links = [
        (
            f'<a href="#{html.escape(ident, quote=True)}" '
            f'data-scroll="{html.escape(ident, quote=True)}">{html.escape(title)}</a>'
        )
        for ident, title in toc
    ]
    return f'<nav id="filing-toc">{"".join(links)}</nav>'


def html_json(value: Any) -> str:
    """HTML에 넣을 JSON. `<`, `>`, `&`, U+2028, U+2029는 이스케이프한다."""
    raw = json.dumps(value, ensure_ascii=False)
    return (
        raw.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _path(rcept_no: str, dcm_no: str, action: str, base: str = "doc") -> str:
    return f"/{base}/{quote(rcept_no)}/{quote(dcm_no)}/{action}"


def _data(capture_url: str, preview_url: str, filing_html: str) -> str:
    payload = html_json(
        {
            "captureUrl": capture_url,
            "previewUrl": preview_url,
            "filingHtml": filing_html,
            "sections": {name: list(phrases) for name, phrases in section_jumps().items()},
        }
    )
    return f'<script id="capture-data" type="application/json">{payload}</script>'
