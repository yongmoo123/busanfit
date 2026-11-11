# 부산핏 (BusanFit)

사용자의 지역·시간·이동수단·이동제약·예산·선호·동행 조건에 맞춰 실제 부산 공공데이터로 놀거리 코스를 구성하는 소프트웨어공학 팀프로젝트입니다.
LLM은 조건 해석과 설명, DB와 규칙 엔진은 장소 선택·시간 계산·필수 조건 검증을 담당합니다. VLM은 범위 밖입니다.

**현재 상태: 세션 생성·조건 카드 전체 교체 API와 메모리 저장소 구현.** 추천 엔진 미연결로 활성 조건은 거절하며 미입력 프로필 저장만 가능합니다. 나머지 업무 API·LLM·DB·지도는 아직 미구현입니다. 기존 계약과 개발 일정은 합의용 초안이며, 가상 예시를 실제 부산 데이터로 사용하지 않습니다.

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
기준 설계는 React SPA·FastAPI·PostgreSQL+PostGIS입니다(SRS 2.3, SDD 2장). 계획서의 Next.js·SQLite는 대안으로 구분합니다.

## 시작하기

원본 SRS 목표는 Python 3.11/Linux/Docker이며 현재 로컬 검증 환경은 Python 3.12.14입니다. CI는 두 버전을 검사하도록 정의했습니다. 정의와 실제 통과 여부는 구분합니다.

저장소 루트에서 실행합니다. 아래는 Windows PowerShell 기준이며 가상환경 활성화는 필요하지 않습니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-lock.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --no-access-log --no-proxy-headers
```

Linux/macOS에서는 `.venv/Scripts/python.exe` 대신 `.venv/bin/python`을 사용합니다.
브라우저에서 http://127.0.0.1:8000/docs 를 열고 **POST /api/sessions → Try it out → 본문 `{}` → Execute**를 누릅니다. 201 응답의 sessionId·expiresAt·requestId를 확인합니다. 추천 기능이 연결되지 않아 capabilities의 배열은 비어 있고 지원 여부는 false입니다.
계약 초안은 [contracts/openapi.json](contracts/openapi.json)이며, 서버 문서에는 구현한 경로만 표시합니다. 단일 worker로 실행하며 재시작·reload 시 세션이 사라집니다. 프록시 연결 전에는 신뢰할 프록시와 IP 제한 정책을 별도 설정해야 합니다.
서버 종료는 Ctrl+C입니다. 프론트엔드 실행 명령은 배진호 담당 구현 후 추가합니다.

### 조건 카드 수정 확인

1. 먼저 POST /api/sessions로 새 세션을 만들고 sessionId를 복사합니다. 서버 reload 전 세션은 재사용하지 않습니다.
2. PUT /api/sessions/{sessionId}/profile → Try it out → sessionId에 복사한 값을 입력합니다.
3. 기본 요청 예시(모든 값 null/UNSET, expectedProfileRevision=0)를 Execute합니다. 200·NEEDS_INPUT·profileRevision=1·누락 질문 2개가 나옵니다.
4. 다음 수정에서는 직전 응답의 profileRevision을 expectedProfileRevision에 넣습니다. 0으로 다시 보내면 409입니다. 응답 유실 시 무조건 재전송하지 않습니다.
5. area를 `{ "value": "HAEUNDAE", "source": "USER", "strength": "HARD" }`로 바꾸면 현재 지원 범위가 비어 있어 422 UNSUPPORTED_CONSTRAINT입니다. 실패 시 기존 프로필·revision·만료 시각은 유지됩니다.

PUT은 전체 교체이므로 모든 필드를 보내야 합니다. 삭제할 조건은 null/UNSET, 직접 지정한 값은 USER입니다. 기존 서버 DEFAULT는 값·강도를 그대로 유지하는 경우에만 보낼 수 있습니다. 현재 서버는 기본값을 생성하지 않습니다.
지원 여부는 세션 생성과 수정 검증이 같은 capabilities를 사용합니다. HAEUNDAE/WALK 계약 예시는 가상 시연 자료이며 현재 지원을 뜻하지 않습니다. READY 경로는 테스트 전용 지원 설정으로 검증했으며 운영 앱에서는 아직 반환하지 않습니다.

## 검사

```powershell
.\.venv\Scripts\python.exe contracts/validate_contract.py
.\.venv\Scripts\python.exe contracts/validate_source_sync.py
.\.venv\Scripts\python.exe -m pytest -q
```

계약 검사는 전체 OpenAPI 표준 검증이 아닙니다. 테스트는 공통 오류·세션 생성 응답·만료·revision 동시성·요청 제한을 검증하며 LLM·DB 성공을 뜻하지 않습니다. `python -O`는 기존 assert 검사를 끄므로 사용하지 않습니다.
GitHub Actions는 main/develop push와 PR에서 같은 검사를 실행합니다. 원격 CI의 실제 결과는 Actions에서 확인합니다.

## 다음 작업

1. 팀원 초대·리뷰 규칙 및 첫 주 범위 검토: 김세민 + 전체.
2. LLM 조건 분석 흐름 연결: 김영무. 실제 추천 검증 구현 후 이찬용과 capabilities 확대 검토. 종료 API 정책은 별도 합의.
3. 실제 데이터 표본·이용조건·DB 매핑: 이찬용.
4. 가상 예시로 화면 상태 연결: 배진호.
5. 가상 평가 입력·정답 작성: 김세민.

[연결 지점과 작업 목록](docs/INTEGRATION.md), [결정 및 현재 상태](docs/DECISIONS.md)를 읽고 시작합니다.
비밀 키는 실행 환경에 설정하고 커밋하지 않습니다. 건강 원문·세션·프로필은 저장소·로그·브라우저 영구 저장소에 보관하지 않습니다.
프로젝트 라이선스는 아직 선택하지 않았으며, 데이터 이용조건은 데이터별로 확인합니다.

## 2026-11-11 조건 처리 보완 (기존 PR #13·#17)

#17 모듈이 함께 반영되면 `/api/chat`과 DEC-020 카드 정규화를 사용한다. #13 단독에서는 기존 세션·카드 API만 등록된다. 실제 Provider는 미설정이며 재시도 후 규칙 파서로 대체한다. 현재 capabilities는 비어 있어 활성 조건은 거절된다. 검토 순서·검증·실행 제한·capabilities 활성화 계획은 [구현 기록](docs/ISSUE6_8_IMPLEMENTATION.md)을 따른다. PR/브랜치 병합 없이 소스 검토 사본에서 188개 통합 테스트를 통과했다.
