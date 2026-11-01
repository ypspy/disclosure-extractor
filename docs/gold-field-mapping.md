# 골드 필드 매핑

기준은 `docs/standard-extraction-items.md`다. 추출기 출력은 `src/dart_parser/fallback/schemas.py`의 `StandardExtraction`이다. HANDOFF 설계 v1.1의 v19 12개 묶음(§2.2, `audit_opinion.v19`)과 다르면 이 표가 우선이다. 채점 subject 이름은 v19 `subjects.py`의 축(`value`, `engagement`, `opinion`, `table`, `{계정}@current`, `{계정}@prior`)을 표준 항목에 맞춰 늘린 것이다.

## 확정 (2026-11-01, 윤석님)

이 절이 아래 표보다 우선이다.

1. 계정 정답은 표시값 `value`와 단위 `unit_scale`이 둘 다 같을 때다.
2. 회사명, 문서 제목, 기수, 주석 목차, 매출액, 영업이익은 기간 셀 99% 대상이다. 주석 목차는 개수와 제목 목록 전체를 한 subject로 판정한다.
3. 계속기업은 비적정 의견의 근거로만 있는 경우, 전기 인용만 있는 경우, 청산기준 강조사항만 있는 경우 모두 `1`이다.
4. 감사의견 값은 `적정`, `한정`, `부적정`, `거절`이다. 골드 라벨은 `한정`을 받는다.

1단계로 들어온 `matching.py`는 v19 규칙 그대로다. 계정은 `raw`에서 읽은 표시 정수와 단위 문자열(`원`, `천원`, `백만원`)을 비교한다. 위 1·3·4의 코드 반영과 추출기 수정은 아직이다.

## 공통

한 항목의 출력은 대부분 `Item[T]`다. 경로는 `{키}.status`, `{키}.value`, `{키}.source`, `{키}.evidence`다. `icfr`와 `subsidiary`만 상태 필드가 값 객체 안에 있다.

| 상태 | 골드에서의 뜻 |
| --- | --- |
| `found` | 값이 있다. 이 값만 정밀도 claim에 넣는다. |
| `missing` | 제도 안에 있어야 하는데 없다. 실패다. |
| `not_applicable` | 그 문서 유형에는 해당이 없다. |
| `not_in_regime` | 그 서식 기간에는 제도가 없다. |

v19 판정 `na`는 위 두 비실패 상태를 한 칸에 넣는다. 골드 라벨은 둘을 그대로 둔다. 정답이 `not_applicable` 또는 `not_in_regime`인데 추출기가 값을 냈으면 틀리다(정답=없음).

판정 단위는 세 가지다.

| 단위 | subject | 쓰는 곳 |
| --- | --- | --- |
| 단일 값 | `value` 하나. 내부회계만 `engagement`, `opinion` 둘 | 식별, 스칼라 묶음, 주석 목차 |
| 표 전체 | `table` 하나 | `hours`, `activities`, `communications` |
| 계정 당기·전기 | `{계정}@current`, `{계정}@prior` | `accounts` 13계정, 26칸 |

희소는 측정값이 아니다. HANDOFF §7.5가 v19 스냅샷에서 예상한 목록을 표준 항목으로 옮긴 구분이다. 확정 목록은 나중에 이 추출기 스냅샷으로 `gold_runs.params.sparse_fields`에 고정한다.

| 구분 | 판정 |
| --- | --- |
| 상시 | 기간별 셀. Wilson 95% 하한 ≥ 99% (D1) |
| 희소 | 기간 풀링. 풀링 claim이 383 미만이면 그 필드가 있는 문서만 과표집 (D11) |

문서 안 근거는 `parser/sections.py`의 섹션 창이다. 창 키가 추출기 `evidence`와 같은 항목이 많다. `StandardExtraction.rcept_no`, `fs_scope`, `source`는 표준 항목이 아니다. `fs_scope`(`separate` / `consolidated`)는 문서 제목과 함께 정해지고, 층화와 계정 표 선택에 쓴다.

채점 subject는 42개다. v19 `subjects.py`는 34개(계정 22칸, 식별 3종과 주석 목차 없음)다.

## 식별

보고기간은 아래 `current_period`와 같은 항목이다. 여기서 다시 채점하지 않는다.

