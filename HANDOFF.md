# ⚠ 대상 변경 (2026-11-01, 윤석님 결정) — 이 절이 아래 모든 내용보다 우선
- 검증·개량 대상 추출기: C:\dev\disclosure-extractor (ypspy/disclosure-extractor, src/dart_parser). dart-wrapper v19가 아님.
- 작업 위치: disclosure-extractor 저장소, 새 브랜치 feat/gold-review → PR, 머지 금지.
- 카탈로그 C:\dev\dart-wrapper\packages\web-api\dart_catalog.db 는 표본 모집단·문서 위치용으로 sqlite mode=ro + busy_timeout 로만 읽기. 스키마·수집 코드 변경 금지. dart-wrapper 저장소는 수정하지 않음.
- 네트워크 금지: OpenDART 호출 끔, SLM fallback 끔(DART_LLM_ENABLED=false), 유료 API 금지. 추출기는 로컬 캐시 문서에만 실행.
- 필드: v19의 12개 묶음 대신 docs/standard-extraction-items.md 기준. 아래 설계의 필드·계정 규칙은 매핑표 확정 후 다시 맞춤.
- 스냅샷: audit_report_facts 대신 disclosure-extractor를 캐시 문서에 돌린 출력(추출기 버전/커밋 태그 포함)을 gold.db에 저장.
- 검토 UI: dart-wrapper admin이 아니라 disclosure-extractor 안의 별도 로컬 앱. extraction_reviews 사용 안 함.
- gold.db(gold*.db)는 .gitignore.
- 첫 단계: 필드 매핑표(standard 항목 ↔ 추출기 출력 키 ↔ 판정 단위 ↔ 희소 여부 ↔ 근거 위치)를 만들어 보고하고 멈춤.

## dart-wrapper feat/gold-review 재사용 표시 (packages/research/research/gold/)
- 그대로 이식: periods.py, scoring.py(Wilson·풀링), db.py, schema.py, matching.py, cache.py, 대응 테스트(test_gold_periods/scoring/db/matching/cache/rescore/oversample), gold_fixtures.py(카탈로그 픽스처)
- 수정 후 이식: sampler.py(카탈로그 읽기는 유지, 경로 설정만), snapshots.py(출력 출처를 disclosure-extractor로), labels.py·subjects.py·evidence.py(필드 목록을 매핑표 기준으로)
- 버림: research/api/admin 연동, templates/admin/gold, local_app.py(새 앱 구조에 맞춰 재작성), config.py 변경

# DART 골드 검증 인수인계 (2026-10-31)
## 최우선 규칙
- AWS/Gemini/유료 API 절대 금지, DART_LLM_ENABLED=false 유지. DART 네트워크 수집·신규 샘플링은 윤석님 승인 필수.
## 경로
- 저장소: C:\dev\dart-wrapper  (DB: packages\web-api\dart_catalog.db, 읽기전용 mode=ro)
- 추출기: packages\research\research\extracting\ (audit_opinion.v19, audit_report_facts)
- 관리자 UI: research\api\admin\reviews.py (FastAPI) / 참고: C:\Users\yoont\quality-updates (curator)
- 신규 코드 위치: packages\research\research\gold\, research\api\admin\gold.py, templates\admin\gold\, scripts\gold_*.py, tests\test_gold_*.py; gold.db는 별도 파일
## 빈 테스트 항목
- 작업 5, 8, 9, 12, 15의 테스트는 설명만 있고 코드 미작성. 실행 진입점 없으면 research\local_app.py 추가(조건부).
## 미결 5개와 기본값
1. P6 내 구서식 정정 별도 층: 기본 = 별도 표시만, 층 분리 안 함
2. 추출기 셀 좌표 출력: 기본 = 선택 필드로 추가(없어도 동작)
3. 누락 원문 보충 수집 시점·속도: 기본 = 파일럿 후, 2~4초 지터, 승인 후
4. 상장일 출처: 기본 = 카탈로그 현재 시장 태그로 대체
5. 수정 재검증 홀드아웃 크기: 기본 = 기간당 골드의 20%
## 연간 점검 주기안 (설계 v1.2 추가 예정)
- 1~4월 시즌: 주 1회(피크 3월 중순~4월 초 주 2회) 서식 지문·필드 분포 이상 감시, 표시율 2% 초과 시 경보
- 5월: 그해 공시 400건 신규 골드, Wilson 하한 99% 재확인 후 기간 편입
- 6~12월: 월 1회 정정·지연분 지문 점검; 1월 초 기준 개정 사전 확인
- 기준 개정/DTD 변경/표시율 급증 시 임시 기간(P8 후보) 개설


---
# DART 감사보고서 골드셋 검수 도구 설계서

