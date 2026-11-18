# 이슈 #25 — 추천 이유·출처·장소 상세 API

2026-11-16(KST), 김영무 담당 COMP-08/API-006. FR-012, AI-REQ-01·02·03, NFR-009 / DEC-003·006·017. 실제 DB는 가상 구현으로 먼저 검증했습니다. UI-04는 배진호 담당입니다.

## 기준과 재사용

- 최신 원격 develop `22f1a03`에서 `feature/FR-012-place-explanations`를 만들고 #23/PR #50의 `7a51a77`까지 재사용했습니다. #20·#21·#23이 미병합이므로 develop diff에 선행 변경도 포함됩니다.
- #23 Place/Source 변환·Repository Protocol·검증기·세션 guard와 #20 AIService·Gemini 어댑터를 재사용했습니다. 새 패키지·DB 스키마·외부 API 필드 변경은 없습니다.
- PM의 PR #51 DEC-023도 읽었습니다. 주소 필수·운영시간 미구조화 코스 제외 방향을 유지하며 실제 중심 좌표·검색 제외 규칙·적재는 데이터 담당 후속입니다. 미병합 결정 문서를 통째로 합치지 않았습니다.

## 구현

1. `app/places/presentation.py`: 코스·상세 Place/Source 변환 공통화. 기본/접근성 출처 합집합·중복 제거·참조 완전성 검사. 운영시간 구조화 값이 없으면 UNKNOWN, 원문은 보존. 접근성 None/false 구분과 가격 UNKNOWN 유지.
2. `app/api/places.py`·`place_models.py`: GET `/api/places/{placeId}`, 기존 PlaceResponse와 requestId/no-store. 없는 ID 404, 저장소 장애·깨진 출처·유효하지 않은 레코드는 500. 세션·TTL·LLM을 사용하지 않으며 주소 None을 임의로 채우지 않음.
3. `app/domain/explanation.py`: 최대 6개 최종 장소, 최대 200자 개요와 허용 사실 키의 내부 모델. AI CourseContext에 구조화 장소를 추가. 사용자 원문·세션·전체 프로필·접근성 raw 전송 금지.
4. `app/explanations/generator.py`: 모델이 장소별 확인된 근거 1~2개를 선택하고 시스템이 1~2문장으로 조립. 임의 문장을 사실처럼 채택하지 않고 숫자는 확정 일정에서 삽입. CATEGORY/STAY와 확인된 실내·실외·장소 접근성만 사용하며 개요의 새로운 사실을 설명에 옮기지 않음.
5. Gemini EXPLAIN 호출은 user_message=None 대신 구조화 CourseContext JSON을 실제 요청 본문에 전달. 출력 JSON 스키마와 temperature 0.2 사용. 추출 호출의 기존 본문 유지.
6. 스키마 오류·타임아웃은 기존 AIService가 1회 재시도. 전체 설명 시간 예산 안에서만 호출. 재실패·누락·중복·미확인 근거는 해당 장소의 TEMPLATE/AI_FALLBACK으로 대체. 목록 밖 ID는 설명에서 버리고 검증된 코스는 유지. 임의 문장·가격·시간·출처 필드는 거절.
7. POST `/api/courses` 최종 검증 뒤 설명 연결. 장소·일정·sourceIds·하드 검증 결과는 유지. 설명 전후 ID·Place·Source·방문 구간 영업시간 및 레코드 변경 확인. API에서 revision·만료를 재확인하고 실패 응답은 TTL을 갱신하지 않음.

`reasonMethod=LLM`은 모델이 고른 근거를 시스템이 문장화한 경우입니다. 자유 서술의 의미 검증을 흉내 내지 않는 제한적인 초기 구현입니다. 외부 계약 변경 없이 환각 사실 유입을 막기 위한 구현 선택이며 풍부한 개요 요약·개인화 설명 품질은 후속 검토 사항입니다.

## 실행과 가상 범위

Python 3.12, backend/requirements-lock.txt 설치 후 저장소 루트에서 실행합니다.

```text
.venv/Scripts/python.exe -m uvicorn app.explanation_demo:app --app-dir backend --port 8003 --no-access-log
.venv/Scripts/python.exe -m uvicorn app.explanation_demo:fallback_app --app-dir backend --port 8004 --no-access-log
```

