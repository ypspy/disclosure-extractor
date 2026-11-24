# HANDOVER — ypspy/disclosure-extractor

- 작성: 2026-11-24 CET(UTC+1), 조율 담당(Mr. Vegetable) executor. 기준 브랜치 `handover` @ `cf9afbfa` (base `feat/standard-extractors` `d4e7bae9`).
- 이 파일은 `handover` 브랜치 PR로 올린 초안이다. 머지는 윤석님 검토·승인 후.
- 표기: [확인됨] 이번 작성에서 직접 확인 / [추정] 기록·봇 보고에 있으나 이번에 재확인 안 함 / [확인 불가] 근거를 찾지 못함 / [접근 불가] 접근 경로 없음(LAPTOP-YS 오프라인 11/21–11/30 등).
- 비밀값(토큰·키·비밀번호·환경변수 값)은 적지 않았다. 이름만 적었다.
- 자매 문서: `ypspy/quality-updates` `HANDOVER.md`, `ypspy/dart-wrapper` `HANDOVER.md` (2·4·9절은 세 문서 공통).

## 1. 프로젝트 목적과 현재 상태

disclosure-extractor(패키지 이름 `dart-hybrid-parser`, 모듈 `dart_parser`)는 비정형 DART 공시 HTML에서 `API Fetch → HTML·표 정규화 → 앵커 규칙 엔진 → 검증 → SLM fallback` 순서로 구조화 데이터를 뽑는 파서이며, 첫 과제는 감사보고서 `standard` 항목(12묶음)이다 [확인됨: `README.md`, `AGENTS.md`]. 2026-11-01 결정으로 골드 검증·개량 대상 추출기가 dart-wrapper v19에서 이 저장소로 바뀌었고, 골드 검수 도구(Gold Desk, `src/dart_parser/gold/`)가 들어 있다 [확인됨: `HANDOFF.md` 머리말]. 작업 기본 브랜치 `feat/standard-extractors`는 `d4e7bae9`(#13, issue #8 해결)이고 열린 PR·이슈는 0건이다 [확인됨]. 골드 표본 446건이 LAPTOP-YS `gold.db`에 준비되어 있으나 캡처(labels)는 0건이며, W1 캡처는 윤석님 12월 복귀 후로 미뤄졌다 [추정: `/workspace/proposals/gold-ingest/w1-desk-restart-20261121-CT.md`, `Zucchini.md` §3].

## 2. 자료 위치 지도

표기: [확인됨] 이번 작성에서 파일·명령·API로 직접 확인 / [추정] 기록에 있으나 이번에 재확인하지 않음 / [확인 불가] 찾아봤으나 근거 없음 / [접근 불가] 접근 경로가 없음(랩탑 오프라인 등).

### 2.1 GitHub 저장소 (소유자 `ypspy`)

| 저장소 | 공개 여부 | 기본 브랜치 | 용도 | 근거 |
|---|---|---|---|---|
| `ypspy/quality-updates` | PUBLIC | `main` | MkDocs 공개 사이트 Quality Updates(Product A). 분기 규제 업데이트·제재 의결·품질관리감리·질의회신 수집 스크립트 | [확인됨] `gh repo view ypspy/quality-updates --json visibility,defaultBranchRef` |
| `ypspy/dart-wrapper` | PUBLIC | `master` | DART 공시 카탈로그 수집(1층)·Viewer API·감사 추출 연구 패키지 모노레포 | [확인됨] 같은 명령 |
| `ypspy/disclosure-extractor` | PUBLIC | `feat/standard-extractors` | DART 공시 하이브리드 파서(`dart_parser`)와 골드 검수 도구(Gold Desk) | [확인됨] 같은 명령 |
| `ypspy/obsidian-vault` | PRIVATE | `main` | LLM 위키(Second-Brain). `wiki/` 435개 파일, `raw/` 원문. 쓰기는 Mr. Kale만 | [확인됨] `gh repo list ypspy`, 박스 사본 `/workspace/vault` (HEAD `e54d2aa9`, PR #20 머지) / 역할은 `wiki/bot-operations.md` |
| `ypspy/review-kit` | PRIVATE | `main` | 독립 리뷰어(클라우드 에이전트) 규칙·스킬. 9절 참고 | [확인됨] `git ls-remote` main = `e124cd3893c4fb7cd56b20252ef37f9c4dbb509b` |
| `ypspy/my-obsidian-vault` | PRIVATE | — | 리타이어한 이전 볼트. 삭제·아카이브는 윤석님 확인 필요 | [확인됨] 목록 / [추정] 상태는 `wiki/bot-operations.md` 2026-11-05 기록 |

세 대상 저장소의 `handover` 브랜치: quality-updates `c8826001`(base `main` 150cdca5), dart-wrapper `ab74bad6`(base `master` ef02eb7e), disclosure-extractor `cf9afbfa`(base `feat/standard-extractors` d4e7bae9). 각각 `.gitignore` 보강과 `.env.example`(이름만) 커밋 1개. [확인됨] `git log` (이 파일이 놓인 clone)

### 2.2 로컬 폴더 — LAPTOP-YS (Windows, 윤석님 노트북)

**[접근 불가]** 2026-11-21~11-30 여행으로 오프라인. 아래 경로는 봇 보고서·박스 기록에 적힌 마지막 확인값이며 이번에 직접 보지 않았다.

| 경로 | 용도 | 근거 |
|---|---|---|
| `C:\dev\dart-wrapper` | DW 작업 트리. `feat/gold-review` @ `2f0bf964`로 고정(checkout·pull 금지) | [추정] `/workspace/handover/bot-reports/Seaweed.md` §1, `/workspace/laptop-sync/origin-sync-result-20261122-0922.txt` |
| `C:\dev\dart-wrapper\packages\web-api\dart_catalog.db` | 1층 카탈로그(SQLite, 10,096,406,528 B, 2026-11-20 조회) | [추정] `/workspace/proposals/cloud-migration/plan.md` §1 |
| `C:\dev\dart-wrapper\packages\web-api\dart_sections.db` | F004 본문(6,328,320 B) | [추정] 같은 문서 |
| `C:\dev\dart-wrapper\data\gold\gold.db` | DW 골드 DB(읽기 전용, 새 라벨 금지) | [추정] `/workspace/handover/bot-reports/Zucchini.md` §6.1 |
| `C:\dev\dart-wrapper\packages\web-api\f004_research.db` | F004 연구 DB(백업 대상 아님) | [추정] `Seaweed.md` §2.7 |
| `C:\dev\disclosure-extractor` / `data\gold.db` | DE 트리(`feat/standard-extractors` @ `d4e7bae9`)와 골드 DB(samples 446, labels 0) | [추정] `/workspace/proposals/gold-ingest/w1-desk-restart-20261121-CT.md` |
| `C:\dev\dart-nightly\run.ps1`, `C:\dev\dart-f004\run.ps1` | 야간 수집·F004 주간 래퍼(작업 스케줄러 `DartNightlyCatalog`, `DartF004Weekly`) | [추정] `Seaweed.md` §1 |
| `C:\backups\dart\run-backup.ps1`, `backup.py`, `dart-db-slot{N}.zip` | 주간 DB 백업(`DartDbBackup`) | [추정] `Seaweed.md` §2.7, 박스 사본 `/workspace/dart-backup/` |
| `C:\Users\yoont\arf-resume-20261115\` | ARF 추출 도구·Gold Desk 로그 | [추정] `Zucchini.md` §6.1 |
| `C:\dev\quality-updates`, 제재 폴더 `qu-sanctions`(969폴더) | QU 랩탑 트리·제재 원자료 | [추정] `Cabbage.md` §1, `Mint.md` §1 |
| `accounting-lit-mcp`, `ax-learning` | 랩탑에만 있는 프로젝트(이관 대상 아님) | [접근 불가] |

### 2.3 봇 박스 (Grok Bot 공용 Linux 박스, `/workspace`)

| 경로 | 용도 | 근거 |
|---|---|---|
| `/workspace/handover-repos/<repo>` | 이 HANDOVER.md가 놓인 `handover` 브랜치 clone | [확인됨] |
| `/workspace/quality-updates`, `/workspace/repos/dart-wrapper`, `/workspace/disclosure-extractor-pr11`, `/workspace/qu-*`, `/workspace/wt*` 등 | 봇 작업용 clone·worktree(여러 개, 일부 detached) | [확인됨] `find / -name .git` |
| `/workspace/decision-inbox/queue.md` | 결정 대기열(추가만, 봇 보고 한 줄씩). 544줄 | [확인됨] |
| `/workspace/proposals/` | 계획서·실행안(`economy/team-rules-v1.md`, `cloud-migration/`, `gold-ingest/`, `qu-bf2000/`, `team-ops-5-actions-20261122.md`) | [확인됨] |
| `/workspace/plans/` | 수집·백필 계획(2026-11-11~11-20) | [확인됨] |
| `/workspace/prompts/` | 봇·클라우드 에이전트 지시서 85개 | [확인됨] `ls \| wc -l` |
| `/workspace/reviews/`, `/workspace/reviews/state/<repo>-<pr>.json` | 독립 검토 보고서와 라운드 상태 | [확인됨] |
| `/workspace/handoff/` | Mint 분류표(`qu-bf-2000`~`qu-bf-2013`), Kale 반입 묶음(zip) | [확인됨] |
| `/workspace/qu-collect/downloads/`, `/workspace/qu-collect-logs/` | QU 백필 원문 입수본·수집 로그 | [추정] `Mint.md` §5 |
| `/workspace/quality-updates/data-handoff/` | `F004`, `fss-replies`, `kasb-replies`, `sanctions` 전달 묶음(untracked) | [확인됨] |
| `/workspace/f004/`, `/workspace/fss-review/` | F004 추출 검토·FSS 감리 주간 기준선(`baseline_2026-11-23.json`) | [확인됨] |
| `/workspace/arf-resume/`, `/workspace/proposals/gold-ingest/` | ARF C2·W1 Gold Desk 점검 기록 사본 | [확인됨] |
| `/workspace/vault` | `ypspy/obsidian-vault` 공유 clone | [확인됨] |
| `/workspace/full_scan/`, `/workspace/drive_*.csv`, `/workspace/step3_rename_candidates/` | Rice의 Drive 전수 목록·정리 기록 | [확인됨] 파일 존재 |
| `/workspace/reports/team-diagnosis-20261122.md` | 팀 운영 진단(봇 구성·루틴·GitHub 수치) | [확인됨] |
| `/workspace/handover/bot-reports/<봇>.md` | 이번 이관용 봇 보고서 | [확인됨] |
| `/workspace/exports/` | 대화 기록 내보내기. **저장소에 넣지 않음, 내용 인용 안 함** | [확인됨] 존재만 |

### 2.4 클라우드

| 위치 | 용도 | 근거 |
|---|---|---|
| https://quality-updates.onrender.com | QU 공개 사이트(Render). `main` 푸시 시 자동 빌드·배포 | [확인됨] HTTP 200(2026-11-24 CET), `README.md` 배포 절 / Render 대시보드·서비스 설정은 [접근 불가] |
| Google Drive `Second-Brain` 폴더 (`1nW461q4t4aSTHOqaqT1myAznMdxnFAvp`) | `Bot-Operations`, `Home`, `README (지식체계 인덱스)`, `지식체계 요약본` 4개 Docs. 요약본은 2026-11-05부터 갱신 안 함 | [확인됨] Drive 목록 / [추정] 갱신 중단은 `wiki/bot-operations.md` |
| Google Drive `80_개발_AI/DART_DB_백업` | DART DB 주간 백업 zip(슬롯 2개) | [확인됨] 폴더 존재 / 슬롯 파일 현황은 [확인 불가] |
| Google Drive `80_개발_AI/quality-updates`, `accounting-lit-mcp`, `ax-learning`, `cost-analysis` | 코드 사본 폴더(2026-10-29) | [확인됨] 폴더 존재 / 내용·용도 [확인 불가] |
| Cursor 캔버스 「결정 대기함」, 「정보원 정기 입수 개선안 (2026-11-12)」 | 결정 카드·정보원 로드맵(P0~P3) | [추정] `/workspace/reports/team-diagnosis-20261122.md` §1 (URL 기재) |
| GoatCounter `yoonseokseong.goatcounter.com` | QU 접속 통계 | [추정] `Cabbage.md` §2 |
| GitHub Actions | QU `CI`(lint/build/validate/test), DW `ci`(web-api·research pytest). DE는 워크플로 없음 | [확인됨] `.github/workflows/` |

## 3. 구조

### 3.1 주요 폴더·파일 [확인됨: `ls`]

| 경로 | 내용 |
|---|---|
| `src/dart_parser/fetcher/` | Open DART 목록·원문·XBRL (네트워크는 여기와 `fallback/`만) |
| `src/dart_parser/normalizer/` | HTML 정리, `numeric.py`(`to_number()`), `table_grid.py`(colspan/rowspan 평탄화) |
| `src/dart_parser/parser/` | 앵커 매칭, 단위, 규칙 엔진 |
| `src/dart_parser/validator/` | 합계·회계등식 검증 |
| `src/dart_parser/fallback/` | Pydantic 스키마(`schemas.py`), Instructor SLM 클라이언트 |
| `src/dart_parser/config/settings.py` | `pydantic-settings`, 접두사 `DART_`, `.env` 읽음 |
| `src/dart_parser/gold/` | Gold Desk: `app.py`(WSGI, argparse `--catalog`, `--gold`, `--cache`, `--port` 기본 8765), `sampler.py`, `scoring.py`, `capture*.py`, `recapture.py`, `db.py`, `schema.py`, `static/capture.js` |
| `src/dart_parser/pipeline.py` | 오케스트레이션 |
| `tests/`(46개 `test_*.py`, `sample_htmls/` 3개, `gold_fixtures.py`) | 단위 테스트 |
| `docs/standard-extraction-items.md`, `gold-field-mapping.md`, `gold-pilot-checks.md`, `superpowers/`(specs 3, plans 4) | 항목 정의·골드 설계 |
| `AGENTS.md`, `HANDOFF.md`, `.cursor/rules/dart-parser.mdc` | 기존 에이전트 규칙. 수정하지 않음 |

### 3.2 브랜치 전략
- GitHub 기본 브랜치가 `feat/standard-extractors`(별도 `main` 없음) [확인됨: `gh repo view`]. 보호 규칙 없음(`main` 브랜치 없음) [확인됨].
- 원격 브랜치 13개: `feat/` 10(`gold-*` 다수), `fix/` 2, `handover` [확인됨]. PR은 `feat/standard-extractors`로 merge 커밋(#9~#12) 또는 squash(#13) [확인됨: `git log`].
- 2026-11-01 지시: 새 브랜치 → PR, 머지는 윤석님 결정 [확인됨: `HANDOFF.md` 머리말].

### 3.3 실행·테스트 명령 [확인됨: `README.md`, `AGENTS.md`, `pyproject.toml`]

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # 값은 로컬에서만 채움
python -m pytest                # pyproject addopts -q, testpaths tests
ruff check .
```
- Gold Desk 기동(마지막 성공 기록, 랩탑 PowerShell, `PYTHONPATH=src`, `DART_LLM_ENABLED` 끔): `C:\dev\disclosure-extractor\.venv\Scripts\python.exe -m dart_parser.gold.app --catalog C:\dev\dart-wrapper\packages\web-api\dart_catalog.db --gold C:\dev\disclosure-extractor\data\gold.db --port 8765` → `http://127.0.0.1:8765/` [추정: `Zucchini.md` §6.2]. `app.py`에 `main()`·argparse가 있고 기본 포트 8765, `main()`이 `DART_LLM_ENABLED` 기본값을 `false`로 둔다 [확인됨: 소스].
- 이번 박스 실측(Python 3.13.5, `/tmp` venv): pytest **301 passed**(rc 0), `ruff check .` "All checks passed!" [확인됨].
- 배포: 없음(로컬 도구). CI 워크플로 없음 [확인됨: `.github/` 부재].

## 4. 봇별 역할 분담

조직 근거: `ypspy/obsidian-vault` `wiki/bot-operations.md`(2026-11-11 확정 조직, 마지막 갱신 2026-11-16), `/workspace/reports/team-diagnosis-20261122.md` §2. 2026-11-16에 Mr. Strawberry(홍보·세일즈)는 조직에서 빠졌다. [확인됨: 두 파일]
봇 보고서: `/workspace/handover/bot-reports/<봇>.md` — 6개 모두 수신(Cabbage, Mint, Seaweed, Zucchini, Rice, Kale; 2026-11-24 02:36~02:42 CET). 보고서 안의 [확인됨]은 그 봇이 작성 시점에 확인했다는 뜻이며, 이 문서에서 다시 확인한 것은 따로 적었다.

| 봇 | 역할 | 담당 파일·모듈 | 지금까지 한 일 (근거) | 보고 |
|---|---|---|---|---|
| Mr. Vegetable · 조율 담당 | 조율만. 결정 대기함, 브리핑, 봇 지시, 독립 검토 띄우기, 머지 실행(윤석님 결정 후) | `/workspace/decision-inbox/queue.md`, `/workspace/proposals/`, `/workspace/prompts/`, `/workspace/reviews/state/` | 세 저장소 `handover` 브랜치 생성·커밋(`c8826001`, `ab74bad6`, `cf9afbfa`) [확인됨: git log]. 머지 실행 예: dart-wrapper #20 `ef02eb7e`, quality-updates #153 `85b66aa4` [추정: queue.md 2026-11-20 줄] | 요청자(해당 없음) |
| Mr. Cabbage · Quality Update 담당 | `quality-updates` 구현·수집·draft PR. 비DART 원천(FSC·FSS·KASB 등) 수집·가공 | `scripts/crawl.py`, `scripts/crawler/`, `scripts/attach_sanction_minutes.py`, `scripts/lint_public_body.py`, `docs/quality-updates/`, `data/` | 최근 머지 #173~#186 [확인됨: `gh pr list --state merged`]. 2013→2000 연도 백필 중 #177(2013)·#183(2012) 머지, #184(2011)·#185(2010) draft. 루틴 `qu`, `qu-2`, `fss-b0000291` [추정: 보고서] | 수신 `Cabbage.md` |
| Mr. Mint · 품질관리감리 담당 | 품질관리감리·제재 의결 분류와 원문 대조. **코드 구현 안 함** | `/workspace/handoff/qu-bf-<연도>/`, `/workspace/fss-review/`, `/workspace/f004/review-pr*` | 2013→2000 분류 r2 완료, F004 관련 #145~#150 머지, 주간 감리 점검(2026-11-23 신규 0) [추정: `Mint.md` §2~3] | 수신 `Mint.md` |
| Mr. Seaweed · 데이터 추출 담당 | DART 1층 원천 수집(`dart_catalog.db` `disclosures`/`entries`/`corps`/`slice_progress`, `dart_sections.db`), DB 파일·백업 실행 | DW `packages/web-api`(수집), 랩탑 `run.ps1`·`backup.py` | D3-2015(F002 2015 365/365 complete), 공시 누계 483,710(11/20)→488,539(11/21), 여행 전 수동 백업 [추정: `Seaweed.md` §3] | 수신 `Seaweed.md` |
| Mr. Zucchini · DART 파서 담당 | DART 2층 파싱·추출(`audit_report_facts`, `extraction_*`), DE `gold.db` 품질 검증(Gold Desk), DW·DE PR 오너 수용 검토. 1층은 읽기만 | DW `packages/research/`, DE `src/dart_parser/gold/` | DW #14~#20, DE #13 지시·수용 검토, W1 Gold Desk 기동(446 샘플), ARF C2 14,288/17,455 처리 후 보류 [추정: `Zucchini.md` §1~3] | 수신 `Zucchini.md` |
| Mr. Kale · Second-Brain 담당 | `ypspy/obsidian-vault`에만 쓰기. raw 반입·위키 합성 | 볼트 `raw/`, `wiki/`, `.cursorrules` | 볼트 PR #16~#20 머지: #18 회계기준위 566회(`b247e2bf`), #19 금융위·증선위 969회차(`67752242`), #20 허브 날짜(`e54d2aa9`) [확인됨: `gh pr list -R ypspy/obsidian-vault --state merged`]. 루틴 D12(`/workspace/synth-runner/run_weekly.py`, 잔액 하한 가드로 11/23 skip) [추정: `Kale.md` §6] | 수신 `Kale.md` |
| Mr. Rice · 드라이브 문서 담당 | Google Drive 개인 문서 정리(Second-Brain 제외). DART DB는 다루지 않고 백업 위치만 | `/workspace/full_scan/`, `/workspace/drive_cleanup_*`, `/workspace/step3_rename_candidates/` | Drive 전수 목록 r79–r84 누계 63,340항목·쓰기 0 [확인됨: `/workspace/full_scan/report_r79-r84.md`], Step 3 이름 변경 1,823행, 중복 정리 Step 1 이동 7,119·잔여 1,768, `DART_DB_백업` 폴더 생성 [추정: `Rice.md` §2~3]. 루틴: 전수 조사(`automation-1794885772459`), 중복 정리 야간(`automation-1793420638471`), Inbox 분류(`drive-inbox`) | 수신 `Rice.md` |

PR·커밋 봇 식별 규칙(앞방향만): 라벨 `bot:<봇이름>`(클라우드 에이전트면 `bot:cloud-agent` 추가), 커밋 끝 `Bot: <봇이름>` + `Made-with: cursor-agent`. [추정] `/workspace/proposals/team-ops-5-actions-20261122.md` §1 (실행안, 라벨 저장소 생성은 별도 승인), `Cabbage.md` §5. 2026-10-25~11-22 PR 216건 중 213건 작성자가 `ypspy`라 과거 PR은 봇을 구분할 수 없다. [추정: 같은 문서 배경]

## 5. 결정 기록

별도 DECISIONS.md에서 관리 예정

## 6. 진행 중 작업

### 6.1 열린 PR·이슈
- 열린 PR 0건, 열린 이슈 0건 [확인됨, 2026-11-24 CET]. issue #8(`_hours_keys` 키 불일치)은 #13(`d4e7bae9`, "Closes #8")로 닫힘 [확인됨: PR 제목].
- 최근 머지: #13 `d4e7bae9`, #12 `bf0a2445`(카탈로그 연결 짧게), #11 `3d070581`(Desk 매핑), #10 `ef6fa5db`, #9 `0ae12e5b`, #7 `353510b3`(재캡처 일관성), #6 `5ab7fd61`, #5 `b563d0fb` [확인됨].

### 6.2 미완료 작업
- W1 골드 캡처: 표본 446(blind 40, prefill 406), labels·captures 0. 캡처는 윤석님이 브라우저로 직접 [추정: `w1-desk-restart-20261121-CT.md`, `Zucchini.md` §3-1].
- 골드 입수 재개 범위: 권고 R1(미라벨·재캡처 대상만, blind 10% 유지), 확정은 윤석님 [추정: `/workspace/proposals/gold-ingest/resume-scope-schedule.md`].
- PORT-15/16(DW #15·#16 수정의 이식)은 나중에 따로 결정 [추정: 같은 문서].
- 미결: 희소 필드 확정, sampler 조건, A001 leaf 없을 때 `not_in_regime`, 한정 의견 미출력, 파일럿 점검 3항목(`docs/gold-pilot-checks.md`) [추정: `wiki/project-disclosure-extractor.md` 미결].

### 6.3 막힌 지점
- LAPTOP-YS 오프라인으로 Gold Desk 생존·`gold.db` 현재값 확인 불가 [접근 불가].
- W1 시작·완료는 12월 복귀 이후 [추정: `Zucchini.md` §3-2].

## 7. 알려진 문제와 기술 부채
1. CI 없음 — 테스트·ruff를 수동으로만 돌림 [확인됨].
2. 기본 브랜치가 기능 브랜치 이름(`feat/standard-extractors`)이고 `main` 없음 [확인됨].
3. DE `gold.db`가 주간 백업(`DartDbBackup`) 대상에 없음 [추정: `Seaweed.md` §2.7].
4. Desk가 패키지 미설치 상태로 `PYTHONPATH=src`에 의존 [추정: `Zucchini.md` §6.2].
5. `HANDOFF.md` 하단의 2026-10-31 설계는 dart-wrapper 경로 기준이라 머리말(2026-11-01)과 섞여 있음 [확인됨].
6. `tests/sample_htmls/` 실제 DART 스냅샷 3개뿐 [확인됨].
7. 저장소 PUBLIC [확인됨].

## 8. 환경변수(이름만)·외부 서비스·의존성
- `.env.example`(10개, `handover` 커밋) [확인됨]: `DART_API_KEY`, `DART_API_BASE_URL`, `DART_HTTP_TIMEOUT`, `DART_LLM_BASE_URL`, `DART_LLM_API_KEY`, `DART_LLM_MODEL`, `DART_LLM_TIMEOUT`, `DART_LLM_ENABLED`, `DART_LLM_MAX_RETRIES`, `DART_CACHE_DIR`.
- 외부 서비스: Open DART API(문서 수집 시), OpenAI 호환 엔드포인트(Ollama/vLLM, 선택·fallback) [확인됨: README]. 골드 작업 중에는 네트워크·SLM·유료 API 금지(`DART_LLM_ENABLED` 끔) [확인됨: `HANDOFF.md`]. 표본 모집단은 dart-wrapper `dart_catalog.db`를 `mode=ro`로만 읽음 [확인됨: `HANDOFF.md`].
- 의존성(`pyproject.toml`): `lxml>=5.0`, `beautifulsoup4>=4.12`, `html5lib>=1.1`, `pandas>=2.0`, `pydantic>=2.0`, `pydantic-settings>=2.0`, `rapidfuzz>=3.0`, `instructor>=1.0`, `openai>=1.0`, `httpx>=0.27`; dev `pytest>=8.0`, `pytest-cov>=5.0`, `ruff>=0.5`; Python ≥3.11, ruff line-length 100, 규칙 `E,F,I,UP,B` [확인됨].

## 9. 리뷰 규칙

### 9.1 머지 기준
- 머지·삭제·데이터 이동·외부 발송·public/private 전환은 **윤석님 본인의 말**로만 승인한다. 읽기 전용 점검, 계획·프롬프트, 머지하지 않는 draft PR은 사전 허용. [추정] `wiki/bot-operations.md`(2026-11-11 결정 인용), `Seaweed.md` §5, `Zucchini.md` §7
- 흐름: 담당 봇이 draft PR → 담당 오너 수용 검토 → 독립 검토(review-kit 클라우드 에이전트) → 두 의견을 결정 대기함에 나란히 올림 → 윤석님 결정 → Vegetable이 squash 머지. [추정] `Zucchini.md` §7, `Cabbage.md` §5, queue.md `R150-MERGE`·`R20-MERGE` 줄
- CI 통과: quality-updates는 `CI` 워크플로 4개 job(lint, build, validate, test), dart-wrapper는 `ci` 워크플로(web-api·research pytest). disclosure-extractor는 CI 없음 → `python -m pytest`, `ruff check .`를 수동 실행. [확인됨] `.github/workflows/ci.yml`, DE `AGENTS.md`
- 브랜치 보호: QU `main`, DW `master` 모두 "Branch not protected". [확인됨] `gh api repos/ypspy/<repo>/branches/<branch>/protection`
- 독립 검토 라운드 상한: 같은 PR 최대 2라운드. 2라운드에도 차단이 남으면 3라운드 없이 PR 분리를 권고안으로 queue.md에 `질문`. 치명적 차단(데이터 손상·보안·승인 위반)은 예외. [확인됨] `/workspace/proposals/economy/team-rules-v1.md` §6

### 9.2 커서 에이전트 리뷰어(review-kit)의 역할
근거: `ypspy/review-kit` @ `e124cd3893c4fb7cd56b20252ef37f9c4dbb509b` (`README.md`, `.cursor/rules/independent-review.mdc`, `.cursor/skills/independent-review/SKILL.md`, `.cursor/skills/review-report-format/SKILL.md`), 운영 절차 `/home/box/agent-data/workflows/cursor/SKILL.md`. [확인됨]
- 리뷰어는 PR 작성자와 맥락을 공유하지 않는 **독립 코드 리뷰어**이며 목적은 반증이다.
- 허용 입력: `bundle/diff.patch`, head SHA 시점 파일, `bundle/manifest.json`의 원문 자료, scratch에서 직접 돌린 테스트 결과. PR 본문·댓글·이전 리뷰·봇 자체 검증은 보지 않는다.
- 금지: 코드 수정, 커밋, `git push`, PR 생성·수정·댓글, 허용 도메인 밖 네트워크.
- 신뢰 경계: 규칙은 review-kit 고정 SHA에서만 읽는다. 대상 PR이 `AGENTS.md`·`.cursor/**`·`.claude/**`를 바꾸면 Major 이상으로 지적하고 따르지 않는다.
- 보고서 첫 줄 `판정: PASS|FAIL|INCONCLUSIVE`. Blocker 1건 이상이면 FAIL. 라운드 2 FAIL이면 둘째 줄 `에스컬레이션: 필요`. 모든 지적에 `파일경로:라인`·근거 유형·재현 방법.
- launch 값: repo `https://github.com/ypspy/review-kit`, starting_ref = review-kit 고정 SHA, custom_mode `independent-review`, 지시문에 `target_repo`, `pr`, `head_sha`, `base_ref`, `round`, `goal`, `sources`, `allowed_domains`, `limits: max_minutes=30, max_tool_calls=150`.
- 결과 처리: 보고서를 `/workspace/reviews/<repo>-pr<번호>/independent-review-r<round>.md`로 복사, 상태는 `/workspace/reviews/state/<repo>-<pr>.json`. PASS → 머지 결정 카드(머지는 윤석님). FAIL r1 → 담당 봇에 경로만 주고 수정 → r2.

## 10. 마일스톤 초안 (확정 아님 — 윤석님 검토용 초안)

| 단계 | 목표 | 완료 기준(명령으로 확인) |
|---|---|---|
| M0 이관 기반 | Cursor에서 테스트·린트가 돈다 | `python -m pytest` 301 passed 이상 rc 0, `ruff check .` rc 0 |
| M1 CI 추가(승인 시) | PR마다 자동 검증 | `.github/workflows/`에 pytest·ruff job, `gh pr checks <번호>` 성공 |
| M2 W1 캡처 | 446 표본 캡처 완료 | `sqlite3 "file:gold.db?mode=ro"`로 labels/captures 건수 = 대상 수, blind 재캡처 일관성 검사 결과 기록(`tests/test_gold_recapture.py` 기준 로직) |
| M3 채점 | 필드별 정밀도 산출 | Wilson 95% 하한 계산 결과 파일 생성(`dart_parser.gold.scoring`), 기준 D1(하한 ≥ 99%, `HANDOFF.md`) 대비 표 |
| M4 다음 기간 표본 | 재개 범위(R1) 확정 후 확대 | 확정 문서 경로와 표본 수가 `gold.db` 실측과 일치 |

## 11. 봇들이 루틴 업무 외에 맡을 수 있었던 후보 작업 (제안)
- Zucchini: DE용 GitHub Actions(pytest·ruff) draft PR — 근거 7절 1.
- Zucchini: `HANDOFF.md` 정리(현재 유효 규칙과 과거 설계 분리) 문서 PR — 근거 7절 5.
- Zucchini: 파일럿 점검 3항목(`docs/gold-pilot-checks.md`)과 한정 의견 추출 설계 — 근거 6.2.
- Seaweed: DE `gold.db` 백업 포함안 — 근거 7절 3.

## 12. 다음에 바로 할 일 5개
1. 윤석님이 `HANDOVER.md` 초안을 검토하고 `handover` 브랜치에 커밋.
2. Cursor에서 `python -m pytest`, `ruff check .` 실행(M0).
3. 기본 브랜치를 `feat/standard-extractors`로 유지할지 결정.
4. 랩탑 복귀 후 `gold.db` 읽기 전용 점검(건수·sha) 후 W1 캡처 일정 확정.
5. CI 추가(M1) 승인 여부 결정.

## 이 문서만으로 이어받기 어려운 부분
- `C:\dev\disclosure-extractor\data\gold.db`와 골드 캐시 `C:\dev\dart-wrapper\data\gold_cache`, Desk 로그 — [접근 불가].
- 표본 추출 시드·층화 결과는 `gold.db` 안에만 있음 — [접근 불가].
- 골드 설계 결정 D1~D11과 2026-11-01 변경의 원문 맥락은 `HANDOFF.md`와 봇 기록에만 있다.

## 내게 확인이 필요한 질문
1. 기본 브랜치를 `main`으로 새로 만들지, `feat/standard-extractors`를 계속 쓸지?
2. W1 캡처를 Cursor 이관 뒤에도 같은 Gold Desk로 할지?
3. 골드 입수 재개 범위 R1을 확정할지?
4. DE에 CI를 추가할지?
5. 표본 원문 캐시를 랩탑 밖(박스·클라우드)에 복제해 둘지?
