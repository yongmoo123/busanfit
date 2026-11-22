# 부산핏 (BusanFit)

사용자의 지역·시간·이동수단·이동제약·예산·선호·동행 조건에 맞춰 실제 부산 공공데이터로 놀거리 코스를 구성하는 소프트웨어공학 팀프로젝트입니다.
LLM은 조건 해석과 설명, DB와 규칙 엔진은 장소 선택·시간 계산·필수 조건 검증을 담당합니다. VLM은 범위 밖입니다.

**현재 #72 작업 브랜치 상태(2026-11-21): 실제 해운대 DB·검색기·도보 계산기·승인 동행 가중치·정보 없는 장소 포함 API를 일반 서버에 연결했습니다.** 서버는 DB 경로를 지정해야 시작하며, 준비가 성공하면 HAEUNDAE/WALK와 포함 capability를 공개합니다. 초기 동의는 false이고 실제 null 장소는 명시적 동의 후에만 CONDITIONAL로 허용합니다. 실제 화면·지도·PC/모바일 및 최종 인수는 후속입니다. 가상 미리보기를 실제 여행 데이터나 인수 결과로 사용하지 않습니다.

[제출용 설치·실행 안내](docs/SUBMISSION_RUN.md)와 [테스트 보고서용 검증 근거](docs/TEST_EVIDENCE_2026-11-21.md)를 정리했습니다. 제출 확정본은 승인된 통합 커밋과 화면 인수 결과로 다시 확인합니다. 별도 #73의 AI 계측·연결 재사용 변경은 이 구현에 포함되지 않았습니다.

## 팀 작업 영역

| 담당 | 영역 | 시작 문서 |
|---|---|---|
| 김세민 | PM·일정·문서·평가 정답·검수·발표 | [docs](docs/README.md), [evaluation](evaluation/README.md) |
| 이찬용 | 데이터 수집·정규화·DB·검색·이동시간·날씨 | [pipelines](pipelines/README.md), [data](backend/app/data/README.md) |
| 김영무 | API·세션·LLM·코스 생성·수정·검증 | [backend](backend/README.md) |
| 배진호 | 채팅·조건 카드·지도·타임라인·모바일 | [frontend](frontend/README.md) |
| 공동 | API 계약·통합·자동 검사 | [contracts](contracts/README.md), [협업 규칙](CONTRIBUTING.md) |

```text
frontend/             배진호 — 화면 구현 영역
backend/app/api/      김영무 — HTTP API·공통 오류
backend/app/sessions/ 김영무 — 세션·TTL·revision
backend/app/application/ 김영무 — Orchestrator·흐름 제어
backend/app/constraints/ 김영무 — 조건 분석·수정 의도
backend/app/explanations/ 김영무 — 추천 이유·출처 연결
backend/app/ai/       김영무 — AIService·Provider
backend/app/courses/  김영무 — 배치·검증·수정
backend/app/retrieval/ 이찬용 — 후보 검색·필터 규칙
backend/app/data/     이찬용 — DB·Repository
backend/app/domain/   공동 — 내부 업무 모델
backend/app/travel/   이찬용 — 이동시간
backend/app/weather/  이찬용 — 날씨
backend/tests/        구현 담당 — 자동 테스트
pipelines/            이찬용 — 수집·정규화·적재
contracts/            공동 — 기존 OpenAPI·가상 예시·검사
evaluation/           김세민 — 평가 입력·정답·실행 결과
docs/sources/         기존 참고자료의 보존 사본
.github/              이슈·PR 양식·CI
deployment/           공동 — 원본 배포 초안의 구현 예정 위치
```

각 영역 README는 구현 책임과 다음 작업을 설명합니다. 영역별 서버를 따로 띄우지 않고 하나의 FastAPI 앱 안에서 통합합니다.

원본 DOCX 대조 결과는 [원본 검토](docs/ORIGINAL_REVIEW.md), 12개 컴포넌트의 위치는 [컴포넌트 연결표](docs/COMPONENT_MAP.md), 전체 요구사항은 [요구사항 등록부](docs/REQUIREMENTS.md)에 있습니다.
기준 설계는 React SPA·FastAPI·SQLite입니다(SDD 2장, DB는 DEC-005로 PostgreSQL+PostGIS에서 변경). 계획서의 Next.js는 대안으로 구분합니다.

## 시작하기

설치·공유 DB/SHA 확인·키 없는 기본 재현·프론트 프록시·문제 확인은 [제출용 실행 안내](docs/SUBMISSION_RUN.md)를 따릅니다. 일반 앱은 `.env`를 자동으로 읽지 않으며, DB 없이 빈 데이터로 시작하지 않습니다.

의존성 설치를 마친 뒤 저장소 루트의 PowerShell에서:

