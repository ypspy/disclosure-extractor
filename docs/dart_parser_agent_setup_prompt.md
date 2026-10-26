# DART 파서 개발 프로젝트 초기 세팅 가이드 & Cursor Agent Rules

이 문서는 DART 공시 HTML의 비정형성(스타일 파편화, 셀 병합, 임의 포맷)을 극복하기 위한 **하이브리드 파싱 파이프라인(정규화 → 앵커 규칙 파서 → 경량 LLM Fallback)**을 Cursor 기반으로 구현할 때 사용하는 초기 설정 가이드입니다.

---

## 1. 프로젝트 디렉토리 구조 제안

```text
dart-hybrid-parser/
├── .cursor/
│   └── rules/
│       └── dart-parser.mdc       # Cursor 프로젝트 규칙 (또는 AGENTS.md)
├── AGENTS.md                     # Cursor Agent 작업 지침
├── pyproject.toml / requirements.txt
├── .env.example
├── config/
│   └── settings.py               # API 키, 로컬 LLM 엔드포인트(Ollama/vLLM) 설정
├── src/
│   ├── fetcher/
│   │   ├── dart_client.py        # Open DART API 연동 (TOC, XML, HTML 수집)
│   │   └── xbrl_client.py        # 재무제표 XBRL 우선 수집 클라이언트
│   ├── normalizer/
│   │   ├── cleaner.py            # 인라인 태그 제거, 공백 정규화, 문자셋 보정
│   │   └── table_grid.py         # colspan/rowspan 2D Grid 평탄화
│   ├── parser/
│   │   ├── anchor_matcher.py     # 헤더 키워드 및 퍼지 앵커 매핑
│   │   ├── unit_extractor.py     # 단위(원, 주, 백만원 등) 추출 및 배수 적용
│   │   └── rule_engine.py        # 1차 정형 파싱 엔진
│   ├── validator/
│   │   └── math_validator.py     # 수치 무결성 검증 (합계, 소계, 기말식 일치 검사)
│   ├── fallback/
│   │   ├── llm_client.py         # 경량 LLM 호출 (Ollama/vLLM/OpenAI 호환)
│   │   └── schemas.py            # Pydantic 기반 정형 출력(JSON Schema) 정의
│   └── pipeline.py               # 전체 오케스트레이션 엔트리포인트
└── tests/
    ├── sample_htmls/             # 실제 DART 예외 케이스 HTML 스냅샷
    └── test_parser.py
```

---

## 2. AGENTS.md 설정 파일

Cursor의 Agent 모드(`Composer` 및 `Chat`)가 파이프라인의 원칙과 예외 상황을 일관되게 처리하도록 프로젝트 루트에 `AGENTS.md`를 생성합니다.

```markdown:AGENTS.md
# AGENTS.md - DART Hybrid Parser Project Guidelines

## Project Mission
Extract structured data from irregular DART disclosure documents using a multi-tiered pipeline:
`API Fetch (TOC/XBRL) -> HTML & Table Normalization -> Anchor-based Rule Engine -> Validation -> Fallback to SLM (Small Language Model)`.

## Role & Engineering Principles
1. **Never parse styles:** Ignore font, color, margin, and layout tags. Treat HTML strictly as semantic structures.
2. **Flatten first, then parse:** Never attempt regex or selector navigation on unflattened `colspan` or `rowspan`. Expand them into a 2D coordinate grid first.
3. **XBRL Priority:** For financial statements, prioritize Open DART XBRL API before falling back to HTML parsing.
4. **Deterministic over Stochastic:** Maximize rule-based parsing accuracy. Small LLM fallback should only be invoked when validation fails or table shapes break heuristics.
5. **Strict Schema Output:** LLM outputs and rule engine outputs must both strictly conform to Pydantic schemas.

## Tech Stack & Dependencies
- **Language:** Python 3.11+
- **Parsing/HTML:** `lxml`, `beautifulsoup4`, `html5lib`, `Bleach`
- **Data & Numeric:** `pandas`, `pydantic>=2.0`, `rapidfuzz` (for anchor matching)
- **LLM/Fallback:** `instructor`, `ollama` (or `openai` SDK compatible with vLLM/Ollama endpoints)
- **Testing:** `pytest`

## Code Conventions
- Use type hints on all function signatures.
- Write defensive parsers: all cell conversions must handle commas (`,`), dashes (`-`), and non-breaking spaces gracefully (`to_number()` helper).
- Unit tests must be written alongside parser implementations using mock HTML snippets.
```

---

## 3. Cursor 최초 초기화 프롬프트 (Composer 입력용)

새 프로젝트를 시작할 때 Cursor Composer(`Ctrl + I` 또는 `Cmd + I`)에 복사하여 붙여넣을 프롬프트입니다.