| 항목 | 추출기 출력 키 | 판정 단위 | 희소 | 문서 내 근거 | v19 대응 |
| --- | --- | --- | --- | --- | --- |
| 회사명 | `company_name.value` 문자열 | 단일 값 `value` | 상시. 99% 대상 | `cover`. 의견서 제목 앞. 창이 비면 문서 전체 | v19 12개 묶음에 없다. 묶음 키 `company_name`을 새로 둔다. |
| 문서 제목 | `document_title.value`. `감사보고서` 또는 `연결감사보고서` | 단일 값 `value` | 상시. 99% 대상 | `cover` | 연결·별도는 모집단 층으로도 쓴다. 제목 문자열 자체도 99% 대상이다. 묶음 키 `document_title`. |
| 기수 | `fiscal_term.value`. `제N기` | 단일 값 `value` | 상시. 99% 대상 | `cover`의 제N기 | v19 12개 묶음에 없다. 묶음 키 `fiscal_term`. |
| 보고기간 | `current_period` | 12묶음과 동일 | 상시 | `cover` | 아래 당기 행과 같은 subject. |

## 12묶음

| 항목 | 추출기 출력 키 | 판정 단위 | 희소 | 문서 내 근거 | v19 대응 |
| --- | --- | --- | --- | --- | --- |
| 감사인 | `auditor.value` 문자열. 회계법인 또는 감사반 | 단일 값 `value` | 상시 | `opinion_letter`. 창이 비면 문서 전체. 표지에서는 마지막 법인 줄(`cover`) | 묶음 `auditor`, 컬럼 `auditor_resolved`, subject `value`. 출력 키 이름이 `auditor_resolved`가 아니다. |
| 감사의견 | `opinion.value`. `적정`, `한정`, `부적정`, `거절`. 골드 라벨은 네 값을 받는다. 추출기 `extract_opinion_letter`는 아직 `한정`을 내지 않는다 | 단일 값 `value` | 상시. 비적정은 층 최소할당이지 필드 희소가 아니다 | `opinion_letter`의 당기 의견 문단. 창이 비면 문서 전체. 내부회계 문단은 읽지 않는다 | 묶음 `opinion`, 컬럼 `opinion_resolved`. v19 enum은 `unqualified` / `qualified` / `adverse` / `disclaimer`. `qualified`가 `한정`이다. |
| GAAP | `gaap.value.code` (`K-IFRS`, `K-GAAP`), `gaap.value.raw` | 단일 값 `value`. 비교는 `code`. `raw`는 근거로 스냅샷에 남긴다 | 상시 | `opinion_letter` | 묶음 `gaap`, 컬럼 `gaap_resolved` (`k-gaap` / `k-ifrs` / `other`). 이 추출기 코드는 대문자 `K-IFRS`, `K-GAAP`다. 셋째 코드 `other`는 없고, 기준 문구가 없으면 `missing`이다. |
| 감사보고서일 | `audit_report_date.value`. `YYYY-MM-DD` | 단일 값 `value` | 상시. 의견서 창이 비면 `missing`이고, 다른 날짜로 채우지 않는다 | `opinion_letter`의 마지막 날짜 | 묶음 `audit_report_date`, subject `value`. ISO 날짜로 같다. |
| 당기 | `current_period.value`. `Period.start`, `Period.end` (`YYYY-MM-DD`), `Period.raw` | 단일 값 `value`. 식별의 보고기간과 같은 객체 | 상시 | `cover`. 창이 비면 문서 전체 | 묶음 `current_period`, 컬럼 `current_period_resolved`, 형식 `(YYYY.MM)` 하나. 이 추출기는 시작일·종료일·원문이다. |
| 감사시간 | `hours.value.cells[]`. 칸은 `role`, `role_key`, `metric`, `metric_key`, `period`(`current`/`prior`), `value`, `unmapped` | 표 전체 `table`. 역할×지표×기간으로 쪼개지 않는다 | 희소(구서식). 별지 제4호 2절. P5 이전·전환 구간에 claim이 383 미만일 것으로 예상 | `exhibit4_hours` | 묶음 `hours`, subject `table`, JSON 목록. 같다. 칸에 `unmapped`가 있다. 틀린 표의 정답 입력은 D9대로 총 감사시간·투입 인원과 메모로 좁혀도, 채점 단위는 표 하나다. |
| 실시항목 | `activities.value`의 7키. `planning`, `fieldwork`, `inventory_observation`(내용·시기·장소·대상), `financial_asset_observation`(같음), `external_confirmations`(`financial`, `receivables_payables`, `legal`, `other`), `tcwg_communication`, `expert` | 표 전체 `table`. 절차마다 subject를 두지 않는다 | 희소(구서식). 별지 제4호 3절. 감사시간과 같은 기간 조건 | `exhibit4_activities` | 묶음 `activities`, subject `table`. 같다. 표준 항목이 7개 절차 키를 고정한다. D11의 희소 외부감사 실시내용 표가 이 묶음과 감사시간·커뮤니케이션이다. |
| 커뮤니케이션 | `communications.value.has_audit_committee`, `communications.value.items[]` (`round`, `date`, `raw`) | 표 전체 `table` | 희소(구서식). 별지 제4호 4절. 2절이나 3절만 있고 4절이 없으면 `not_in_regime` | `exhibit4_communications` | 묶음 `communications`, subject `table`, JSON 객체. 같다. 옛 공시의 상태는 `not_in_regime`으로 남긴다. |
| 계정 | `accounts.value.{계정}.current`, `accounts.value.{계정}.prior`. 각 금액은 `Amount.raw`, `value`, `unit_scale`, `value_won` | 계정 당기·전기. 13×2 = 26 subject. 정답은 `value`와 `unit_scale`이 둘 다 같을 때 | 계정마다 아래 표 | 재무상태표 `bs`(구서식 이름 대차대조표), 손익계산서 `is_`(포괄손익 제목은 제외). 연결은 연결 표, 별도는 개별 표 | v19는 11계정 22칸이다. 매출액·영업이익이 없다. v19 `matching.py`는 `raw` 표시 정수와 단위 문자열을 비교한다. 이 저장소의 정답 조건은 `value`와 `unit_scale`이다. `raw`와 `value_won`은 스냅샷에 남긴다. 당기순손실·영업손실은 음수다. |
| 내부회계 | `icfr.icfr_engagement` (`audit` / `review`), `icfr.icfr_opinion_code`, `icfr.icfr_status` | 단일 값 둘. subject `engagement`, `opinion`. `icfr_status`는 채점 값이 아니다 | 희소(제도). 비상장 개별 F001, 사업연도 2022년까지 F002는 leaf가 없으면 `not_in_regime` | `icfr_opinion`. 내부회계관리제도 감사·검토 의견. 회사 운영보고서는 이 항목이 아니다 | v19 subject `engagement`, `opinion`. 컬럼 `icfr_engagement`, `icfr_opinion_code`. 같다. v19 claim 필터 `icfr_status='ok'`는 이 추출기의 `found`에 해당한다. 감사 코드는 적정·부적정·거절(중요한 취약점은 부적정). 검토 코드는 적정·한정·거절·중요한 취약점. 추출기 `icfr_in_regime`은 F002이면서 사업연도 2023년 이후만 제도 안으로 본다. A001은 leaf가 있으면 `found`, 없으면 `not_in_regime`이다. |
| 계속기업 | `going_concern.value`. 당기 중요한 불확실성이 있으면 `1`, 없으면 `0`. 비적정 의견의 근거로만 있는 경우, 전기 인용만 있는 경우, 청산기준 강조사항만 있는 경우도 `1` | 단일 값 `value` | 상시. 1인 문서가 적어도 필드 희소가 아니다. D11 목록에 없다 | `going_concern`. 강조사항, 기타사항, 계속기업. 창이 비면 문서 전체 | 묶음 `going_concern`, subject `value`, 0/1. 위 세 경우는 `1`이다. 추출기 `extract_going_concern`은 그 경우를 아직 `0`으로 둔다. |
| 종속기업 | `subsidiary.subsidiary_count` 정수, `subsidiary.subsidiary_status` | 단일 값 `value` = 개수. 상태는 채점 값이 아니다. 별도 문서는 `not_applicable`, 개수 `null` | 희소(연결만). 별도는 claim에서 빠진다 | `subsidiaries` 제목 창의 종속기업 표. 창이 비면 문서 안의 그 표. 관계기업·공동기업 행은 세지 않는다 | v19 묶음 이름은 `subsidiary_count`, `subjects.py` 묶음 키는 `subsidiary`, subject `value`. 이 저장소 묶음 키는 `subsidiary`다. |

