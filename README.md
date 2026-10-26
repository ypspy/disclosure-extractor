# dart-hybrid-parser

DART 공시 HTML의 비정형성을 다루기 위한 하이브리드 파서입니다.

`API Fetch (TOC/XBRL) → HTML·표 정규화 → 앵커 규칙 엔진 → 검증 → SLM fallback`

첫 추출 과제는 `standard`입니다. 항목 정의는 [`docs/standard-extraction-items.md`](docs/standard-extraction-items.md)를 따릅니다.

## 요구 사항

- Python 3.11+
- Open DART API 키 (문서 수집 시)
- (선택) Ollama / vLLM 등 OpenAI 호환 엔드포인트 — 규칙 파서 검증 실패 시 fallback

## 설치

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
```

`.env`의 `DART_API_KEY`에 Open DART 인증키를 넣습니다. SLM을 쓰지 않으면 `DART_LLM_ENABLED=false`로 두면 됩니다.

## 사용

```python
from dart_parser.pipeline import Pipeline

result = Pipeline().run_from_html(html, rcept_no="20240312000000", use_fallback=False)
print(result.extraction.model_dump())
print(result.tables[0].grid)
```

Open DART에서 원문을 받으려면 `DartClient` / `XbrlClient`를 사용합니다. 재무제표 계정은 XBRL·계정 API를 HTML보다 우선합니다.

## 패키지 구조

```text
src/dart_parser/
  fetcher/       Open DART 목록·원문·XBRL
  normalizer/    HTML 정리, 숫자 변환, colspan/rowspan 평탄화
  parser/        앵커 매칭, 단위, 규칙 엔진
  validator/     합계·회계등식 검증
  fallback/      Pydantic 스키마, Instructor SLM 클라이언트
  pipeline.py    오케스트레이션
tests/
  sample_htmls/  스냅샷 (실제 DART HTML은 여기)
```

작업 원칙은 루트의 `AGENTS.md`입니다.

## 테스트

```powershell
python -m pytest
ruff check .
```
