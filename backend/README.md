# 백엔드

하나의 FastAPI 앱으로 통합합니다. 김영무는 api/application/sessions/constraints/explanations/ai/courses, 이찬용은 retrieval/data/travel/weather를 담당합니다. domain은 공유 모델을 검토하는 위치입니다.
실행·검사 명령은 루트 README에 있습니다.

현재 구현: POST /api/sessions, 메모리 세션 저장소, 30분 비활동 만료·주기적 정리·원자적 revision 갱신·요청 제한 및 공통 오류 응답. 입력·예외 원문을 오류 응답에 반영하지 않습니다.
PUT /api/sessions/{sessionId}/profile도 구현했습니다. 전체 교체·필수 필드·엄격한 타입·null/UNSET·USER/DEFAULT 출처·지역/시간 HARD·한국 시각 날짜 범위·중복 목록·지원 범위를 검증하고 성공 시 revision과 TTL을 갱신합니다. 이력은 유지하며 실패 시 프로필·이력·revision·TTL은 변경하지 않습니다.
POST /api/chat은 AIService → Gemini 또는 규칙 파서 → 부분 병합·되묻기·DEC-019~022 정책으로 연결했습니다. POST /api/courses도 스케줄러·검증기와 연결했으며 후보 검색·이동시간·Repository를 주입해야 합니다. 일반 서버는 가짜 구현을 자동 사용하지 않습니다. place API·실제 DB·CORS 설정은 아직 미연결입니다. 409·410·429는 외부 호출 전 검사하고 완료 직전 revision·만료를 다시 검사합니다. 일반 서버의 활성 조건은 실제 연결 검증 전 빈 capabilities에 따라 거절합니다. [#23 실행·검증](../docs/ISSUE23_COURSES_IMPLEMENTATION.md).
테스트 전용 경로는 테스트 코드에서만 등록합니다. 운영 앱에는 없습니다.

ai/service.py의 AIService·Provider와 constraints의 규칙 파서를 HTTP·세션에 연결했습니다. Gemini REST 어댑터는 backend/.env의 키와 모델 이름을 설정한 경우에 사용하며, 키가 없으면 규칙 대체로 진행합니다. 실제 모델 정확도 측정은 아직 실행하지 않았습니다. 실행 방법과 가상 데모의 범위는 [이슈 #20 기록](../docs/ISSUE20_CHAT_IMPLEMENTATION.md)을 참고하세요.

## 첫 구현 작업 — 김영무
관련 FR-001·002·006, NFR-003·008.
1. contracts의 요청/응답 모델과 공통 오류 의미를 구현합니다.
2. 세션 생성·30분 비활동 만료·명시적 종료 정책을 구현/검토합니다.
3. profileRevision 0 시작, 성공 변경만 원자 증가, 충돌 409와 만료 410을 시험합니다.
4. 요청 제한·로그 보호를 추가한 뒤 chat/profile/course 담당 흐름을 연결합니다.

실제 LLM 조건 추출·미지원 조건 거절 없이 가상 성공 응답을 서비스 API로 노출하지 않습니다. 단일 worker로 시작하며 세션 공유 방식을 바꾸기 전 다중 worker를 사용하지 않습니다.
개발 실행은 `--no-access-log`를 사용합니다. 향후 프록시·배포 환경도 세션 토큰 URL과 건강 원문이 기록되지 않는지 별도로 검증합니다.

구현 참고: [FastAPI 앱 시작](https://fastapi.tiangolo.com/tutorial/first-steps/), [공통 오류 처리](https://fastapi.tiangolo.com/tutorial/handling-errors/).