`/docs`에서 POST sessions → READY 조건 PUT → POST courses → 반환 place.id로 GET places 순서입니다. 가상 선택 경로는 LLM, 실패 주입 앱은 TEMPLATE/AI_FALLBACK입니다. 첫 앱의 LLM 표시는 프로토콜 분기 검증이며 실제 모델 호출을 뜻하지 않습니다. `synthetic:unknown-detail`은 상세 전용 정보 없음 픽스처이고 코스 후보에 넣지 않습니다.

일반 앱에는 가상 제공자를 자동 등록하지 않고 capabilities도 열지 않습니다. 실제 연결은 같은 Repository를 사용하는 CourseService·ExplanationGenerator를 앱 생성 시 주입합니다. Gemini는 기존 환경변수와 `AIService(configured_provider())`로 연결할 수 있습니다. 키·원문·세션 ID는 결과/로그에 저장하지 않습니다.

## 검사 기록

Python 3.12.14 전체 **391 passed**(선행 331 + 신규 60), 기존 Starlette/httpx 경고 1건. 공통 검사도 통과했습니다.

```text
python -m pytest -q
python contracts/validate_contract.py
python contracts/validate_source_sync.py
git diff --check
python evaluation/explanations/run.py --output evaluation/explanations/results/synthetic-2026-11-16.json
```

- 계약: 5 operations·31 schemas·20 examples·15 정책 사례/negative controls·참고 문서 JSON 동기화 통과.
- 상세: 정상·404·UNKNOWN·출처 합집합/누락·DB 장애·잘못된 레코드·세션 TTL 불변 검사.
- 설명: 성공·재시도·장애·시간 예산·취소·미존재/누락/중복 ID·미확인 사실·임의 문장 차단, 범주화 입력·개요 200자, 대기 중 DB 변경 검사.
- Gemini 어댑터의 HTTP 본문은 httpx.MockTransport로 검사. 외부 네트워크/실제 모델 호출 없음.
- 설명 중 revision 변경·만료·세션 폐기, 오류 우선순위·실패 시 TTL 불변 검사.
- 별도 Uvicorn 실제 HTTP smoke에서도 세션→조건→코스→상세 연결(SUCCESS 4곳·가상 LLM 선택)과 정보 없음 상세 UNKNOWN을 확인했습니다. 세션 ID를 출력/저장하지 않았고 확인 서버는 종료했습니다.
- 독립 하드 검사기와 일반·휠체어·유모차·부상 × 가상 선택/실패 **8개 HTTP/ASGI 시나리오** 실행. 하드 위반 0건, 상세 Place와 코스 Place 일치, UNKNOWN 보존 확인. 최종 실행 revision·가상 지연은 결과 JSON을 따르며 실제 모델 정확도·DB 성능·15초 인수 결과가 아님.

## 후속 작업과 프론트 인계

1. #7 실제 Repository/출처·개요·운영시간·접근성 연결. 데이터 담당과 레코드 유효성·조회 일관성/트랜잭션·DB I/O 제한 합의.
2. #22 실제 검색·이동시간을 #23에 연결하고 해운대 실제 4개 시나리오 검증.
3. 실제 모델의 사실 키 선택·설명 품질·지연·실패율을 가상 입력으로 평가하고 시연용 유료 API 정책 확인. 실제 외부 API·호스팅 포함 15초 목표 검증.
4. 배진호 UI-04: CourseItem.reason/reasonMethod + 상세 API의 place/sources/warnings 조합. 상세 계약에 reason 추가 없음. null은 정보 없음으로, 제공기관·데이터명·기준일·이용조건과 공공데이터 고지 표시. 화면·캡처·프론트 lint/build는 이번 범위에 없음.
5. #26 제안·#27 점수화·#29 앵커·#32 수정은 별도. 선행 PR과 develop 반영 후 통합 검사 필요. 이번 작업은 로컬 구현·검증이며 PR 게시·원격 CI·이슈 종료는 수행하지 않음.


## 기존 PR #54 보완 (2026-11-17)

최신 #50의 세션 종료·SQLite 연결 검증을 통합하고, 실제 SQLite 코드/가상행의 설명·상세·두 출처 일치와 HTTP 삭제 중 설명 성공/오류의410 우선 검사를 보완했다. 전체610 passed(기존 경고1건), 계약6 operations·참고 문서 동기화 통과. 실제 모델 평가는 사용자 요청으로 보류하고 UI-04·실데이터 연결은 후속이다. 새 PR을 만들지 않고 기존 브랜치를 갱신한다.
