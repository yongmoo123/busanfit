# feat: FR-009 코스 생성 — 스케줄러·검증기·POST /api/courses 가상 연동

대상 develop. 로컬 설명 초안이며 아직 게시하지 않았다.

후보·이동시간·Repository를 주입하는 CourseService와 스케줄러·검증기·POST /api/courses를 구현했다. 정상 코스만 2~6곳으로 반환하며, 최대 3회 교체 후에도 안전한 두 곳을 만들지 못하면 후보 부족으로 반환한다. 미확인 하드 조건·장소 미존재·영업시간 위반·부상 10분 초과를 통과시키지 않는다. 의존성 장애와 실제 후보 부족을 구분하고 생성 중 revision·만료를 재검사한다.

#22와 이동시간 계산은 이찬용 담당으로 유지하고 FakeRetriever·FakeTravel·FakeRepository로 먼저 검증했다. PR #15의 Repository Protocol/공통 레코드/ID 규칙을 변경 없이 선택 재사용했다. 가짜 제공자는 일반 앱에서 자동 사용하지 않고 일반 capabilities도 열지 않는다. 최소 TEMPLATE 이유와 suggestions=[]는 #25·#26 연결 전 범위다.

기존 #49/#48의 세션·기본값을 재사용하므로 선행 PR 미병합 시 develop diff에 선행 변경도 포함된다. 구현·실행·테스트·성능 수치·한계는 [검증 기록](ISSUE23_COURSES_IMPLEMENTATION.md)과 [가상 결과](../evaluation/courses/results/synthetic-2026-11-13.json)를 따른다. 프론트 코스 연결·실제 DB·검색·이동시간·LLM을 검증한 것은 아니다.

후속: #22 실제 연결 입출력 합의, 해운대 4개 시나리오 하드 위반/미존재 ID 0건, 실환경 15초 목표 측정, #21 실제 활성화, #24 프론트, #25·#26·#27·#29·#32 후속. 실제 데이터 완료 기준이 남아 있어 이슈 #23을 자동 종료하지 않는다.

로컬 검사: Python 3.12.14 pytest **331 passed**(기존 251 + 신규 80), 기존 경고 1건. 계약 5 operations·31 schemas·20 examples·15 정책 사례 및 참고 문서 동기화·diff 검사 통과. 독립 검사기로 4개 가상 시나리오 40회에서 하드 위반/가상 Repository 미존재 ID 0건과 15초 이내를 확인했다. 별도 Uvicorn HTTP 요청도 4개 시나리오 성공이다. 실제 데이터/호스팅의 15초 목표 인수나 원격 CI 결과를 의미하지 않는다.

Refs #23, #20, #21. 관련 FR-009, AI-REQ-01·05, NFR-001·002·003·005, DEC-001·014·015·016·021.
