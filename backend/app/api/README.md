# API — 김영무
현재: 공통 오류 처리. 다음: 기존 계약의 sessions/chat/profile/courses/places 5개 API 모델·라우터.
FR-001·002·006·009·012. 외부 경로와 필드는 contracts를 따릅니다. 서비스 로직은 각 내부 영역에 위임합니다.
입력 실패는 공통 오류, 성공 여부와 지원 범위는 실제 구현을 기준으로 반환합니다.
COMP-02의 HTTP 경계이며 파이프라인 순서 제어는 application/Orchestrator로 위임합니다. 전체 9개 HTTP API와 관리 CLI 매핑은 docs/COMPONENT_MAP.md에 있습니다.