### 계정 26칸

subject는 `{키}@current`, `{키}@prior`다. 희소 칸도 당기·전기를 각각 판정한다 (D3).

| 계정 | 키 | 표 | 희소 | v19 |
| --- | --- | --- | --- | --- |
| 자산총계 | `total_asset` | 재무상태표 | 상시 | 22칸에 있다 |
| 유동자산 | `current_asset` | 재무상태표 | 상시 | 있다 |
| 재고 | `inventory` | 재무상태표 | 희소(일부 기간) | 있다. §7.5 |
| 매출채권 | `receivable` | 재무상태표 | 상시 | 있다. §7.5 희소 예상에는 없다 |
| 장기매출채권 | `long_term_receivable` | 재무상태표 | 희소 | 있다. §7.5 |
| 계약자산 | `contract_asset` | 재무상태표 | 희소 | 있다. §7.5 |
| 미청구공사 | `unbilled` | 재무상태표 | 희소 | 있다. §7.5 |
| 부채총계 | `total_liability` | 재무상태표 | 상시 | 있다 |
| 유동부채 | `current_liability` | 재무상태표 | 상시 | 있다 |
| 자본총계 | `total_equity` | 재무상태표 | 상시 | 있다 |
| 매출액 | `revenue` | 손익계산서. `영업수익`·`공사수익`도 이 칸 | 상시. 99% 대상 | v19 22칸에 없다 |
| 영업이익 | `operating_income` | 손익계산서. 영업손실은 음수 | 상시. 99% 대상 | v19 22칸에 없다 |
| 당기순손익 | `net_income` | 손익계산서. 당기순손실은 음수 | 상시 | 있다 (`net_income`) |