```powershell
$env:BUSANFIT_DB_PATH = (Resolve-Path data/share/haeundae_sample_v1.sqlite3).Path
$env:GEMINI_API_KEY = $null
$env:GEMINI_MODEL = $null
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log
```

API 문서는 http://127.0.0.1:8000/docs 입니다. 단일 worker를 사용하고 재시작 후에는 새 세션을 만듭니다. 새 POST /api/sessions에서 지원 범위를 확인하고 최신 프로필 전체 PUT → READY의 새 revision POST 순서로 연결합니다. 동의 변경·후보 부족·조건부 경고와 프론트 실행은 [실제 연결 안내](docs/ISSUE30_FRONTEND_HANDOFF.md)를 참고하세요.

## 검사

```powershell
.\.venv\Scripts\python.exe contracts/validate_contract.py
.\.venv\Scripts\python.exe contracts/validate_source_sync.py
.\.venv\Scripts\python.exe -m pytest -q
```

계약 검사는 전체 OpenAPI 표준 검증이 아닙니다. 테스트는 공통 오류·세션·revision·요청 제한과 코스/동의 정책 등을 검사합니다. 실제 DB 검사는 BUSANFIT_DB_PATH에 공유 파일을 지정해야 하며 CI에는 DB가 없습니다. 실제 DB 및 별도 Gemini 지연 근거의 실행 범위는 검증 근거 문서를 따릅니다. `python -O`는 기존 assert 검사를 끄므로 사용하지 않습니다.
GitHub Actions는 main/develop push와 PR에서 같은 검사를 실행합니다. 원격 CI의 실제 결과는 Actions에서 확인합니다.

## 다음 작업

진호의 실제 화면 연결·지도·PC/모바일·수동 인수와 #72·#73 리뷰 대응이 남아 있습니다. 코드/API 검증 완료와 최종 사용자 인수는 구분합니다. #32 부분 수정은 11/22 범위 판단 후 계약부터 진행하고 날씨·고정 일정은 11/25 판단 전 착수하지 않습니다.

[연결 기록](docs/ISSUE23_COURSES_IMPLEMENTATION.md), [포함 기능 기록](docs/ISSUE30_UNKNOWN_ACCESSIBILITY_IMPLEMENTATION.md), [기준 결정](docs/DECISIONS.md)을 참고하세요. 아래 날짜가 붙은 과거 기록의 비활성·미연결 표기는 당시 상태입니다.

## 2026-11-11 조건 처리 보완 (기존 PR #13·#17)

아래는 당시 기록이다. 최신 로컬 통합 상태·검증은 [이슈 #20 기록](docs/ISSUE20_CHAT_IMPLEMENTATION.md)을 따른다.

#17 모듈이 함께 반영되면 `/api/chat`과 DEC-020 카드 정규화를 사용한다. #13 단독에서는 기존 세션·카드 API만 등록된다. 실제 Provider는 미설정이며 재시도 후 규칙 파서로 대체한다. 현재 capabilities는 비어 있어 활성 조건은 거절된다. 검토 순서·검증·실행 제한·capabilities 활성화 계획은 [구현 기록](docs/ISSUE6_8_IMPLEMENTATION.md)을 따른다. PR/브랜치 병합 없이 소스 검토 사본에서 188개 통합 테스트를 통과했다.

세션 종료는 기존 PR #12를 로컬 통합해 DELETE /api/sessions/{sessionId}의 멱등204·no-store를 제공한다. SQLite Repository는 PR #41의 구현을 재사용해 가상행으로만 검증하며 실제 검색/이동시간·일반 capabilities는 연결 전 닫혀 있다.

[2026-11-17 서버 완료 기준 점검](docs/SERVER_COMPLETION_AUDIT_2026-11-17.md): 새 PR 없이 기존 #48·#49·#50·#54·#55·#56에 서버 보완을 반영했다. 실제 LLM 평가는 사용자 보류, 실제 해운대 검색/이동시간·프론트·PM 확인은 후속이며 일반 가중치는 비활성이다. `python evaluation/server/run.py --output evaluation/server/results/offline-2026-11-17.json`으로 근거를 수집한다.

## 2026-11-11 프론트 종료 연동 검토

새 채팅·pagehide/keepalive·BFCache 처리와 이전 세션의 늦은 응답 무시는 프론트 연동 시 확인합니다. 204는 빈 응답이며 JSON 파싱하지 않습니다. 세션 경로가 남을 수 있는 Uvicorn·프록시·호스팅 로그 검수는 [세션 로그 보호](deployment/SESSION_LOG_PRIVACY.md)를 따릅니다. 실제 프록시·브라우저 검증은 아직 수행하지 않았습니다.
