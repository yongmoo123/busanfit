# 백엔드

하나의 FastAPI 앱으로 통합합니다. 김영무는 api/application/sessions/constraints/explanations/ai/courses, 이찬용은 retrieval/data/travel/weather를 담당합니다. domain은 공유 모델을 검토하는 위치입니다.
실행·검사 명령은 루트 README에 있습니다.

현재 구현: POST /api/sessions, 메모리 세션 저장소, 30분 비활동 만료·주기적 정리·원자적 revision 갱신·요청 제한 및 공통 오류 응답. 입력·예외 원문을 오류 응답에 반영하지 않습니다.
PUT /api/sessions/{sessionId}/profile도 구현했습니다. 전체 교체·필수 필드·엄격한 타입·null/UNSET·USER/DEFAULT 출처·지역/시간 HARD·한국 시각 날짜 범위·중복 목록·지원 범위를 검증하고 성공 시 revision과 TTL을 갱신합니다. 이력은 유지하며 실패 시 프로필·이력·revision·TTL은 변경하지 않습니다.
chat/course/place API·DB·LLM·CORS 설정은 아직 구현하지 않았습니다. 409·410·429는 조건 카드 HTTP 경로에 연결했습니다. 활성 조건은 현재 빈 capabilities에 따라 거절합니다. 기능이 없는데 READY/SUCCESS를 반환하는 대체 코드를 넣지 않습니다.
테스트 전용 경로는 테스트 코드에서만 등록합니다. 운영 앱에는 없습니다.

작업 E 골격: ai/service.py의 AIService·Provider, fake.py의 가짜 Provider, constraints/parser.py의 규칙 파서, domain/extraction.py의 부분 추출 결과를 추가했습니다. 독립 모듈이며 기존 HTTP·세션·capabilities에는 연결하지 않았습니다. 실제 모델 호출 없이 재시도·타임아웃·취소·스키마 검증·보수적 키워드 추출을 검사합니다. 지원 문법·미완료 정책은 각 영역 README를 참고합니다. FR-002 전체나 추출 정확도 목표 완료가 아닙니다.

## 첫 구현 작업 — 김영무
관련 FR-001·002·006, NFR-003·008.
1. contracts의 요청/응답 모델과 공통 오류 의미를 구현합니다.
2. 세션 생성·30분 비활동 만료·명시적 종료 정책을 구현/검토합니다.
3. profileRevision 0 시작, 성공 변경만 원자 증가, 충돌 409와 만료 410을 시험합니다.
4. 요청 제한·로그 보호를 추가한 뒤 chat/profile/course 담당 흐름을 연결합니다.

실제 LLM 조건 추출·미지원 조건 거절 없이 가상 성공 응답을 서비스 API로 노출하지 않습니다. 단일 worker로 시작하며 세션 공유 방식을 바꾸기 전 다중 worker를 사용하지 않습니다.
개발 실행은 `--no-access-log`를 사용합니다. 향후 프록시·배포 환경도 세션 토큰 URL과 건강 원문이 기록되지 않는지 별도로 검증합니다.

구현 참고: [FastAPI 앱 시작](https://fastapi.tiangolo.com/tutorial/first-steps/), [공통 오류 처리](https://fastapi.tiangolo.com/tutorial/handling-errors/).