작성일: 2026-10-31 · 상태: **확정본 v1.1 (2026-10-31)** — 미결 질문 결정 반영(§0), v1.1: D11 희소 필드 풀링 · 대상 추출기: `audit_opinion.v19` (`C:\dev\dart-wrapper\packages\research\research\extracting\`)
검수자: 윤석님(CPA, 단독) · 근거: `analysis/FORMAT_BOUNDARIES_FINAL.md`, `dart_catalog.db` 읽기 전용 조사(2026-10-31)

---

## 0. 확정 결정 요약 (2026-10-31, 윤석님)
| # | 결정 |
|---|---|
| D1 | 통과 기준 = **Wilson 95% 하한 ≥ 99%**. 기간당 **400건**(총 약 2,800건). n=400에서 **오류 0건이어야 통과**(하한 99.05%; 오류 1건이면 98.60%로 불통과). 작업량 약 400시간 |
| D2 | 골드 데이터는 별도 **`gold.db`** (dart_catalog.db는 읽기 전용 ATTACH) |
| D3 | 계정: **당기+전기 22셀**, **표시 단위 기준 정확 일치** |
| D4 | 원본·정정 **모두 모집단 포함**, 정정은 **접수일 기준**으로 기간 배정 |
| D5 | 표본 원문을 **노트북에 사전 캐시**, 박스 `dart-sample/docs` 원문 재사용 |
| D6 | 블라인드 모드도 **근거 섹션 자동 이동 허용**, 단 추출값은 절대 비표시 |
| D7 | 골드 판정은 `extraction_reviews`에 **기록하지 않음**, 중복 문서 플래그만 |
| D8 | 골드 문서에 대해 **추출기 버전별 출력 스냅샷** 보관 |
| D9 | 틀린 표: **자유 메모 + 핵심값 정답(총 감사시간, 투입 인원)만** 입력 |
| D10 | 시장 층은 당분간 **현재 시장 태그** 사용, 상장일 데이터는 추후 |
| D11 | **희소 필드**(icfr, subsidiary_count, 희소 외부감사 실시내용 표, 희소 계정)는 **기간 풀링**으로 판정. 풀링 n이 383 미만이면 **해당 필드가 있는 문서를 추가 과표집**. 서식 변화가 큰 기간은 **별도 보고 플래그** (v1.1) |

---

## 1. 목표 / 비목표

### 목표
1. 추출기 12개 묶음(auditor, opinion, gaap, audit_report_date, current_period, hours, activities, communications, accounts, icfr, going_concern, subsidiary_count) **모든 필드의 정밀도(precision) ≥ 99%** 를 **서식 기간(P1–P7)별로** 검증한다.
2. 기간별 **400건** × 7기간 ≈ **2,800건**의 무작위 층화 골드셋을 재현 가능하게 만든다(고정 시드).
3. 사전 채움(prefill) 검수를 기본으로 하되, 기간별 약 10%(≈40건)는 **블라인드 입력**으로 받아 앵커링 편향을 측정한다.
4. 골드 라벨을 추출기 버전과 분리 저장하여, 추출기가 바뀌어도 **고정된 골드로 재채점**할 수 있게 한다.
5. 근거(원문 섹션·표 셀)를 한 화면에서 보며 키보드로 빠르게 판정한다.

### 비목표
- 추출기 수정·재실행, LLM 호출(`DART_LLM_ENABLED=false` 유지), AWS/Gemini 등 유료 API 사용.
- 기존 이상치 기반 `extraction_reviews` 큐(51,481건, 전부 `hold`) 처리 — 별개 흐름으로 유지(§4.4).
- 다중 검수자·검수자 간 일치도(κ) — 단독 검수 전제. (블라인드 재입력이 대체 지표)
- 재현율(recall) 공식 보증 — 부수적으로 계산하되 목표 지표는 아님(§7.4).
- F003(결합), F004, 감사의감사보고서, P0(1999) — 골드셋 제외.
- 원격 배포·인증 체계 고도화 — 노트북 로컬 전용.

---

## 2. 범위 정의

### 2.1 기간(FORMAT_BOUNDARIES_FINAL 기준)
| 기간 | 규칙 | 하위 층 |
|---|---|---|
| P1 | 접수일 2000-01-01 ~ 2007-12-31 | P1a(2000–01) / P1b(2002–07) |
| P2 | 접수연도 2008 | – |
| P3 | 접수일 2009-01-01 ~ 2011-12-31 | – |
| P4 | 접수연도 2012–2014 | P4a(2012) / P4b(2013–14) |
| P5 | 접수 2015 ~ **FYE 2018.11 이전** | 2015 1–4월 과도기 과표집 |
| P6 | **FYE 2018.12 이후** & 접수일 ≤ 2024-02-28 | 2019 1–3월 과표집 |
| P7 | 접수일 ≥ 2024-02-29 (`dart4.xsd`) | 2024-02-26~03-08 과표집 |

- P5/P6은 **회계연도말(FYE)** 축, P6/P7은 **접수일·dtd** 축이다.
- **정정보고서는 접수일 기준으로 기간 배정**(D4). 예: 2024-02-29 이후 접수된 과거 FY 정정 → P7. P5/P6 경계도 정정은 접수일로 판정하므로, FYE<2018.12 정정이 2019년 이후 접수되면 P6에 배정된다. 이 경우, 메타에 `layout_era`(구/신 배치)를 별도 기록한다.
- 기간 판정 입력: `disclosures.rcept_dt`, `disclosures.year_end`(또는 `audit_report_facts.current_period_resolved`), `entries.dtd`. 판정 결과와 근거를 `gold_samples`에 저장(§4.1).

### 2.2 필드 단위(채점 단위 = "subject")
| 묶음 | 채점 단위 | 값 형식 | 판정 방식 |
|---|---|---|---|
| auditor | `auditor_resolved` 1개 | 문자열(법인명 정규화) | 스칼라 |
| opinion | `opinion_resolved` 1개 | enum: unqualified/qualified/adverse/disclaimer | 스칼라 |
| gaap | `gaap_resolved` 1개 | enum: k-gaap/k-ifrs/other | 스칼라 |
| audit_report_date | `audit_report_date` 1개 | ISO 날짜 | 스칼라 |
| current_period | `current_period_resolved` 1개 | `(YYYY.MM)` | 스칼라 |
| icfr | `icfr_engagement`, `icfr_opinion_code` 2개 | enum | 스칼라 |
| going_concern | `going_concern` 1개 | 0/1 | 스칼라 |
| subsidiary_count | `subsidiary_count` 1개 | 정수(연결만) | 스칼라 |
| hours | 표 전체 1개(`table`) | JSON 목록 | **표 단위** |
| activities | 표 전체 1개 | JSON 목록 | **표 단위** |
| communications | 표 전체 1개 | JSON 객체 | **표 단위** |
| accounts | 11계정 × 당기/전기 = **22개(확정, D3)** (`total_asset@current` 등) | 정수(원 단위 `value_won`) | 계정 셀 단위 |

- 11계정: total_asset, total_equity, net_income, inventory, receivable, long_term_receivable, contract_asset, unbilled, current_asset, total_liability, current_liability.
- 당기·전기 모두 판정(D3).
- 스칼라 판정: **맞다 / 틀리다 / 해당없음**. "틀리다"면 정답값 입력 필수. "해당없음"은 *원문에 해당 항목이 실제로 없음*(예: 비상장 별도의 ICFR, 별도재무제표의 종속기업수)을 뜻하며, 추출기가 값을 냈다면 그것은 "틀리다"(정답=없음)로 기록한다(§6.3).

---

## 3. 표본 추출 절차

### 3.1 모집단
- `audit_report_facts`(약 50,250행) ⋈ `disclosures` ⋈ `corps`, 조건: `fetch_status='ok'`, `source_report_type IN ('F001','F002','A001')`, `extractor_version='audit_opinion.v19'`.
- 제외: F003·F004, 감사의감사보고서, P0. **원본과 정정은 모두 포함**(D4); 같은 corp·FY 쌍은 `meta.correction_group`으로 묶어 표시.
- **주의**: 표본은 *추출 결과가 있는 문서*에서만 뽑으므로 추출 실패(fetch 실패) 문서는 정밀도 분모에서 빠진다. 커버리지는 §7.4에서 따로 보고.

### 3.2 층(strata)
기간 내 다음 변수로 층화(교차 셀이 너무 작으면 상위 변수 우선으로 병합):
1. 보고서 유형: 별도(F001·A001 별도) vs 연결(F002·A001 연결), 목표 **2:1**
2. 형태: 단독(F001/F002) vs 사업보고서 첨부(A001) — P5 이후(첨부는 2018년 이후 검증분)
3. 시장: KOSPI(Y) / KOSDAQ(K) / 기타·비상장 — `corps.corp_cls` **현재 시장 태그 사용(D10)**. 접수 시점 시장은 상장일 데이터 확보 후 사후 재층화(가중치만 재계산)
4. P6–P7: KAM 유무, 의견 유형(적정/비적정), 정정 여부 **최소 할당**(각 ≥ 15건, 모집단이 부족하면 전수)
5. 과도기 과표집 창(§2.1)
6. 하위 기간 P1a/P1b, P4a/P4b 비례 배분(단 P4b ≥ 80건)

KAM 유무는 facts에 컬럼이 없으므로 `entries.section_name`에 "핵심감사사항" 포함 여부로 판정하되 "수주산업 핵심감사사항" 제외.

### 3.3 알고리즘(재현성)
1. 모집단 행에 `period`, `stratum_key` 계산.
2. 각 문서에 `u = SHA256(f"{seed}|{rcept_no}|{dcm_no}")` 의 앞 16hex를 정수화한 값을 부여(시드 기본 `"gold-2026-10"`).
3. 층별 할당량(비례 + 최소할당, 최대잔여법 반올림)에 따라 `u` 오름차순 상위 n건 선택.
4. 선택된 기간 표본 안에서 `v = SHA256(f"{seed}|blind|{rcept_no}|{dcm_no}")` 오름차순 상위 10%(층 비례)를 **블라인드**로 지정.
5. `queue_order` = 기간 내 `u` 순서 + 블라인드 문서를 일정 간격으로 섞음(연속 블라인드 방지; 예: 매 10번째).
6. 실행 메타(`gold_runs`: seed, 모집단 쿼리 해시, DB 파일 mtime, 층별 모집단/표본 수)를 저장. 같은 시드·같은 DB 스냅샷이면 같은 표본.
- 해시 기반이라 모집단에 문서가 추가돼도 기존 선택 순서가 크게 흔들리지 않는다(추가 표본 필요 시 다음 순위부터 보충).
- `extraction_reviews`에 있는 문서도 **제외하지 않는다**(무작위성 유지). 교집합 여부만 플래그로 기록.

### 3.4 예비분
층별 할당의 +10%를 예비(`reserve`)로 뽑아둔다. 문서가 범위 외(감사의감사보고서 오분류 등)로 판명되면 `excluded`로 표시하고 같은 층 예비분을 승격.

---

## 4. 데이터 모델

골드 테이블은 **별도 파일 `gold.db`** 에 둔다(D2). 앱은 `gold.db`를 주 연결로 열고 `dart_catalog.db`를 URI `mode=ro`로 `ATTACH`해 조회만 한다. 기존 DB 무변경, 백업·이동은 `gold.db`(수 MB)만. 아래는 논리 스키마.

### 4.1 gold_runs / gold_samples
```sql
CREATE TABLE gold_runs (
  run_id        TEXT PRIMARY KEY,      -- 'gold-2026-10'
  seed          TEXT NOT NULL,
  created_at    DATETIME NOT NULL,
  population_sql_sha TEXT NOT NULL,
  db_snapshot   TEXT,                  -- mtime/size
  params        JSON NOT NULL,         -- 층 정의, 할당, 블라인드 비율
  stats         JSON NOT NULL          -- 층별 N/n
);

CREATE TABLE gold_samples (
  run_id      TEXT NOT NULL REFERENCES gold_runs(run_id),
  rcept_no    VARCHAR(32) NOT NULL,
  dcm_no      VARCHAR(32) NOT NULL,
  period      VARCHAR(8)  NOT NULL,    -- P1..P7
  sub_period  VARCHAR(8),              -- P1a, P4b ...
  stratum     VARCHAR(128) NOT NULL,   -- 'P6|consolidated|attached|Y|kam1|...'
  stratum_weight REAL NOT NULL,        -- N_h / n_h (가중 추정용)
  sample_hash VARCHAR(16) NOT NULL,
  mode        VARCHAR(8) NOT NULL,     -- 'prefill' | 'blind'
  role        VARCHAR(8) NOT NULL,     -- 'main' | 'reserve'
  queue_order INTEGER NOT NULL,
  status      VARCHAR(16) NOT NULL,    -- 'todo'|'in_progress'|'done'|'excluded'|'skipped'
  exclude_reason TEXT,
  meta        JSON NOT NULL,           -- dtd, fye, layout_era, kam, market_at_filing, in_extraction_reviews, 자산총계 등
  started_at  DATETIME, finished_at DATETIME,
  active_seconds INTEGER,              -- 실제 검수 시간(유휴 제외)
  PRIMARY KEY (run_id, rcept_no, dcm_no)
);
```

### 4.2 gold_labels (정답, 버전 독립)
```sql
CREATE TABLE gold_labels (
  rcept_no  VARCHAR(32) NOT NULL,
  dcm_no    VARCHAR(32) NOT NULL,
  bundle    VARCHAR(32) NOT NULL,      -- 12 묶음
  subject   VARCHAR(64) NOT NULL,      -- 'value' | 'engagement' | 'opinion' | 'table' | 'total_asset@current' ...
  pass      VARCHAR(8)  NOT NULL,      -- 'prefill' | 'blind'
  verdict   VARCHAR(8)  NOT NULL,      -- 'correct'|'wrong'|'na'|'unsure'
  gold_value JSON,                     -- 확정 정답(correct면 당시 추출값 복사, wrong이면 입력값, na면 null)
  shown_value JSON,                    -- 화면에 보였던 추출값(blind면 null)
  shown_extractor_version VARCHAR(32), -- 'audit_opinion.v19'
  evidence  JSON,                      -- {entry_id, viewer_url, cell:{table_idx,row,col}, snippet}
  error_tag VARCHAR(32),               -- 'wrong_table','unit','sign','period_swap','missing_row','ocr' ...
  note      TEXT NOT NULL DEFAULT '',
  labeled_at DATETIME NOT NULL,
  seconds   INTEGER,
  PRIMARY KEY (rcept_no, dcm_no, bundle, subject, pass)
);
```
- 키 `(rcept_no, dcm_no, bundle, subject)` 은 `extraction_reviews` 와 같은 축을 쓴다. 단 `extraction_reviews.subject`(예: `audit_current_total`, `current_liability`)는 신호별 문자열이므로 **매핑표 `gold_subject_map(bundle, review_subject, gold_subject)`** 를 둔다.
- 블라인드 문서는 `pass='blind'` 로 먼저 입력하고, **블라인드 제출 후** 같은 문서를 prefill 화면으로 다시 열어 `pass='prefill'` 라벨을 받는다(앵커링 비교용 쌍). 최종 정답은 `gold_final` 뷰에서 결정(§7.3).
- 이력: 라벨 수정 시 덮어쓰지 않고 `gold_label_history`(동일 컬럼 + `superseded_at`)에 이전 행을 남긴다.

### 4.3 gold_scores (버전별 채점 결과, 재생성 가능)
```sql
CREATE TABLE gold_scores (
  extractor_version VARCHAR(32) NOT NULL,
  rcept_no, dcm_no, bundle, subject,    -- gold_labels 키
  predicted JSON,                       -- 해당 버전 추출값
  outcome   VARCHAR(8) NOT NULL,        -- 'tp'|'fp'|'fn'|'tn'|'abstain'
  scored_at DATETIME NOT NULL,
  PRIMARY KEY (extractor_version, rcept_no, dcm_no, bundle, subject)
);
```
`gold_labels`는 사람 입력, `gold_scores`는 스크립트 산출물 — **결정과 원천 분리**(curator의 sidecar 원칙).

### 4.4 extraction_reviews 와의 관계
| 구분 | extraction_reviews | gold_* |
|---|---|---|
| 목적 | 이상치 진단(신호 기반, 편향 표본) | 정밀도 추정(무작위 층화) |
| 단위 | 신호×subject | 필드×subject |
| 버전 | 행마다 버전 고정 | 정답은 버전 독립, 채점만 버전별 |
| 판정 | verdict/tag/note(현재 전부 hold) | correct/wrong/na + 정답값 |

- 상호 반영(D7): 골드 판정을 `extraction_reviews`에 **쓰지 않는다**(버튼도 두지 않음). 중복 문서는 `gold_samples.meta.in_extraction_reviews`(+해당 신호 목록) 플래그만 기록하고, prefill 화면에 배지로 표시(블라인드 모드에선 숨김).
- 지표는 골드에서만 계산. `extraction_reviews` 결과는 정밀도 추정에 섞지 않는다.

---

## 5. 앱 구조 — 기존 FastAPI admin 확장 권고

### 5.1 결론
**기존 `packages/research` FastAPI admin에 `/admin/gold` 라우터를 추가**한다. Flask 앱을 새로 만들지 않고, curator의 *UX 패턴*만 이식한다.

### 5.2 근거
| 항목 | FastAPI admin 확장 | 신규 Flask 앱 |
|---|---|---|
| DB/ORM | `AuditReportFact`, `ExtractionReview`, `entries` 모델·세션 재사용 | 모델 중복 정의 |
| 필드 정의 | `field_bundles.BUNDLE_KEYS`, `status_attr`, `classify_outcome` 직접 import → 추출기와 자동 동기 | 하드코딩·불일치 위험 |
| 인증 | 기존 토큰 게이트(`_has_valid_token`) 재사용 | 신규 구현 |
| 근거 링크 | `DART_DOCUMENT_VIEW`, entries 조회 코드 존재 | 재작성 |
| 렌더링 | 기존 reviews 페이지처럼 서버 HTML + 경량 JS | curator JS 재사용 쉬움 |
| 단점 | admin 코드 비대화 → 별도 모듈(`api/admin/gold.py`, `services/gold_*`, `templates/gold/*`, `static/gold.js`)로 격리 | 두 서버 운영 |

curator에서 가져올 것: 키보드 우선 행 이동·상태 순환, Enter=미리보기(포커스 유지), 저장 후 재조회로 인덱스 갱신, 원천과 결정의 분리 저장, 자동 제안은 "제안만" 원칙.

### 5.3 엔드포인트(초안)
- `GET /admin/gold` 기간별 진행 대시보드
- `GET /admin/gold/next?period=P6` 다음 `todo` 문서로 리다이렉트
- `GET /admin/gold/doc/{rcept_no}/{dcm_no}?pass=prefill|blind`
- `GET /admin/gold/evidence/{entry_id}` 섹션 HTML(로컬 캐시 우선, sanitize, 셀에 `data-r/c` 부여)
- `POST /admin/gold/label` (단건, 자동 저장) · `POST /admin/gold/doc/.../complete` · `POST .../exclude`
- `GET /admin/gold/metrics?version=audit_opinion.v19` 지표 표, CSV 내보내기

### 5.4 근거(evidence) 소스
- 섹션 위치: facts의 `*_entry_id`(cover/opinion/activity/bs/is/fs_parent/icfr/notes/a001_*) → `entries`(ele_id, offset, length, dtd, `viewer_url`).
- 표시: ① 로컬 원문 캐시(있으면) → iframe 대체 렌더, ② 없으면 `viewer_url`(DART 뷰어) 새 창 링크. DART 호출은 사람의 클릭으로만, 자동 대량 조회 없음.
- **원문 사전 캐시(D5)**: 표본(+예비) 문서 원문을 노트북 `C:\dev\dart-wrapper\data\gold_cache\<rcept_no>\` 에 미리 둔다. 박스 `/workspace/dart-sample/docs/<연도>/<rcpNo>/`(main.html, toc.json, secNN.html, attN/)에 이미 있는 문서는 복사 재사용, 없는 문서만 낮은 속도로 DART에서 수집(사람이 시작하는 일회성 배치, 속도 제한·중단 지점 기록). 검수 중 DART 조회는 하지 않는다.

---

## 6. 화면 & 키보드

### 6.1 레이아웃(1개 문서 = 1화면)
```
┌ 헤더: P6 · 127/300 · 연결·첨부·KOSPI · rcept_no/dcm_no · [DART 열기] · 모드: PREFILL | BLIND ┐
├──────── 좌: 필드 목록 (40%) ────────┬──────── 우: 근거 미리보기 (60%) ────────┤
│ ▸ 기본: auditor / opinion / gaap /   │  선택 필드의 entry 섹션 HTML           │
│   date / period / icfr×2 / GC / 종속 │  (값 위치 하이라이트, 스크롤 고정)      │
│ ▸ 외부감사 실시내용: hours / act / comm│  표 단위: 추출 JSON을 표로 재구성 ↔ 원표│
│ ▸ 계정 11×(당기·전기)                 │  계정: BS/IS 원표, 셀 하이라이트        │
└──────────────────────────────────────┴─────────────────────────────────────────┘
 하단: 진행바 · 경과시간 · 미판정 n개 · [완료 Ctrl+Enter]
```
- 행 배지 색: 미판정(회색) / 맞다(녹) / 틀리다(적) / 해당없음(청) / 보류(황).
- 추출 `*_status`가 fail/not_found여도 행은 표시(값 "—"). 정답이 존재하면 "틀리다"+값 입력(→ FN으로 집계).

### 6.2 스칼라 필드
- 표시: 추출값, `*_source`, `*_raw`(접기), `conflicts` 중 해당 필드 항목 경고 아이콘.
- `audit_report_date`: 후보 목록(`audit_report_date_candidates`)을 스니펫과 함께 표시, 숫자키로 후보 선택 가능.
- enum 필드는 정정 시 선택 팝업, 자유값은 텍스트 입력(형식 검증: 날짜·`(YYYY.MM)`·정수).

### 6.3 외부감사 실시내용 표(hours/activities/communications)
- 우측에 원문 표, 좌측에 추출 JSON을 같은 행·열 순서로 재구성한 표(매핑 실패 `unmapped=true` 강조).
- 판정은 **표 전체 1개**: 맞다 / 틀리다 / 해당없음(P1–P4·2015 초 구서식 등 섹션 부재). 틀리다면 **자유 메모 필수** + 오류 태그(행 누락, 역할 오매핑, 당기/전기 뒤바뀜, 단위, 합계 불일치…) 선택.
- 정답 표 전체 재입력은 하지 않는다. 대신 **핵심값 정답**만 입력(D9): hours=총 감사시간(당기)·투입 인원(당기), activities·communications=메모만. 재채점 시 핵심값은 자동 비교(§8.2).

### 6.4 계정(11)
- 우측: BS·IS 원표(`bs_entry_id`, `is_entry_id`, 필요시 `fs_parent_entry_id`). 좌측: 11계정 × 당기/전기 목록(값·단위·`account_raw`).
- 좌측 값 클릭(또는 행 이동) 시 해당 원문 셀 하이라이트 + 자동 스크롤. 셀 좌표는 추출기 `table_matrix`의 (표, 행, 열)을 facts JSON에 담아야 정확 — **현재 accounts JSON에 셀 좌표가 없음**(§9 갭). 임시안: `raw` 문자열과 `account_raw` 라벨로 원표에서 텍스트 매칭 하이라이트.
- 틀리다 시 정답 입력 방식: 원문 셀 클릭 → 값 자동 채움(단위 배수 적용, 원 단위 표시) 또는 숫자 직접 입력.

### 6.5 블라인드 모드
- 추출값·raw·source·status·conflicts·날짜 후보·리뷰 배지 **모두 숨김**(D6).
- 필드 선택 시 **근거 섹션 자동 이동은 허용**(D6). 단 섹션 내 값 위치 하이라이트(셀/스니펫)는 추출값을 암시하므로 끈다. 계정은 BS/IS 표 전체만 보이고 셀 하이라이트 없음.
- 각 필드는 값 입력 또는 "해당없음". 계정 22셀은 원문 셀 클릭으로 값 입력. 표 묶음은 "섹션 존재/부재 + 핵심값(총 감사시간·투입 인원)"만 입력(D9).
- 제출 후 즉시 prefill 화면으로 전환하지 **않고**, 큐에서 최소 N건(예: 20건) 뒤에 prefill 재검수를 배치(기억 효과 완화).

### 6.6 키보드 맵
| 키 | 동작 |
|---|---|
| `j`/`↓`, `k`/`↑` | 다음/이전 필드 |
| `1` / `y` | 맞다 |
| `2` / `n` | 틀리다 → 값 입력창 포커스 |
| `3` / `x` | 해당없음 |
| `4` / `?` | 보류(unsure) |
| `Space` | 미판정→맞다→틀리다→해당없음 순환(curator 방식) |
| `Enter` | 근거 패널 해당 위치로 이동/하이라이트(포커스 유지) |
| `e` | 정답값 편집 · `m` 메모 · `t` 오류 태그 |
| `Tab` / `Shift+Tab` | 섹션 그룹 이동(기본→표→계정) |
| `a` | 현재 그룹 미판정 전부 "맞다"(확인 대화상자, 블라인드 불가) |
| `c`(날짜) / 숫자 | 후보 선택 |
| `o` | DART 뷰어 새 창 |
| `Ctrl+Enter` | 문서 완료(미판정 있으면 차단) → 다음 문서 |
| `Ctrl+Shift+X` | 문서 제외(사유 입력) |
| `Esc` | 입력 취소/필드 모드 복귀 |

- 모든 판정 즉시 자동 저장(낙관적 UI, 실패 시 토스트). 저장 후 서버 상태 재조회.
- `a`(일괄 맞다)는 앵커링을 키우므로 사용 횟수를 로그로 남겨 블라인드 비교에 반영.

---

## 7. 지표 계산

### 7.1 정의(필드 f, 기간 p, 버전 v)
- 추출 "주장"(claim): 추출기가 값을 낸 경우(`status='ok'` 또는 값 non-null).
- **정밀도** = (claim ∧ 정답 일치) / claim. 정답이 "해당없음"인데 claim → FP. 
- 일치 규칙: 문자열 정규화(공백·괄호·"회계법인" 접미/접두, 영문 대소문자), 날짜 동일, enum 동일. **금액은 원문 표시 단위 기준 정확 일치(D3)**: 추출 `raw`(부호·괄호 정규화 후 숫자) = 정답 표시값이고 `unit_raw`/`unit_scale`이 원문 단위와 일치해야 TP. 단위 오류는 숫자가 같아도 FP(오류태그 `unit`). 표 묶음은 사람 판정 그대로 + 핵심값 일치 보조지표.
- 계정은 (계정×기간) 셀 단위로 집계, 문서 단위 "계정 전체 정확률"도 보조 보고.
- 보조: 커버리지 = claim / (정답 존재), 재현율 = TP / (정답 존재).

### 7.2 신뢰구간
- 기간·필드별 **Wilson 95% 구간**(z=1.96). 층별 가중이 필요할 땐 가중 추정 + 유효표본수로 Wilson 근사, 또는 층 부트스트랩(시드 고정 2,000회).
- **통과 기준(D1): Wilson 95% 하한 ≥ 99%** (기간×필드 셀마다).
- n=400 claim에서 **오류 0건 → 하한 99.05% 통과**, 오류 1건 → 98.60% 불통과. 즉 사실상 무오류 요구. (n=300이면 0건이어도 98.74%로 불통과; 0오류 통과 최소 n ≈ 383.)
- 오류 1건까지 허용하려면 claim ≈ 560건, 2건이면 ≈ 720건 필요.
- **희소 필드 주의**: claim은 "해당없음"·미추출을 빼므로 icfr(상장·연도 제한), subsidiary_count(연결만, 약 1/3), 외부감사 실시내용 3표(P5 이후만), contract_asset·unbilled 등 희소 계정은 기간 400건이어도 claim이 383 미만이 되어 **구조적으로 통과 불가**. → **D11 적용(§7.5)**.
- 오류 발견 시: 추출기 수정 → 새 버전으로 **같은 골드 재채점**(§8). 같은 골드로 수정·검증하는 과적합 위험은 예비 표본 holdout으로 점검(§12-5).
- 다중 비교: 12묶음×7기간 = 84개 셀(계정 포함 시 더 많음). 셀별 통과 여부와 함께 전체 집계(풀링) 정밀도도 보고.

### 7.3 블라인드 vs prefill
- 블라인드 문서(기간당 ~40, 총 ~280)에서 필드별 쌍 (blind 값, prefill 최종값, 추출값) 비교:
  - **일치율** blind=prefill, 불일치 원인 분류(블라인드 실수 / prefill 앵커링 / 모호).
  - **앵커링 지표**: 추출값이 틀렸는데(blind 기준) prefill에서 "맞다" 처리된 비율 = 놓침률. 
  - prefill 정밀도 vs blind 기준 정밀도 차이 + 대응표본 McNemar(문서 단위).
- 최종 정답(`gold_final`): blind·prefill 불일치 시 **재검토 큐**에 올려 3번째 판정으로 확정(adjudication). 
- 놓침률 상한(예: 놓침률 Wilson 상한 > 기준) 초과 시 prefill 정밀도를 하향 보정하거나 해당 필드 블라인드 비율 상향.

### 7.5 희소 필드 풀링(D11)
- **희소 필드 판정**: 표본 확정 후 v19 스냅샷 기준으로 기간×필드 claim 수가 383 미만인 필드를 희소로 지정(예상: icfr 2종, subsidiary_count, P5 경계·구기간의 hours/activities/communications, contract_asset·unbilled·long_term_receivable·inventory 일부 기간). 목록은 `gold_runs.params.sparse_fields`에 고정.
- **풀링 판정**: 희소 필드는 기간별 셀 대신 **전체 기간 풀링 셀**로 통과/불통과를 판정. 기간이 층이므로 **층 가중(N_h/n_h) 정밀도 + 유효표본수 기반 Wilson 하한**을 쓰고, 비가중 Wilson 하한도 병기. 통과는 가중 하한 ≥ 99%.
- **과표집**: 풀링 claim < 383(가중 시 유효표본수 < 383)이면, 모집단에서 **해당 필드 claim이 있는 문서**(예: `icfr_status='ok'`, `fs_scope='consolidated'`, `hours != '[]'`, 해당 계정 존재)만 대상으로 같은 시드 해시 순서로 추가 추출(`gold_samples.role='oversample'`, `meta.oversample_for=<field>`). 과표집 문서는 **그 희소 필드만** 검수 대상(다른 필드 지표에는 미포함 — 무작위성 보존). 기간 비례로 배분.
- 과표집 가중치: 해당 필드 claim 모집단 기준 `N_h(field)/n_h(field)` 로 별도 계산.
- **별도 보고 플래그**: 서식 변화가 큰 기간 — P1a(비표준 TOC), P2(과도기), P5(2015 연중 전환·외부감사 실시내용 도입), P7(dart4) — 및 희소 필드 오류가 특정 기간에 몰린 경우(풀링 내 기간 오류 비율 > 전체 2배)는 풀링 결과와 **별도로 기간별 수치·오류 사례를 보고**(`flag_period_report=true`). 플래그 기간에서 오류가 1건이라도 있으면 풀링 통과와 무관하게 해당 기간 "주의"로 표기.
- 작업량 추가: 과표집 문서는 단일 필드만 보므로 문서당 1–3분, 필드당 수십~수백 건 → 총 +20–40시간 예상(§10에 추가).

### 7.4 출력
- `metrics/<version>/precision.csv`(period, bundle, subject, n_claim, tp, fp, precision, wilson_lo, wilson_hi, coverage), 대시보드 히트맵(기간×필드), FP 사례 목록(근거 링크 포함).

---

## 8. 추출기 버전 변경 처리

### 8.1 원칙
- 정답(`gold_labels`)은 버전과 무관하게 고정. 새 버전 산출물이 생기면 `gold_scores`를 **재채점 스크립트**로 다시 만든다(사람 재검수 없음).
- **버전별 스냅샷(D8)**: `audit_report_facts`는 `(rcept_no,dcm_no)` PK라 재추출 시 덮어쓰므로, 골드 문서(+예비)의 facts 행 전체를 `gold.db`의 `extractor_snapshots(extractor_version, rcept_no, dcm_no, payload JSON, captured_at, PRIMARY KEY(extractor_version, rcept_no, dcm_no))`에 복사한다. 시점: 표본 확정 직후(v19) 1회, 이후 새 버전 재추출 직후마다. 채점은 항상 스냅샷에서 읽는다.

### 8.2 재채점이 불가한 경우
| 경우 | 처리 |
|---|---|
| 스칼라·계정 | 정답값이 있으므로 자동 재채점 |
| 표 묶음(hours/activities/comm) | 정답 = "v19 표 맞다/틀리다 + 메모 + 핵심값(D9)". 새 버전 표가 v19와 **정규화 후 동일**하면 판정 승계. 다르면 hours는 핵심값(총 감사시간·인원) 자동 비교 → 불일치면 FP 확정, 일치하면 **재검수 큐**(diff 화면). activities·communications는 다르면 재검수 큐 |
| 새 필드 추가 | 해당 필드만 보충 검수 큐 생성(문서 재방문) |
| 정답 오류 발견 | `gold_label_history`로 수정, 모든 버전 재채점 |
| 필드 의미 변경(enum 확장 등) | 매핑 함수 버전(`gold_schema_version`)으로 관리 |


---

## 9. 추출기·DB 갭(설계 반영 필요)
1. accounts/hours JSON에 **원문 셀 좌표 없음** → 셀 하이라이트 정확도 제한. 추출기 출력에 `cell:{entry_id, table_idx, row, col}` 추가를 차기 버전에 권장(본 설계 범위 밖, 임시 텍스트 매칭).
2. `extraction_reviews.subject` 문자열 ≠ facts 컬럼명 → `gold_subject_map` 필요.
3. `current_period` 는 리뷰 신호가 없음 → 골드에서만 측정됨.
4. `conflicts`(listing vs activity의 year_end 등)는 별도 필드가 아님 → 화면 경고로만 활용.
5. KAM 여부·dtd·FYE 기간 판정 컬럼이 facts에 없음 → `gold_samples.meta`에 계산 저장.
6. `audit_report_date_override` 가 유일한 수동 수정 컬럼 → 골드 정답을 여기에 쓰지 않음(원천 불변).

---

## 10. 작업량 추정 (400건/기간, D1·D3 반영)
| 항목 | 문서당 시간(추정) | 비고 |
|---|---|---|
| 스칼라 9개 확인 | 1.5–2분 | 대부분 표지·의견 단락 |
| 외부감사 실시내용 3표 | 2–3분 | P5 이후만(구기간은 해당없음 즉시) |
| 계정 22셀(당기+전기) | 2.5–5분 | 셀 하이라이트 품질에 좌우 |
| 오류 시 정정·메모·핵심값 | +1–2분/건 | |
| **prefill 합계** | P1–P4 약 5.5분, P5–P7 약 10분 | |
| **blind** | P1–P4 약 11분, P5–P7 약 20분 | + 이후 prefill 재검수 약 3분 |

- 기간당 prefill 360 + blind 40.
- prefill: P1–P4 4×360×5.5분 ≈ 132h, P5–P7 3×360×10분 ≈ 180h
- blind: 160×11분 ≈ 29h, 120×20분 ≈ 40h, blind 문서 prefill 재검수 280×3분 ≈ 14h
- adjudication·제외/예비 승격·파일럿 ≈ 10–15h
- D11 희소 필드 과표집 +20–40h
- **총 약 400시간(과표집 포함 시 약 420–440시간)** (하루 3시간이면 약 130일, 4시간이면 약 100일). 원문 사전 캐시(D5) 전제; 셀 하이라이트가 텍스트 매칭에 머물면 계정 부분 +20–30%.
- 진행 순서: P7·P6(현재 서식) → P5 → P1–P4. 기간 중 오류가 나오면 그 필드는 해당 버전으로는 불통과이므로 추출기 수정·재채점을 병행하고, 정답은 버전 무관이라 검수는 계속한다.

## 11. 단계별 진행(제안)
1. 표본기(sampler) 스크립트 + `gold.db`의 `gold_runs/gold_samples` 생성(읽기 전용 모집단 쿼리) — 층별 모집단 수 검토.
2. 문서 화면(prefill) + 스칼라 판정 + 자동 저장.
3. 계정 화면(셀 하이라이트 임시안), 표 묶음 화면.
4. 블라인드 모드·재검토 큐.
5. 지표 스크립트(Wilson, 블라인드 비교) + 대시보드.
6. 원문 캐시(D5)·v19 스냅샷(D8) → 파일럿 P7 30건 → 시간 측정·UI 조정 → 본 검수.

---

## 12. 남은 미결 사항
(희소 필드 판정은 D11로 확정되어 삭제)
1. **정정보고서 기간 배정의 P5/P6 예외**: 접수일 배정(D4)이면 FYE<2018.12 구배치 정정이 2019년 이후 접수 시 P6에 들어간다. 그대로 둘지, P6 안에 `layout_era=old` 별도 층·최소 할당을 둘지.
2. **셀 좌표**: 계정·hours 셀 하이라이트를 위해 추출기 출력에 셀 좌표(entry_id, table_idx, row, col)를 추가할지(추출기 변경 = 새 버전 → 재채점). 미추가 시 텍스트 매칭 임시안.
3. **원문 캐시 보충 수집**: 박스 `dart-sample/docs`에 없는 표본 원문을 DART에서 받는 일회성 배치의 실행 시점·속도 제한(노트북 실행, 사람 승인 후).
4. **상장일 데이터(D10 후속)**: 접수 시점 시장 정보 출처와 사후 재층화 시점.
5. **동일 골드 재사용 과적합**: 수정 검증을 같은 골드로 하므로 holdout(예비 표본 일부 고정 보류) 크기·사용 규칙.

---
# DART 골드셋 검수 도구 구현 계획

> **에이전트 작업자용:** 필수 하위 스킬 — superpowers:subagent-driven-development(권장) 또는 superpowers:executing-plans 로 태스크 단위 실행. 각 단계는 체크박스(`- [ ]`)로 추적.

**목표:** `GOLD_REVIEW_DESIGN.md` 확정본 v1.1을 `C:\dev\dart-wrapper\packages\research`에 구현해, 기간별 400건 층화 골드셋을 키보드 중심 웹 화면에서 검수하고 Wilson 하한(희소 필드 풀링 포함)으로 정밀도를 판정한다.

**아키텍처:** 기존 연구 패키지(`research/`)에 `research/gold/` 하위 패키지(순수 로직)와 `research/api/admin/gold.py` FastAPI 라우터(`/admin/gold`)를 추가한다. 골드 데이터는 별도 SQLite `gold.db`에 두고 `dart_catalog.db`는 `ATTACH ... mode=ro`로 읽기만 한다. 표본·채점·스냅샷·캐시는 CLI 스크립트(`packages/research/scripts/gold_*.py`)로 실행한다.

**기술 스택:** Python ≥3.11, FastAPI + Jinja2(`research.templating.create_templates`), sqlite3(표준 라이브러리, 동기), pytest(`asyncio_mode=auto`), httpx 테스트 클라이언트, 바닐라 JS.

작성일: 2026-10-31 · 근거 문서: `GOLD_REVIEW_DESIGN.md` v1.1 · 대상 브랜치: `feat/gold-review`(작업트리 권장)

## 전역 제약
- `DART_LLM_ENABLED=false` 유지. `research.adapters.llm_date_resolver`·`DateResolverService`를 골드 코드에서 import 금지.
- AWS·Gemini·OpenAI 등 **유료 서비스 호출 0건**. 필요 없음.
- `dart_catalog.db`는 **읽기 전용**(`file:...?mode=ro` URI). 스키마·데이터 무변경. `ensure_schema`에 골드 테이블 추가 금지.
- 골드 판정을 `extraction_reviews`에 **쓰지 않음**(D7).
- 추출기(`research/extracting/*`) 수정·재실행 없음. 버전 상수는 `research.extracting.constants.EXTRACTOR_VERSION`(=`audit_opinion.v19`)에서 읽는다.
- 통과 기준: Wilson 95%(z=1.96) 하한 ≥ 0.99. 기간당 400건, 블라인드 10%, 예비 10%, 시드 기본 `gold-2026-10`.
- 계정 22셀(11계정×current/prior), 표시 단위 기준 정확 일치.
- **DART 네트워크 접근은 Task 11의 보충 수집 단계에서만**, 윤석님 승인 후 실행. 그 외 모든 태스크·테스트는 오프라인.
- 테스트는 실제 `dart_catalog.db`를 열지 않는다. `tests/gold_fixtures.py`의 소형 SQLite 픽스처만 사용.

### 승인 필요 단계 요약
| 단계 | 내용 | 승인 |
|---|---|---|
| Task 11 Step 6 | 박스 캐시에 없는 원문을 DART에서 보충 수집 | **윤석님 승인 필수**(건수·속도 보고 후) |
| Task 14 Step 1 | 실DB로 표본 생성(`gold.db` 생성 — 신규 파일, 기존 DB 무변경) | 윤석님 확인 권장 |
| 박스→노트북 원문 복사 | `CopyFromBox` 또는 압축 파일 전달 | 윤석님 확인 권장 |
| 유료 서비스 | 없음 | — |

---

## 파일 구조

| 경로(`packages/research/` 기준) | 책임 |
|---|---|
| `research/gold/__init__.py` | 패키지 표식 |
| `research/gold/db.py` | `gold.db` 연결, 카탈로그 read-only ATTACH, 스키마 마이그레이션(`user_version`) |
| `research/gold/schema.py` | DDL 문자열 목록(MIGRATIONS) |
| `research/gold/periods.py` | P1–P7·하위기간 판정(접수일·FYE·dtd), 서식 변화 플래그 기간 |
| `research/gold/subjects.py` | 12묶음→채점 subject 목록, 22계정 셀, `extraction_reviews.subject` 매핑 |
| `research/gold/sampler.py` | 모집단 쿼리, 층화, 해시 순위, 할당, 블라인드·예비·과표집 |
| `research/gold/snapshots.py` | 버전별 facts 스냅샷 저장/조회 |
| `research/gold/labels.py` | 라벨 저장(이력 포함), 문서 완료·제외, 큐(next) |
| `research/gold/matching.py` | 필드별 정답 일치 규칙(정규화, 표시 단위 금액) |
| `research/gold/scoring.py` | TP/FP 산출, Wilson, 기간별·풀링(가중) 지표, 블라인드 비교 |
| `research/gold/cache.py` | 원문 캐시 경로 해석, 박스 캐시 재사용 목록, 섹션 HTML 로드 |
| `research/gold/evidence.py` | entries→근거 섹션, 셀 텍스트 매칭 하이라이트 |
| `research/api/admin/gold.py` | `/admin/gold` 라우터(대시보드, 문서 화면, 라벨 API, 지표) |
| `research/templates/admin/gold/*.html` | 대시보드·문서·지표 템플릿 |
| `research/templates/admin/gold/gold.js` (인라인 포함) | 키보드 맵, 자동 저장 |
| `scripts/gold_sample.py`, `gold_snapshot.py`, `gold_cache.py`, `gold_score.py` | CLI |
| `tests/gold_fixtures.py`, `tests/test_gold_*.py` | 픽스처·테스트 |

검증 공통 명령(노트북 PowerShell):
```powershell
cd C:\dev\dart-wrapper\packages\research
$env:DART_LLM_ENABLED='false'
python -m pytest tests -k gold -v
```

---

### Task 1: gold.db 연결·스키마 마이그레이션

**Files:**
- Create: `research/gold/__init__.py`, `research/gold/schema.py`, `research/gold/db.py`
- Create: `tests/gold_fixtures.py`, `tests/test_gold_db.py`

**Interfaces:**
- Produces: `open_gold(gold_path: Path, catalog_path: Path | None) -> sqlite3.Connection` (row_factory=Row, 카탈로그는 스키마명 `cat`으로 ATTACH, mode=ro), `migrate(conn) -> int`(적용 후 user_version), `make_catalog(tmp_path) -> Path`(픽스처: disclosures/corps/entries/audit_report_facts/extraction_reviews 최소 컬럼 + 샘플 행).

- [ ] **Step 1: 실패 테스트 작성**
```python
# tests/test_gold_db.py
import sqlite3, pytest
from research.gold.db import open_gold, migrate
from tests.gold_fixtures import make_catalog

def test_migrate_creates_tables(tmp_path):
    conn = open_gold(tmp_path / "gold.db", None)
    assert migrate(conn) >= 1
    names = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
    assert {"gold_runs","gold_samples","gold_labels","gold_label_history",
            "gold_scores","extractor_snapshots"} <= names

def test_migrate_idempotent(tmp_path):
    conn = open_gold(tmp_path / "gold.db", None)
    v = migrate(conn); assert migrate(conn) == v

def test_catalog_attached_read_only(tmp_path):
    cat = make_catalog(tmp_path)
    conn = open_gold(tmp_path / "gold.db", cat)
    assert conn.execute("select count(*) from cat.disclosures").fetchone()[0] > 0
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("delete from cat.disclosures")
```
- [ ] **Step 2: 실패 확인** — `python -m pytest tests/test_gold_db.py -v` → `ModuleNotFoundError: research.gold`
- [ ] **Step 3: 최소 구현**
```python
# research/gold/db.py
from __future__ import annotations
import sqlite3
from pathlib import Path
from research.gold.schema import MIGRATIONS

def open_gold(gold_path: Path, catalog_path: Path | None) -> sqlite3.Connection:
    conn = sqlite3.connect(gold_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    if catalog_path is not None:
        uri = Path(catalog_path).resolve().as_uri() + "?mode=ro"
        conn.execute("ATTACH DATABASE ? AS cat", (uri,))
    return conn

def migrate(conn: sqlite3.Connection) -> int:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version, ddl in enumerate(MIGRATIONS, start=1):
        if version > current:
            conn.executescript(ddl)
            conn.execute(f"PRAGMA user_version={version}")
    conn.commit()
    return conn.execute("PRAGMA user_version").fetchone()[0]
```
  `open_gold`는 ATTACH 전에 `sqlite3.connect(..., uri=True)`가 필요하므로 `sqlite3.connect(gold_path.as_uri(), uri=True)`로 연다(테스트로 확인).
  `schema.py`의 `MIGRATIONS[0]`: 설계서 §4.1–4.3 DDL 그대로(gold_runs, gold_samples[role IN main/reserve/oversample, meta JSON], gold_labels, gold_label_history, gold_scores) + `extractor_snapshots(extractor_version, rcept_no, dcm_no, payload TEXT NOT NULL, captured_at TEXT NOT NULL, PRIMARY KEY(extractor_version, rcept_no, dcm_no))`.
- [ ] **Step 4: 통과 확인** — 같은 명령 → 3 passed
- [ ] **Step 5: 커밋** — `git add research/gold tests/gold_fixtures.py tests/test_gold_db.py; git commit -m "feat(gold): gold.db schema and read-only catalog attach"`

---

### Task 2: 기간 판정(periods)

**Files:** Create `research/gold/periods.py`, `tests/test_gold_periods.py`

**Interfaces:**
- Produces: `assign_period(rcept_dt: str, fye: str | None, dtd: str | None, is_correction: bool = False) -> tuple[str, str | None]` → (`"P1".."P7"` 또는 `"OUT"`, 하위기간), `FLAGGED_PERIODS = frozenset({"P1a","P2","P5","P7"})`, `layout_era(fye) -> "old"|"new"|None`.

- [ ] **Step 1: 실패 테스트**
```python
from research.gold.periods import assign_period
import pytest
@pytest.mark.parametrize("rcept,fye,dtd,exp", [
    ("20010315","2000.12","dart2.dtd",("P1","P1a")),
    ("20050315","2004.12","dart2.dtd",("P1","P1b")),
    ("20080315","2007.12","dart2.dtd",("P2",None)),
    ("20100315","2009.12","dart3.xsd",("P3",None)),
    ("20120315","2011.12","dart3.xsd",("P4","P4a")),
    ("20140315","2013.12","dart3.xsd",("P4","P4b")),
    ("20190320","2018.11","dart3.xsd",("P5",None)),   # FYE 축
    ("20190320","2018.12","dart3.xsd",("P6",None)),
    ("20240228","2023.12","dart3.xsd",("P6",None)),
    ("20240229","2023.12","dart4.xsd",("P7",None)),
    ("20240423","2017.12","dart4.xsd",("P7",None)),   # 정정: 접수일 기준(D4)
    ("19990601","1998.12","dart.dtd",("OUT",None)),
])
def test_assign_period(rcept,fye,dtd,exp):
    assert assign_period(rcept,fye,dtd) == exp

def test_correction_by_filing_date():   # D4: 정정은 접수일 기준
    assert assign_period("20200410","2017.12","dart3.xsd", is_correction=True) == ("P6", None)
    assert assign_period("20200410","2017.12","dart3.xsd") == ("P5", None)
```
- [ ] **Step 2: 실패 확인** — `python -m pytest tests/test_gold_periods.py -v` → ImportError
- [ ] **Step 3: 구현**
```python
def _fye_key(fye):  # "2018.12" / "(2018.12)" -> 201812
    if not fye: return None
    d = "".join(ch for ch in fye if ch.isdigit())
    return int(d[:6]) if len(d) >= 6 else None

def assign_period(rcept_dt, fye, dtd, is_correction=False):
    d = int(rcept_dt[:8]); y = d // 10000
    if y < 2000: return ("OUT", None)
    if d >= 20240229: return ("P7", None)
    if y <= 2007: return ("P1", "P1a" if y <= 2001 else "P1b")
    if y == 2008: return ("P2", None)
    if y <= 2011: return ("P3", None)
    if y <= 2014: return ("P4", "P4a" if y == 2012 else "P4b")
    if is_correction and d >= 20190101: return ("P6", None)   # D4
    k = _fye_key(fye)
    if k is not None and k >= 201812: return ("P6", None)
    return ("P5", None)
```
  주: 정정 여부는 `disclosures.correction_type` 비어있지 않음으로 판정. 2019년 이후 접수된 FYE<2018.12 정정은 D4대로 P6에 배정하고 `meta.layout_era='old'` 기록(설계 §12-1에서 별도 층 여부 미결). `dtd`는 메타 검증용(불일치 시 `meta.period_dtd_mismatch=True`).
- [ ] **Step 4: 통과 확인** · **Step 5: 커밋** `feat(gold): period assignment`

---

### Task 3: 채점 단위(subjects)와 리뷰 subject 매핑

**Files:** Create `research/gold/subjects.py`, `tests/test_gold_subjects.py`

**Interfaces:**
- Consumes: `research.extracting.field_bundles.BUNDLE_KEYS`
- Produces: `ACCOUNTS: tuple[str,...]`(11개), `subjects_for(bundle) -> list[str]`, `TABLE_BUNDLES = {"hours","activities","communications"}`, `extract_predicted(fact_row: dict, bundle, subject) -> object | None`, `REVIEW_SUBJECT_MAP: dict[tuple[str,str], str]`.

- [ ] **Step 1: 실패 테스트**
```python
from research.gold.subjects import subjects_for, ACCOUNTS, extract_predicted
from research.extracting.field_bundles import BUNDLE_KEYS
def test_every_bundle_has_subjects():
    for b in BUNDLE_KEYS: assert subjects_for(b)
def test_accounts_22_cells():
    s = subjects_for("accounts"); assert len(s) == 22 and "total_asset@prior" in s
def test_icfr_two_subjects():
    assert subjects_for("icfr") == ["engagement","opinion"]
def test_extract_account_display_value():
    row = {"accounts": '[{"account":"inventory","period":"current","raw":"1,234","unit_raw":"천원","unit_scale":1000,"value":1234}]'}
    assert extract_predicted(row,"accounts","inventory@current") == {"raw":"1,234","unit_raw":"천원","value":1234}
    assert extract_predicted(row,"accounts","inventory@prior") is None
```
- [ ] **Step 2: 실패 확인** · **Step 3: 구현** — 스칼라 매핑: auditor→`auditor_resolved`, opinion→`opinion_resolved`, gaap→`gaap_resolved`, audit_report_date→`audit_report_date`, current_period→`current_period_resolved`, icfr→engagement:`icfr_engagement`/opinion:`icfr_opinion_code`, going_concern→`going_concern`, subsidiary→`subsidiary_count`; 표 묶음 subject `"table"` → JSON 원문 반환; 계정 subject `f"{acct}@{period}"`. 매핑표에 `("hours","audit_current_total")→"table"`, `("accounts",acct)→f"{acct}@current"`.
- [ ] **Step 4: 통과 확인** · **Step 5: 커밋** `feat(gold): scoring subjects`

---

### Task 4: 표본기 — 모집단·층·해시 순위·할당

**Files:** Create `research/gold/sampler.py`, `tests/test_gold_sampler.py`; Modify `tests/gold_fixtures.py`(기간별 수백 행 합성 생성 함수 `make_population(tmp_path, n_per_year=60)`)

**Interfaces:**
- Consumes: `assign_period`, `open_gold`, `migrate`
- Produces: `SampleParams(seed="gold-2026-10", per_period=400, blind_ratio=0.10, reserve_ratio=0.10, min_alloc=15, p4b_min=80)`, `rank_hash(seed, *parts) -> int`, `load_population(conn) -> list[PopRow]`, `stratum_key(row) -> str`, `allocate(counts: dict[str,int], n: int, min_alloc: int) -> dict[str,int]`, `build_sample(conn, params) -> str(run_id)`.

- [ ] **Step 1: 실패 테스트**
```python
from research.gold.sampler import rank_hash, allocate, build_sample, SampleParams
from research.gold.db import open_gold, migrate
from tests.gold_fixtures import make_population

def test_rank_hash_stable():
    assert rank_hash("s","1","2") == rank_hash("s","1","2") != rank_hash("t","1","2")

def test_allocate_sums_and_min():
    a = allocate({"A":1000,"B":30,"C":5}, 100, min_alloc=15)
    assert sum(a.values()) == 100 and a["B"] >= 15 and a["C"] == 5

def _run(tmp_path, seed):
    cat = make_population(tmp_path)
    conn = open_gold(tmp_path / f"{seed}.db", cat); migrate(conn)
    rid = build_sample(conn, SampleParams(seed=seed, per_period=40))
    return conn, rid

def test_reproducible(tmp_path):
    c1, r1 = _run(tmp_path, "x"); c2, r2 = _run(tmp_path, "x")
    q = "select rcept_no,dcm_no,mode,role from gold_samples order by 1,2"
    assert c1.execute(q).fetchall() == c2.execute(q).fetchall()

def test_blind_and_reserve_ratio(tmp_path):
    c, _ = _run(tmp_path, "x")
    for p in ("P6","P7"):
        main = c.execute("select count(*) from gold_samples where period=? and role='main'",(p,)).fetchone()[0]
        blind = c.execute("select count(*) from gold_samples where period=? and mode='blind'",(p,)).fetchone()[0]
        assert main == 40 and blind == 4

def test_excludes_f003_and_out(tmp_path):
    c, _ = _run(tmp_path, "x")
    assert c.execute("select count(*) from gold_samples where period='OUT'").fetchone()[0] == 0

def test_overlap_flag(tmp_path):
    c, _ = _run(tmp_path, "x")
    flags = [r[0] for r in c.execute("select json_extract(meta,'$.in_extraction_reviews') from gold_samples")]
    assert set(flags) <= {0,1} and 1 in flags
```
- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현** — 핵심:
```python
import hashlib
def rank_hash(seed, *parts):
    return int(hashlib.sha256("|".join((seed,)+parts).encode()).hexdigest()[:16], 16)
```
  - 모집단 SQL(읽기 전용): `cat.audit_report_facts f JOIN cat.disclosures d USING(rcept_no) LEFT JOIN cat.corps c ON c.corp_code=d.corp_code WHERE f.fetch_status='ok' AND f.source_report_type IN ('F001','F002','A001')` + `cat.entries`에서 dtd(cover_entry_id)·KAM(`section_name LIKE '%핵심감사사항%' AND section_name NOT LIKE '%수주산업%'`), `extraction_reviews` 존재 여부. 원본·정정 모두 포함(D4).
  - 층 키: `period|sub|scope|form|market|kam|opinion_nonclean|correction` (P6/P7만 뒤 3개).
  - `allocate`: 최소할당 후 최대잔여법 비례. P4b ≥ p4b_min. 과도기 창(2015-01~04, 2019-01~03, 2024-02-26~03-08, 2009-01~02)은 층 키에 `tr=1`로 넣어 최소할당.
  - 층 내 `rank_hash(seed, rcept_no, dcm_no)` 오름차순 → main n_h, 다음 순위 reserve(10%). 블라인드: main 중 `rank_hash(seed,"blind",...)` 상위 10%(층 비례). `queue_order`: 기간 내 순위, 블라인드는 10번째마다 배치되도록 재배열. `stratum_weight=N_h/n_h`. `gold_runs.params/stats` 기록, `population_sql_sha`.
- [ ] **Step 4: 통과 확인** · **Step 5: 커밋** `feat(gold): reproducible stratified sampler`

---

### Task 5: 희소 필드 판정·과표집(D11)

**Files:** Modify `research/gold/sampler.py`; Create `tests/test_gold_oversample.py`

**Interfaces:**
- Consumes: `build_sample`, `extract_predicted`, 스냅샷(Task 6 이전이므로 카탈로그 facts 직접)
- Produces: `find_sparse_fields(conn, run_id, threshold=383) -> list[tuple[str,str]]`(bundle,subject; 풀링 claim < threshold 또는 기간 claim < threshold), `oversample(conn, run_id, field, target=383) -> int`(추가 건수), `CLAIM_FILTERS: dict[str, str]`(SQL 조건).

- [ ] **Step 1: 실패 테스트**
```python
def test_sparse_detected_and_oversampled(tmp_path):
    c, rid = _run(tmp_path, "x")   # per_period=40 → 모든 필드 희소
    sparse = find_sparse_fields(c, rid, threshold=60)
    assert ("icfr","opinion") in sparse
    added = oversample(c, rid, ("icfr","opinion"), target=60)
    rows = c.execute("select json_extract(meta,'$.oversample_for') from gold_samples where role='oversample'").fetchall()
    assert added == len(rows) and all(r[0] == "icfr:opinion" for r in rows)

def test_oversample_only_docs_with_claim(tmp_path):
    ...  # 과표집 문서 모두 icfr_status='ok' 확인(전체 코드는 구현 시 동일 패턴)
```
  (두 번째 테스트 본문: `assert all(c.execute("select icfr_status from cat.audit_report_facts where rcept_no=? and dcm_no=?", (r,d)).fetchone()[0]=="ok" for r,d in c.execute("select rcept_no,dcm_no from gold_samples where role='oversample'"))`)
- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현** — `CLAIM_FILTERS`: icfr→`icfr_status='ok'`, subsidiary→`fs_scope='consolidated' AND subsidiary_status='ok'`, hours/activities/communications→`<bundle>_status='ok'`, 계정→`accounts LIKE '%"account": "<acct>"%'`. 과표집은 기존 표본 제외, 기간 비례 배분, 같은 시드 해시 순서, `role='oversample'`, `mode='prefill'`, `meta.oversample_for="bundle:subject"`, 필드별 가중치 `meta.field_weight=N_h(field)/n_h(field)`. `gold_runs.params.sparse_fields` 갱신.
- [ ] **Step 4: 통과** · **Step 5: 커밋** `feat(gold): sparse-field oversampling (D11)`

---

### Task 6: 추출기 버전 스냅샷(D8)

**Files:** Create `research/gold/snapshots.py`, `scripts/gold_snapshot.py`, `tests/test_gold_snapshots.py`

**Interfaces:**
- Produces: `capture(conn, run_id, version: str | None = None) -> int`(기본 `EXTRACTOR_VERSION`; 대상 = 해당 run의 모든 gold_samples; 이미 있으면 덮어쓰지 않고 건너뜀), `load_snapshot(conn, version, rcept_no, dcm_no) -> dict | None`, `versions(conn) -> list[str]`.

- [ ] **Step 1: 실패 테스트**
```python
def test_capture_and_load(tmp_path):
    c, rid = _run(tmp_path, "x")
    n = capture(c, rid, "audit_opinion.v19")
    assert n == c.execute("select count(*) from gold_samples").fetchone()[0]
    r = c.execute("select rcept_no,dcm_no from gold_samples limit 1").fetchone()
    snap = load_snapshot(c, "audit_opinion.v19", r[0], r[1])
    assert snap["extractor_version"] == "audit_opinion.v19"
    assert capture(c, rid, "audit_opinion.v19") == 0      # 멱등

def test_version_mismatch_refused(tmp_path):
    c, rid = _run(tmp_path, "x")
    with pytest.raises(ValueError):   # 카탈로그 행 버전 ≠ 요청 버전
        capture(c, rid, "audit_opinion.v20")
```
- [ ] **Step 2: 실패 확인** · **Step 3: 구현** — `SELECT * FROM cat.audit_report_facts WHERE rcept_no=? AND dcm_no=?` → dict → `json.dumps(ensure_ascii=False)`; 행의 `extractor_version`이 요청과 다르면 `ValueError`. CLI: `python scripts/gold_snapshot.py --gold C:\dev\dart-wrapper\data\gold\gold.db --catalog ..\web-api\dart_catalog.db --run gold-2026-10`.
- [ ] **Step 4: 통과** · **Step 5: 커밋** `feat(gold): per-version extractor snapshots`

---

### Task 7: 일치 규칙(matching)

**Files:** Create `research/gold/matching.py`, `tests/test_gold_matching.py`

**Interfaces:**
- Produces: `matches(bundle, subject, predicted, gold_value) -> bool`, `normalize_auditor(s) -> str`, `normalize_amount(raw: str) -> int | None`.

- [ ] **Step 1: 실패 테스트**
```python
from research.gold.matching import matches, normalize_amount
def test_auditor_normalized():
    assert matches("auditor","value","삼일 회계법인","삼일회계법인")
def test_amount_display_unit_exact():
    p = {"raw":"(1,234)","unit_raw":"천원","value":-1234}
    assert matches("accounts","inventory@current",p,{"display":"-1234","unit":"천원"})
    assert not matches("accounts","inventory@current",p,{"display":"-1234","unit":"원"})  # 단위 오류=FP
    assert not matches("accounts","inventory@current",p,{"display":"-1235","unit":"천원"})
def test_negative_parentheses():
    assert normalize_amount("(1,234)") == -1234 and normalize_amount("△1,234") == -1234
def test_table_uses_verdict_only():
    assert matches("hours","table",[{"x":1}],{"verdict":"correct"})
```
- [ ] **Step 2–4** 구현: 문자열 공백·괄호 제거, "회계법인"·"(주)"·"주식회사" 제거, 영문 casefold; 날짜 ISO 비교; enum 동일; 금액 `normalize_amount(raw)==int(display)` 그리고 단위 문자열 정규화(`원`,`천원`,`백만원`) 동일; 표 묶음은 gold_value의 verdict.
- [ ] **Step 5: 커밋** `feat(gold): field matching rules`

---

### Task 8: 라벨 저장·이력·큐

**Files:** Create `research/gold/labels.py`, `tests/test_gold_labels.py`

**Interfaces:**
- Produces: `save_label(conn, *, rcept_no, dcm_no, bundle, subject, pass_, verdict, gold_value, shown_value, shown_version, evidence=None, error_tag=None, note="", seconds=None) -> None`(기존 행은 `gold_label_history`로 이동), `next_doc(conn, run_id, period, pass_) -> tuple[str,str] | None`, `complete_doc(conn, run_id, rcept_no, dcm_no, pass_) -> None`(미판정 subject 있으면 `ValueError`), `exclude_doc(conn, run_id, rcept_no, dcm_no, reason) -> tuple[str,str] | None`(같은 층 reserve 승격), `required_subjects(conn, run_id, rcept_no, dcm_no) -> list[tuple[str,str]]`(oversample이면 해당 필드만).

- [ ] **Step 1: 실패 테스트**
```python
def test_label_history(tmp_path):
    c, rid = _run(tmp_path, "x"); r = _first(c)
    save_label(c, **r, bundle="opinion", subject="value", pass_="prefill", verdict="correct",
               gold_value="unqualified", shown_value="unqualified", shown_version="audit_opinion.v19")
    save_label(c, **r, bundle="opinion", subject="value", pass_="prefill", verdict="wrong",
               gold_value="qualified", shown_value="unqualified", shown_version="audit_opinion.v19")
    assert c.execute("select count(*) from gold_label_history").fetchone()[0] == 1

def test_blind_prefill_ordering(tmp_path):
    # 블라인드 문서는 blind 완료 후 최소 20건 뒤에야 prefill 큐에 등장
    ...
def test_complete_requires_all(tmp_path):
    c, rid = _run(tmp_path, "x"); r = _first(c)
    with pytest.raises(ValueError): complete_doc(c, rid, r["rcept_no"], r["dcm_no"], "prefill")
def test_exclude_promotes_reserve(tmp_path):
    c, rid = _run(tmp_path, "x"); r = _first(c)
    promoted = exclude_doc(c, rid, r["rcept_no"], r["dcm_no"], "감사의감사보고서")
    assert promoted is not None
def test_never_writes_extraction_reviews(tmp_path):
    # cat 이 read-only 이므로 구조적으로 불가 — 소스에 'extraction_reviews' 쓰기 SQL 없음을 확인
    import inspect, research.gold.labels as m
    assert "insert into cat.extraction_reviews" not in inspect.getsource(m).lower()
```
  (`test_blind_prefill_ordering` 본문: 블라인드 문서 B의 blind 라벨 완료 → `next_doc(...,"prefill")`를 19회 호출·완료해도 B가 나오지 않고, 20회 이후 나오는지 assert.)
- [ ] **Step 2–4** 구현 · **Step 5: 커밋** `feat(gold): labels, history, queues`

---

### Task 9: 채점·Wilson·풀링·블라인드 비교

**Files:** Create `research/gold/scoring.py`, `scripts/gold_score.py`, `tests/test_gold_scoring.py`

**Interfaces:**
- Consumes: `load_snapshot`, `extract_predicted`, `matches`, `gold_final`(이 태스크에서 정의)
- Produces: `wilson(k: int, n: float, z=1.96) -> tuple[float,float]`, `gold_final(conn) -> Iterator[Label]`(blind·prefill 불일치는 `adjudication` 라벨 우선, 없으면 제외+목록), `score(conn, version) -> int`(gold_scores 재생성), `metrics(conn, run_id, version) -> list[MetricRow]`(MetricRow: scope("period"|"pooled"), period, bundle, subject, n_claim, tp, fp, precision, lo, hi, weighted_lo, n_eff, passed, flag_period_report, note), `blind_report(conn, version) -> list[dict]`.

- [ ] **Step 1: 실패 테스트**
```python
from research.gold.scoring import wilson
def test_wilson_known_values():
    assert round(wilson(400,400)[0],4) == 0.9905
    assert round(wilson(399,400)[0],4) == 0.9860
    assert round(wilson(300,300)[0],4) == 0.9874
    assert wilson(383,383)[0] >= 0.99 > wilson(382,382)[0]

def test_pooled_for_sparse(tmp_path):
    c, rid = _scored_fixture(tmp_path, sparse=[("icfr","opinion")])
    rows = metrics(c, rid, "audit_opinion.v19")
    icfr = [r for r in rows if r.bundle=="icfr" and r.subject=="opinion"]
    assert any(r.scope=="pooled" for r in icfr)
    assert all(not r.passed for r in icfr if r.scope=="period")  # 기간 셀은 판정 안 함(passed=False, note='pooled')

def test_flagged_period_reported_separately(tmp_path):
    c, rid = _scored_fixture(tmp_path, sparse=[("icfr","opinion")], fp_in="P7")
    p7 = [r for r in metrics(c, rid, "audit_opinion.v19")
          if r.bundle=="icfr" and r.period=="P7"]
    assert p7 and p7[0].flag_period_report and "주의" in p7[0].note

def test_unit_error_is_fp(tmp_path): ...
def test_na_with_claim_is_fp(tmp_path): ...
def test_oversample_excluded_from_other_fields(tmp_path): ...
```
  (생략된 세 테스트 본문은 `_scored_fixture`로 해당 라벨 1건 만들고 `score()` 후 `gold_scores.outcome=='fp'` 또는 다른 필드 n_claim 불변을 assert.)
- [ ] **Step 2: 실패 확인**
- [ ] **Step 3: 구현**
```python
import math
def wilson(k, n, z=1.96):
    if n <= 0: return (0.0, 1.0)
    p = k / n; d = 1 + z*z/n; c = p + z*z/(2*n)
    r = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n))
    return ((c - r) / d, (c + r) / d)
```
  - claim = 스냅샷 예측값 non-null(그리고 `*_status=='ok'`). gold verdict `na` + claim → FP. TP = `matches`.
  - 기간 셀: main 표본만. 풀링 셀(희소 필드): main+oversample, 기간 층 가중 정밀도 `Σ w_h tp_h / Σ w_h claim_h`, 유효표본수 `n_eff=(Σw)^2/Σw^2`(claim 단위), `weighted_lo = wilson(p*n_eff, n_eff)[0]`. 통과 = 희소 필드는 풀링 `weighted_lo ≥ 0.99`, 그 외는 기간 셀 `lo ≥ 0.99`.
  - `flag_period_report`: period ∈ FLAGGED_PERIODS(P1a 포함 기간 P1, P2, P5, P7) 또는 풀링 내 기간 FP 비율 > 전체 2배. 플래그 기간 FP ≥1 → note "주의".
  - CLI: `python scripts/gold_score.py --gold ... --version audit_opinion.v19 --out C:\dev\dart-wrapper\data\gold\metrics\audit_opinion.v19\precision.csv`.
- [ ] **Step 4: 통과** · **Step 5: 커밋** `feat(gold): scoring, Wilson LB, pooled sparse fields`

---

### Task 10: 근거 연결(evidence)

**Files:** Create `research/gold/evidence.py`, `tests/test_gold_evidence.py`

**Interfaces:**
- Consumes: 카탈로그 `cat.entries`, `research.extracting.field_bundles.DART_DOCUMENT_VIEW`, `research.gold.cache.load_section_html`(Task 11)
- Produces: `ENTRY_FIELDS: dict[str, list[str]]`(bundle→facts의 `*_entry_id` 컬럼 우선순위; accounts→[bs_entry_id,is_entry_id,fs_parent_entry_id], hours/activities/communications→[activity_entry_id] …), `evidence_for(conn, snapshot: dict, bundle) -> list[Evidence]`(Evidence: entry_id, section_name, viewer_url, dart_url), `annotate_cells(html: str) -> str`(모든 td/th에 `data-t/r/c`), `find_cells(html, raw: str, label: str | None) -> list[tuple[int,int,int]]`.

- [ ] **Step 1: 실패 테스트**
```python
def test_annotate_and_find():
    html = "<table><tr><td>재고자산</td><td>1,234</td><td>999</td></tr></table>"
    out = annotate_cells(html)
    assert 'data-t="0" data-r="0" data-c="1"' in out
    assert find_cells(out, "1,234", "재고자산") == [(0,0,1)]
def test_evidence_uses_entries(tmp_path): ...  # 픽스처 entry viewer_url 반환 확인
```
- [ ] **Step 2–4** 구현(표준 라이브러리 `html.parser` 기반; 외부 의존성 추가 없음. 같은 행에 label 포함 셀이 있으면 우선) · **Step 5: 커밋** `feat(gold): evidence linking and cell highlight`

---

### Task 11: 원문 사전 캐시(D5) — 박스 재사용 + 보충 목록

**Files:** Create `research/gold/cache.py`, `scripts/gold_cache.py`, `tests/test_gold_cache.py`

**Interfaces:**
- Produces: `CACHE_ROOT` 기본 `C:\dev\dart-wrapper\data\gold_cache`, `cache_dir(root, rcept_no) -> Path`, `plan_cache(conn, run_id, root, box_mirror: Path) -> CachePlan(present, from_box, missing)`, `import_from_box(plan) -> int`(로컬 복사만), `load_section_html(root, rcept_no, entry: dict) -> str | None`(로컬 파일만, 네트워크 없음), `write_missing_list(plan, path)`.

- [ ] **Step 1: 실패 테스트**
```python
def test_plan_classifies(tmp_path):
    c, rid = _run(tmp_path, "x")
    box = tmp_path/"box"; _mk_box_doc(box, "2019", first_rcept(c))
    plan = plan_cache(c, rid, tmp_path/"cache", box)
    assert first_rcept(c) in plan.from_box and plan.missing
def test_load_section_offline(tmp_path, monkeypatch):
    import socket
    monkeypatch.setattr(socket, "socket", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    assert load_section_html(tmp_path/"cache", "000", {"ele_id":"1"}) is None
```
- [ ] **Step 2–4** 구현 — 박스 미러 구조: `<box_mirror>/<연도>/<rcpNo>/{main.html,toc.json,secNN.html,attN/,atts.json}`. `gold_cache.py plan|import|missing` 서브커맨드. **`fetch` 서브커맨드는 만들지 않는다**(Step 6 참고).
- [ ] **Step 5: 커밋** `feat(gold): source cache planning and box reuse`
- [ ] **Step 6 (⚠ 윤석님 승인 필요 — DART 네트워크)**: `missing.csv` 건수와 예상 시간(기존 `packages/entry-extractor` 수집기, 초당 1건 이하, 403/429 시 즉시 중단)을 보고하고 승인받은 뒤에만 실행. 이 단계는 별도 실행 기록 `data/gold_cache/FETCH_LOG.md`에 승인 일시·건수 기록. 승인 전에는 누락 문서를 `viewer_url` 새 창 링크로만 표시(사람 클릭).
  - 박스 원문 전달: 박스 `/workspace/dart-sample/docs`를 압축 → 노트북 `C:\dev\dart-wrapper\data\box_mirror\`로 복사(윤석님 확인 후).

---

### Task 12: `/admin/gold` 라우터 — 대시보드·문서 화면·라벨 API

**Files:**
- Create: `research/api/admin/gold.py`, `research/templates/admin/gold/dashboard.html`, `research/templates/admin/gold/doc.html`, `research/templates/admin/gold/partials/field_rows.html`, `research/templates/admin/gold/partials/evidence.html`
- Modify: `tests/conftest.py`(`create_app`에 `app.include_router(admin_gold.router)` 추가), `research/config.py`(`gold_db_path: str = "C:/dev/dart-wrapper/data/gold/gold.db"`, `gold_cache_root`, `gold_run_id = "gold-2026-10"` — `ResearchSettings`)
- Test: `tests/test_admin_gold_ui.py`

**Interfaces:**
- Consumes: `open_gold`, `next_doc`, `save_label`, `complete_doc`, `exclude_doc`, `load_snapshot`, `subjects_for`, `extract_predicted`, `evidence_for`, `load_section_html`, `annotate_cells`; 인증은 `reviews.py`의 `_has_valid_token`/`ADMIN_TOKEN_COOKIE` 패턴 재사용(공통 함수로 import).
- Produces: 라우트 `GET /admin/gold`, `GET /admin/gold/next?period=&pass=`, `GET /admin/gold/doc/{rcept_no}/{dcm_no}?pass=prefill|blind`, `GET /admin/gold/evidence/{rcept_no}/{dcm_no}/{bundle}?pass=`, `POST /admin/gold/label`(JSON), `POST /admin/gold/doc/{rcept_no}/{dcm_no}/complete`, `POST .../exclude`, `GET /admin/gold/metrics?version=`, 의존성 `get_gold_conn()`.

- [ ] **Step 1: 실패 테스트**(기존 `client_factory` 픽스처 + 토큰 쿠키 패턴은 `tests/test_admin_reviews_ui.py`와 동일)
```python
async def test_requires_token(client_factory, gold_env):
    async with client_factory() as c:
        r = await c.get("/admin/gold", follow_redirects=False)
        assert r.status_code in (302, 303)

async def test_blind_hides_extracted_values(authed_client, gold_env):
    doc = gold_env.blind_doc
    r = await authed_client.get(f"/admin/gold/doc/{doc.rcept_no}/{doc.dcm_no}?pass=blind")
    assert r.status_code == 200
    for v in doc.extracted_strings:          # 예: '회계법인서정', 'unqualified', '15,277,377,649'
        assert v not in r.text
    assert 'data-evidence-autonav="1"' in r.text   # D6: 자동 이동 허용
    assert 'data-highlight="0"' in r.text          # 셀 하이라이트 끔

async def test_prefill_shows_values_and_overlap_badge(authed_client, gold_env): ...
async def test_label_post_roundtrip(authed_client, gold_env): ...
async def test_evidence_offline_fallback_link(authed_client, gold_env): ...  # 캐시 없으면 viewer_url 링크만
async def test_no_llm_import():
    import research.api.admin.gold as g, inspect
    src = inspect.getsource(g)
    assert "llm_date_resolver" not in src and "DateResolverService" not in src
```
  (생략 본문: prefill 화면에 `doc.extracted_strings[0]` 포함·`in_extraction_reviews` 배지 포함 / POST 후 `gold_labels` 1행 / 캐시 없는 문서의 evidence 응답에 `dart.fss.or.kr` 링크·iframe 없음.)
- [ ] **Step 2: 실패 확인** — `python -m pytest tests/test_admin_gold_ui.py -v`
- [ ] **Step 3: 구현** — 서버 렌더 + 부분 HTML. 블라인드 렌더 시 템플릿 컨텍스트에서 **예측값 키 자체를 넘기지 않는다**(템플릿 실수로 노출 불가). `get_gold_conn`은 요청마다 `open_gold(settings.gold_db_path, catalog_path)` (카탈로그 경로는 web-api `Settings`의 DB 경로에서 파생).
- [ ] **Step 4: 통과** · **Step 5: 커밋** `feat(gold): /admin/gold router and document screen`

---

### Task 13: 키보드 맵·자동 저장·계정 하이라이트(JS)

**Files:**
- Create: `research/templates/admin/gold/partials/gold_js.html`(인라인 `<script>`; 정적 파일 마운트 추가 불필요)
- Modify: `research/templates/admin/gold/doc.html`
- Test: `tests/test_admin_gold_ui.py`(마크업 계약), 수동 체크리스트

**Interfaces:**
- Consumes: Task 12 마크업 계약 — 필드 행 `<li class="gold-row" data-bundle data-subject data-verdict>`, 근거 셀 `data-t/r/c`, 행의 `data-cells="[[t,r,c],...]"`, `POST /admin/gold/label`.
- Produces: 키 맵(설계 §6.6): j/k·↑/↓, 1/y 맞다, 2/n 틀리다(입력 포커스), 3/x 해당없음, 4/? 보류, Space 순환, Enter 근거 이동, e/m/t, Tab 그룹, a 그룹 일괄 맞다(블라인드 비활성, 사용 로그 `bulk_accept` 전송), o DART 새 창, Ctrl+Enter 완료, Ctrl+Shift+X 제외, Esc.

- [ ] **Step 1: 실패 테스트(마크업 계약)**
```python
async def test_rows_have_contract(authed_client, gold_env):
    r = await authed_client.get(gold_env.prefill_url)
    assert r.text.count('class="gold-row"') == gold_env.expected_rows
    assert 'data-subject="total_asset@prior"' in r.text
async def test_blind_disables_bulk_accept(authed_client, gold_env):
    r = await authed_client.get(gold_env.blind_url)
    assert 'data-bulk-accept="0"' in r.text
```
- [ ] **Step 2–4** 구현 · 수동 확인 체크리스트(브라우저, 노트북 로컬): 키 각각 동작, 저장 실패 토스트, 저장 후 재조회, 계정 클릭 시 셀 하이라이트·스크롤, 틀리다 시 셀 클릭으로 값 채움.
- [ ] **Step 5: 커밋** `feat(gold): keyboard-first review UI`

---

### Task 14: 파일럿 마일스톤 — P6/P7 (실데이터, 읽기 전용)

**Files:** Create `docs/superpowers/plans/2026-10-31-gold-review-pilot.md`(결과 기록), `data/gold/`(gitignore 확인)

- [ ] **Step 1 (윤석님 확인 권장)**: 실DB로 표본 생성
```powershell
cd C:\dev\dart-wrapper\packages\research
$env:DART_LLM_ENABLED='false'
python scripts\gold_sample.py --gold C:\dev\dart-wrapper\data\gold\gold.db --catalog ..\web-api\dart_catalog.db --seed gold-2026-10 --per-period 400
```
  기대: 층별 N/n 표 출력, P1–P7 main 각 400, blind 각 40, reserve 각 40. `dart_catalog.db` mtime 불변 확인(`(Get-Item ..\web-api\dart_catalog.db).LastWriteTime` 전후 비교).
- [ ] **Step 2**: 재현성 확인 — 임시 경로로 한 번 더 생성 후 `gold_samples` 비교 스크립트(`scripts\gold_sample.py --verify-against ...`) → 차이 0.
- [ ] **Step 3**: `gold_snapshot.py`로 v19 스냅샷 → 건수 = 표본 수.
- [ ] **Step 4**: 희소 필드 목록 출력(`gold_sample.py --report-sparse`), 과표집은 **파일럿에서는 계획 수치만** 기록.
- [ ] **Step 5**: `gold_cache.py plan` → box 재사용/누락 건수 보고. 누락분 DART 수집은 Task 11 Step 6 승인 절차.
- [ ] **Step 6**: 앱 실행(기존 연구 앱 로컬 실행 방식 — `tests/conftest.py`의 `create_app`과 같은 라우터 구성으로 띄우는 `research/local_app.py` 진입점이 없으면 이 태스크에서 추가: `uvicorn research.local_app:app --port 8010`) → P7 30건(블라인드 3건 포함), P6 30건 검수.
- [ ] **Step 7**: 측정·판단
  - 문서당 active_seconds 중앙값(prefill/blind) vs 설계 추정(P5–P7 prefill 10분, blind 20분)
  - 셀 하이라이트 적중률(텍스트 매칭), 근거 누락 문서 수, 키보드 불편 사항
  - `gold_score.py` 시험 실행 → CSV 생성 확인(파일럿 n이 작아 통과 판정은 의미 없음)
- [ ] **Step 8**: 결과를 파일럿 문서에 기록하고 UI·추정치 조정 항목을 정리 → 윤석님 검토 후 본 검수 시작.

**파일럿 완료 기준:** 60건 완료, 데이터 손실 0, 블라인드 화면 추출값 노출 0(Task 12 테스트 + 육안), 카탈로그 DB 무변경, 네트워크 호출 0(승인된 수집 제외).

---

### Task 15: 버전 변경 재채점·표 묶음 재검수 큐

**Files:** Modify `research/gold/scoring.py`, `research/gold/labels.py`; Create `tests/test_gold_rescore.py`

**Interfaces:**
- Produces: `table_carryover(conn, old_version, new_version) -> list[ReReview]`(표 JSON 정규화 비교; 동일→승계, hours는 핵심값(총 감사시간·인원) 비교로 FP 자동 확정 또는 재검수 큐), `rescore(conn, new_version) -> int`.

- [ ] **Step 1: 실패 테스트**
```python
def test_identical_table_carries_over(tmp_path): ...   # v19와 동일 JSON → 재검수 0
def test_hours_key_value_mismatch_auto_fp(tmp_path): ... # 핵심값 다름 → outcome='fp', 큐 0
def test_hours_changed_but_key_match_queued(tmp_path): ...
def test_scalar_rescored_without_human(tmp_path): ...  # v20 스냅샷 값 변경 → gold_scores 갱신
```
  (각 본문: `capture`로 v19·v20 스냅샷을 픽스처로 직접 삽입 → 함수 호출 → `gold_scores`/큐 행 수 assert.)
- [ ] **Step 2–4** 구현 · **Step 5: 커밋** `feat(gold): version re-scoring and table carry-over`

---

## 자체 점검(설계 대비)
| 설계 항목 | 태스크 |
|---|---|
| D1 Wilson 하한·400건 | 4, 9 |
| D2 gold.db·ATTACH ro | 1 |
| D3 22셀·표시 단위 정확 일치 | 3, 7 |
| D4 원본+정정·접수일 배정 | 2, 4 |
| D5 원문 사전 캐시·박스 재사용 | 11, 14 |
| D6 블라인드 자동 이동·값 비표시 | 12, 13 |
| D7 extraction_reviews 미기록·플래그 | 4, 8, 12 |
| D8 버전 스냅샷 | 6, 15 |
| D9 표 메모+핵심값 | 8, 12, 15 |
| D10 현재 시장 태그 | 4 |
| D11 희소 풀링·과표집·플래그 기간 | 5, 9 |
| 블라인드 vs prefill 비교·adjudication | 8, 9 |
| 키보드 맵 | 13 |
| 파일럿 P6/P7 | 14 |

남은 설계 미결(§12: P5/P6 정정 예외, 셀 좌표, 보충 수집 시점, 상장일 데이터, holdout)은 이 계획에서 **현행 기본값**(정정=접수일 배정+layout_era 메타, 텍스트 매칭, 승인 전 미수집, 현재 시장, holdout 없음)으로 구현하고, 결정 시 해당 태스크만 수정한다.

## 실행 방식
1. **Subagent-Driven(권장)** — 태스크마다 새 서브에이전트, 태스크 간 리뷰.
2. **Inline** — executing-plans로 체크포인트 단위 일괄 실행.
