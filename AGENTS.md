# 부산핏(BusanFit) — AI 코딩 도구 공통 작업 안내

이 파일은 사용하는 AI 도구(Claude Code, Codex, Cursor, Copilot, Gemini 등)와 관계없이 적용되는 팀 공통 지침이다. 도구별 설정 파일에는 내용을 복사하지 말고 이 파일을 가리키게 한다. 사람이 읽어도 그대로 작업 규칙이다.

소프트웨어공학 팀 프로젝트. 사용자가 채팅으로 말한 제약(시간·이동수단·이동제약·예산·선호·날씨·동행)에 맞춰, 부산 공공데이터에 실제로 있는 장소로만 놀거리 코스를 만드는 웹 서비스.
팀: 김세민(PM·문서·평가), 이찬용(데이터·DB·이동시간·날씨), 김영무(API·세션·LLM·코스 엔진), 배진호(프론트엔드).

## 기준 문서 (충돌 시 위가 우선)
1. `docs/DECISIONS.md` — 확정 결정. 기준 문서보다 최신일 수 있음
2. `docs/srs.md` — 요구사항 (FR/NFR/AI-REQ ID)
3. `docs/sdd.md` — 설계 (COMP/ADR/API ID)
4. `contracts/openapi.json` + `contracts/API_CONTRACT.md` — API 형식과 의미

작업 전 관련 요구사항 ID를 확인하고, 문서와 코드가 다르면 임의로 하나를 고르지 말고 차이를 알린다.

## 설계 원칙 (어기지 않음)
- LLM은 조건 추출·수정 의도 해석·추천 이유 문장만 담당한다. 장소 선택·시간 계산·하드 제약 검증은 규칙 엔진과 DB가 한다.
- 코스에는 DB에 있는 장소 ID만 들어간다. LLM이 장소·가격·운영시간·출처를 만들지 않는다.
- 정보 없음(null/UNKNOWN)을 무료·접근 가능·상시 영업·0분으로 바꾸지 않는다. 미입력(null)과 "없음"([]/false)을 구분한다.
- 하드 제약을 몰래 완화하지 않는다. 확인하지 못한 하드 조건이 있으면 PASSED를 주지 않는다.
- 건강 관련 입력·세션 ID·API 키를 로그·DB·저장소·브라우저 영구 저장소에 남기지 않는다. LLM에 사용자 원문을 보내는 건 사용자가 쓴 말을 해석하는 호출(조건 추출, 수정 의도 해석)뿐이고, 시스템이 만든 데이터를 넘기는 호출(코스 요약, 추천 이유 생성)에는 건강 정보를 범주값으로만 넣는다(DEC-006).
- 코스 엔진은 DB를 직접 호출하지 않고 PlaceRepository 인터페이스만 사용한다.

## 현재 주요 결정 (상세: docs/DECISIONS.md)
- DB: SQLite. 좌표는 latitude/longitude REAL, 반경 검색은 사각형 필터 후 하버사인. DB 파일은 커밋하지 않음 (DEC-005)
- 스프린트 2 범위: 해운대, 도보(WALK)만 지원. 대중교통(PUBLIC)·자차(CAR, 일정이 빠듯하면 가장 먼저 축소)·다른 권역은 스프린트 3 (DEC-001, 008, 010)
- 오류: 잘못된 JSON 400, 검증 실패 422 (DEC-004)
- 가상 예시 데이터를 실제 부산 데이터로 사용하거나 제출하지 않는다.

## 구조
- `backend/app/` — 하나의 FastAPI 앱. api·sessions·ai·courses(김영무), data·travel·weather(이찬용)
- `frontend/` — 배진호 / `pipelines/` — 수집·적재 / `evaluation/` — 평가 입력·정답·결과
- `contracts/` — API 계약과 검사 / `docs/` — 기준 문서와 기록

## 명령 (저장소 루트, Python 3.12)
```text
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements-lock.txt      # Linux/macOS: .venv/bin/python
.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --reload --no-access-log
.venv/Scripts/python.exe contracts/validate_contract.py
.venv/Scripts/python.exe -m pytest -q
```

## 작업 규칙
- 브랜치: develop에서 `feature/FR-xxx-<내용>` 또는 `docs/DEC-xxx-<내용>`. PR은 develop으로.
- 커밋·PR 제목에 관련 ID(FR-, NFR-, DEC-)를 쓴다.
- API·DB·요구사항이 바뀌는 코드 변경은 해당 문서(계약·SDD·SRS)와 테스트를 같은 PR에서 고친다.
- 요구사항·결정 ID는 재번호·재사용하지 않는다. 문서 관리 규칙은 `docs/README.md`.
- 테스트를 실행하지 않았으면 통과했다고 쓰지 않는다.
- 이 파일을 바꾸는 것은 팀 규칙을 바꾸는 것이므로 PM 리뷰를 받는다.