```text
DART(대한민국 전자공시시스템) 비정형 공시 문서를 구조화된 JSON 데이터로 추출하는 하이브리드 파서 프로젝트를 구축하려고 합니다.

[작업 목표]
1. Python 기반 프로젝트 골격 생성 (src, tests, config, AGENTS.md)
2. 핵심 파이프라인 모듈 작성:
   - normalizer/cleaner.py: DART 특유의 HTML 노이즈(font, span, nbsp, 전각 공백) 정리
   - normalizer/table_grid.py: rowspan, colspan이 포함된 HTML <table>을 2차원 리스트(Grid)로 평탄화하는 함수
   - parser/anchor_matcher.py: rapidfuzz를 사용하여 헤더 행/열 앵커 키워드 매칭
   - fallback/schemas.py: Pydantic v2 기반 공시 표 추출 스키마 정의
   - fallback/llm_client.py: Ollama/vLLM(Qwen 2.5 7B 등)과 연동하여 Instructor 기반 구조화 추출 클라이언트 구현
3. pyproject.toml 또는 requirements.txt 생성 (lxml, beautifulsoup4, rapidfuzz, pydantic, instructor, openai)

AGENTS.md에 정의된 규칙을 준수하여 단계를 나누어 코드를 생성해 주세요. 먼저 기본 디렉토리와 환경 파일부터 작성해 주세요.
```

---

## 4. 모듈별 구현 참조 스니펫

### 4.1. Table 평탄화 (Colspan / Rowspan 2D Grid)
```python
# src/normalizer/table_grid.py
from bs4 import BeautifulSoup

def flatten_table_to_grid(table_html: str) -> list[list[str]]:
    soup = BeautifulSoup(table_html, "lxml")
    table = soup.find("table")
    if not table:
        return []

    rows = table.find_all("tr")
    grid = []
    
    # 2D Grid 채우기
    for r_idx, row in enumerate(rows):
        cells = row.find_all(["th", "td"])
        c_idx = 0
        
        while len(grid) <= r_idx:
            grid.append([])
            
        for cell in cells:
            rowspan = int(cell.get("rowspan", 1))
            colspan = int(cell.get("colspan", 1))
            text = " ".join(cell.get_text(strip=True).split())

            # 이미 이전 행의 rowspan에 의해 채워진 칸 스킵
            while c_idx < len(grid[r_idx]) and grid[r_idx][c_idx] is not None:
                c_idx += 1

            for r in range(rowspan):
                target_r = r_idx + r
                while len(grid) <= target_r:
                    grid.append([])
                for c in range(colspan):
                    target_c = c_idx + c
                    while len(grid[target_r]) <= target_c:
                        grid[target_r].append(None)
                    grid[target_r][target_c] = text
            c_idx += colspan

    return [[cell or "" for cell in row] for row in grid]
```

### 4.2. Fallback 경량 LLM 클라이언트 (Instructor + Qwen/Llama)
```python
# src/fallback/llm_client.py
import instructor
from openai import OpenAI
from pydantic import BaseModel

class DARTTableExtraction(BaseModel):
    title: str
    unit: str
    headers: list[str]
    rows: list[dict[str, str | float | None]]

def extract_with_slm(table_markdown: str, schema: type[BaseModel] = DARTTableExtraction) -> BaseModel:
    client = instructor.from_openai(
        OpenAI(
            base_url="http://localhost:11434/v1",  # Ollama 기본 포트
            api_key="ollama"
        ),
        mode=instructor.Mode.JSON
    )

    prompt = f"""다음은 DART 공시 문서의 파싱되지 않은 비정형 표 데이터입니다.
정확한 수치와 항목을 식별하여 구조화된 JSON으로 변환하세요.

[Table Data]
{table_markdown}
"""
    return client.chat.completions.create(
        model="qwen2.5:7b",
        response_model=schema,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0
    )
```

---

## 5. 단계별 권장 구현 순서

1. **Phase 1: 전처리 & Grid 변환기 구축**
   - DART 보고서 샘플 HTML 3~5종 다운로드 후 `sample_htmls/`에 배치
   - `cleaner.py`와 `table_grid.py` 단위 테스트 검증
2. **Phase 2: 앵커 규칙 파서 구현**
   - 주요 공시(예: 최대주주 현황, 임원 현황, 배당 내역 등)에 맞춘 앵커 사전 구축
   - 수치 합산 검증기(`math_validator.py`) 연결
3. **Phase 3: 로컬 SLM Fallback 파이프라인 연결**
   - 규칙 파서 검증 실패 시 해당 표를 마크다운 변환 후 Ollama(`qwen2.5:7b`)로 전달
   - Pydantic 스키마 무결성 확인 및 DB/JSON 출력 파이프라인 완성