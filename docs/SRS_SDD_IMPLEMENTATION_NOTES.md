# SRS·SDD에서 옮긴 구현 기록

docs/README 문서 관리 규칙 6항(2026-11-20)에 따라 v1.0 정리(2026-11-27) 때 SRS·SDD 본문에서 **구현·검증 기록**을 이 문서로 옮겼다. 내용은 원문 그대로이며, 요구사항·설계는 바뀌지 않았다. 링크는 `docs/` 기준이다.

설계 내용인 단락(SDD 7.2 API-005 부분 수정 설계, SDD 7.3 COMP-03 추출 근거 검사, SRS 동행 보완 DEC-022)은 본문에 남겼다.

## SRS 본문(3장 요구사항 표 아래)에서 옮긴 단락

FR-009·AI-REQ-01·05의 스케줄러·검증기·POST /api/courses 구현과 가상 4개 시나리오의 자동 검사 결과는 [#23 기록](ISSUE23_COURSES_IMPLEMENTATION.md)을 따른다. 실제 #22·이동시간·Repository 데이터와 해운대 실데이터 하드 위반 0건 및 NFR-001 성능 인수는 아직 검증하지 않았다.

FR-005·006 구현에서 기본 체류시간 설정·도보 기본값·유모차 사용자 우선·예산 제한 없음의 표시, NFR-004·007의 모바일·키보드·오류 포커스를 보완했다. 예산 null/UNSET과 화면 기본 동작의 구분, 실제 #22 연결 후에만 활성화하는 범위와 검증 한계는 [이슈 #21 기록](ISSUE21_DEFAULTS_IMPLEMENTATION.md)을 따른다. 실제 데이터·코스 생성 인수 완료를 뜻하지 않는다.

## SDD 7.3절에서 옮긴 단락

FR-009 구현 보완: CourseService가 CandidateRetriever·TravelTimeProvider·PlaceRepository를 주입받아 CourseScheduler와 CourseValidator를 호출한다. 실제 검색/이동시간을 구현하지 않고 가짜 포트로 먼저 검증했다. 스케줄러는 DB·LLM을 호출하지 않고 검증기는 Repository에서 장소 사실을 다시 확인한다. 배치 초안 후 최대 3회 수리·재검증, 마지막 사실 재검사, API 반환 전 세션 revision/만료 재검사를 수행한다. 코스 경로·필드와 장소 2~6곳 제한은 기존 Course 계약을 유지한다. [#23 연결·검증 기록](ISSUE23_COURSES_IMPLEMENTATION.md).

FR-005·006 보완: config/defaults.json을 서버 기본 체류시간 함수와 카드 안내가 공유한다. application/profile_support.py는 실제 후보 검색 연결·필드 검증 완료를 받은 뒤 지원 범위를 만드는 구성 경계이며 기본 앱은 비활성이다. #22의 검색·항목별 판정과 #23 스케줄러를 새로 구현하지 않았다. [이슈 #21 구현·후속 연결 기록](ISSUE21_DEFAULTS_IMPLEMENTATION.md).

이슈 #20 구현: 추출 Provider는 취소 가능한 Gemini generateContent REST 어댑터이며 JSON 스키마·업무 의미를 검증한다. 실패 시 각 10초·1회 재시도 후 ChatRuleParser로 대체하고 COMP-02가 정책·revision을 처리한다. 기준 한국 날짜를 프롬프트에 제공하며 평가 시에는 평가셋 referenceNow를 고정한다. DEC-022의 영유아 질문 표시 이력·부분 동행은 메모리 세션에만 저장한다. 프론트는 실제 chat/profile API를 순차 호출한다. 일반 capabilities 활성화는 #21·#22의 기존 합의를 유지한다. [실행·검증 기록](ISSUE20_CHAT_IMPLEMENTATION.md).

## SRS 끝 구현 추적 절

### FR-012 구현 추적 (2026-11-16)

이슈 #25의 COMP-08/API-006을 구현했다. 검증된 최종 코스에서만 구조화 근거를 선택하고 시스템이1~2문장·숫자를 조립한다. 실패 시TEMPLATE/AI_FALLBACK을 사용한다. 사용자 원문·세션·전체 프로필은 설명에 보내지 않으며 개요는200자로 제한한다. GET /api/places/{placeId}는 기존 PlaceResponse로 장소·출처·정보 없음·공공데이터 고지를 반환하며 없는 장소404와 저장소 오류500을 구분한다. 코스와 상세의 Place/Source 변환을 공통화했다. 실제 DB·모델·UI-04 연결과 인수 검증은 후속이다. [구현·검증 기록](ISSUE25_EXPLANATIONS_IMPLEMENTATION.md).


### FR-014 ① 구현 추적 (2026-11-17)

이슈 #26 서버 제안 생성을 구현했다. 최종 적용 프로필의 DEFAULT·값 있음·capabilities 지원 항목에서 기존 카드 EDIT_PROFILE을 최대 3개 만든다. 클릭으로 값을 자동 변경하거나 하드 제약을 완화하지 않으며 사용자 카드 저장 후 새 revision으로 재생성한다. 체류시간은 이번 범위에서 제외했다. 정보 없음·날씨·부분 수정 및 프론트 칩·화면 캡처는 후속이다. [구현·검증·인계 기록](ISSUE26_SUGGESTIONS_IMPLEMENTATION.md).


### FR-018 구현 추적 (2026-11-17, 이슈 #27)

동행 카테고리 점수 함수와 가중치 제안 설정을 구현해 가상 후보로 검증했다. 가족 관광·전시·공원 우대 방향은 DEC-013을 따르지만 수치·다른 동행 매핑·실내 대비 계수는 PM 미확정이다. 일반 경로에는 활성화하지 않고 기존 default_score를 유지한다. 가격·분위기·야경·활동성·인원 적합성을 추정하지 않으며 하드 필터·검증기·영유아 유모차·부상 규칙을 유지한다. [제안 표](proposals/issue-27-companion-weights.md), [구현·검증 기록](ISSUE27_COMPANION_SCORING_IMPLEMENTATION.md).

## SDD 끝 구현 보완 기록

### 구현 보완 기록 — FR-002·006·018 / DEC-019~021 (2026-11-11)

COMP-02/03의 application/condition_policy.py는 부분 추출을 기존 프로필과 병합하고 미확인 항목을 세션 내부 pending_fields에 유지한다. 외부 응답 필드는 늘리지 않는다. 질문은 최대 2개이며 코스 진입은 SessionStore.begin_course의 최신 revision·READY 검사를 거친다. 실제 코스 엔진은 아직 미연결이다. AIService·규칙 파서·유모차 정규화는 PR #17, 계약·HTTP 연결은 PR #13으로 구분한다. 구현 상세와 단독/통합 검증, 활성화 계획은 [구현 기록](ISSUE6_8_IMPLEMENTATION.md)을 참조한다. PM의 DEC-019~021은 확정이며 결정 기록 PR #18·SDD 정책 상세 PR #40의 병합 상태와 구분한다.


### FR-012 구현 추적 (2026-11-16)

이슈 #25의 COMP-08/API-006을 구현했다. 검증된 최종 코스에서만 구조화 근거를 선택하고 시스템이1~2문장·숫자를 조립한다. 실패 시TEMPLATE/AI_FALLBACK을 사용한다. 사용자 원문·세션·전체 프로필은 설명에 보내지 않으며 개요는200자로 제한한다. GET /api/places/{placeId}는 기존 PlaceResponse로 장소·출처·정보 없음·공공데이터 고지를 반환하며 없는 장소404와 저장소 오류500을 구분한다. 코스와 상세의 Place/Source 변환을 공통화했다. 실제 DB·모델·UI-04 연결과 인수 검증은 후속이다. [구현·검증 기록](ISSUE25_EXPLANATIONS_IMPLEMENTATION.md).


### FR-014 ① 구현 추적 (2026-11-17)

이슈 #26 서버 제안 생성을 구현했다. 최종 적용 프로필의 DEFAULT·값 있음·capabilities 지원 항목에서 기존 카드 EDIT_PROFILE을 최대 3개 만든다. 클릭으로 값을 자동 변경하거나 하드 제약을 완화하지 않으며 사용자 카드 저장 후 새 revision으로 재생성한다. 체류시간은 이번 범위에서 제외했다. 정보 없음·날씨·부분 수정 및 프론트 칩·화면 캡처는 후속이다. [구현·검증·인계 기록](ISSUE26_SUGGESTIONS_IMPLEMENTATION.md).


### FR-018 구현 추적 (2026-11-17, 이슈 #27)

동행 카테고리 점수 함수와 가중치 제안 설정을 구현해 가상 후보로 검증했다. 가족 관광·전시·공원 우대 방향은 DEC-013을 따르지만 수치·다른 동행 매핑·실내 대비 계수는 PM 미확정이다. 일반 경로에는 활성화하지 않고 기존 default_score를 유지한다. 가격·분위기·야경·활동성·인원 적합성을 추정하지 않으며 하드 필터·검증기·영유아 유모차·부상 규칙을 유지한다. [제안 표](proposals/issue-27-companion-weights.md), [구현·검증 기록](ISSUE27_COMPANION_SCORING_IMPLEMENTATION.md).


### FR-012 실행 연결 보완 (#96, 2026-11-27)

일반 app.main:app의 시작 연결이 DB·검색·계산·승인 가중치를 준비한 뒤 조건 추출과 같은 AIService 및 실행 Repository로 ExplanationGenerator를 자동 구성한다. AIService 연결 풀을 공유하고 종료/시작 실패 시 자동 생성기를 해제한다. 명시적 생성기 주입은 유지한다. API-004의 기존 검증 코스→explain(course, mobility 범주, 남은 시간) 경계·최대12초 설명 예산·재시도 정책과 TEMPLATE/AI_FALLBACK 대체를 그대로 사용한다. JSON 계약 변경은 없고 실제 모델 포함 응답시간/인수 판정은 별도 측정한다. 구현·검증은 [#96 기록](ISSUE96_RUNTIME_EXPLANATIONS.md)에 둔다.