범위 밖이라 subject가 없는 과목은 표준 항목 문서와 같다. `부채와자본총계`, `부채및자본총계`, `비유동`·`기타`가 붙은 과목, `유동화부채`, 계속·중단·귀속·지배·비지배·총포괄이 붙은 당기순손익, 충당이 붙은 재고, `매출원가`, `영업외`가 붙은 손익.

## 12묶음 밖

| 항목 | 추출기 출력 키 | 판정 단위 | 희소 | 문서 내 근거 | v19 대응 |
| --- | --- | --- | --- | --- | --- |
| 주석 목차 | `notes_toc.value.count`, `notes_toc.value.titles` | 단일 값 `value`. 개수와 제목 목록 전체를 한 번에 판정한다. 99% 대상. 제목마다 subject를 두지 않는다 | 상시. 제목 창이 없는 구서식의 빠짐은 P1a 서식 플래그로 보고, D11 희소 목록에는 넣지 않는다 | `notes_toc`. 제목이 주석인 창. 주석 본문은 넣지 않는다 | v19 12개 묶음에 없다. 묶음 키 `notes_toc`. |

## 채점 subject

구현 때 `subjects.py`는 이 목록만 만든다.

| 묶음 키 | subject |
| --- | --- |
| `company_name`, `document_title`, `fiscal_term`, `auditor`, `opinion`, `gaap`, `audit_report_date`, `current_period`, `going_concern`, `subsidiary`, `notes_toc` | `value` |
| `icfr` | `engagement`, `opinion` |
| `hours`, `activities`, `communications` | `table` |
| `accounts` | 위 13키 × `current` / `prior` |

v19 `REVIEW_SUBJECT_MAP`(`extraction_reviews` subject → 골드 subject)은 쓰지 않는다. 대상 변경에 따라 `extraction_reviews`에는 기록하지 않는다.

## 이식 상태

1단계는 `periods.py`, `scoring.py`, `db.py`, `schema.py`, `matching.py`, `cache.py`와 테스트, `gold_fixtures.py`를 옮겼다. `scoring.py`와 `matching.py`가 `subjects.py`, `snapshots.py`, `sampler.py`를 import하므로 그 세 파일도 원문 그대로 같이 왔다. 묶음 키를 이 표로 다시 쓰는 일, 표본 SQL에서 v19 facts 조건을 빼는 일, 스냅샷을 `Pipeline.run_from_html` 출력으로 바꾸는 일은 2단계다.

## dart-wrapper `feat/gold-review` 이식 제안

`packages/research/research/gold/`에서 `periods.py`, `scoring.py`, `db.py`, `schema.py`, `matching.py`, `cache.py`와 테스트 `test_gold_periods.py`, `test_gold_scoring.py`, `test_gold_db.py`, `test_gold_matching.py`, `test_gold_cache.py`, `test_gold_rescore.py`, `test_gold_oversample.py`, `gold_fixtures.py`는 import 경로만 이 저장소로 바꿔 그대로 가져온다. `db.py`의 카탈로그 `mode=ro` ATTACH와 `busy_timeout`은 유지한다. `sampler.py`는 그 ATTACH와 모집단 조회를 유지하고 카탈로그 경로만 이 저장소 설정으로 옮기되, 조회가 아직 `cat.audit_report_facts`와 `audit_opinion.v19`에 묶여 있으므로 표본 구현 단계에서 버전 조건을 빼고 카탈로그의 문서 위치만 쓰도록 쿼리를 고친다. `snapshots.py`는 facts 행 복사 대신 로컬 캐시 HTML에 `Pipeline.run_from_html`을 돌린 `StandardExtraction` JSON을 추출기 버전과 커밋과 함께 `gold.db`에 넣는다. `labels.py`, `subjects.py`, `evidence.py`와 대응 테스트는 이 표의 묶음 키·subject·섹션 창으로 다시 쓴다. `research/api/admin`, `templates/admin/gold`, `local_app.py`는 가져오지 않고 검토 화면은 이 저장소의 로컬 앱으로 새로 만들며, dart-wrapper `config.py`는 변경하지 않는다.
