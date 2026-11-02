# 백엔드

하나의 FastAPI 앱으로 통합합니다. 김영무는 api/application/sessions/constraints/explanations/ai/courses, 이찬용은 retrieval/data/travel/weather를 담당합니다. domain은 공유 모델을 검토하는 위치입니다.
실행·검사 명령은 루트 README에 있습니다.

현재 구현: POST /api/sessions, 메모리 세션 저장소, 30분 비활동 만료·주기적 정리·원자적 revision 갱신·요청 제한 및 공통 오류 응답. 입력·예외 원문을 오류 응답에 반영하지 않습니다.
chat/profile/course/place API·DB·LLM·CORS 설정은 아직 구현하지 않았습니다. 내부 저장소의 409·410 처리는 테스트했으며 실제 업무 API 연결은 다음 단계입니다. 기능이 없는데 READY/SUCCESS를 반환하는 대체 코드를 넣지 않습니다.
테스트 전용 경로는 테스트 코드에서만 등록합니다. 운영 앱에는 없습니다.

## 첫 구현 작업 — 김영무
관련 FR-001·002·006, NFR-003·008.
1. contracts의 요청/응답 모델과 공통 오류 의미를 구현합니다.
2. 세션 생성·30분 비활동 만료·명시적 종료 정책을 구현/검토합니다.
3. profileRevision 0 시작, 성공 변경만 원자 증가, 충돌 409와 만료 410을 시험합니다.
4. 요청 제한·로그 보호를 추가한 뒤 chat/profile/course 담당 흐름을 연결합니다.

실제 LLM 조건 추출·미지원 조건 거절 없이 가상 성공 응답을 서비스 API로 노출하지 않습니다. 단일 worker로 시작하며 세션 공유 방식을 바꾸기 전 다중 worker를 사용하지 않습니다.
개발 실행은 `--no-access-log`를 사용합니다. 향후 프록시·배포 환경도 세션 토큰 URL과 건강 원문이 기록되지 않는지 별도로 검증합니다.

구현 참고: [FastAPI 앱 시작](https://fastapi.tiangolo.com/tutorial/first-steps/), [공통 오류 처리](https://fastapi.tiangolo.com/tutorial/handling-errors/).
