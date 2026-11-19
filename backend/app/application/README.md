# Orchestrator — 김영무 · COMP-02
조건 정책·프로필 지원·코스 생성·기본값 제안 흐름을 구현했다. API 라우팅과 분리한 요청 흐름 제어 위치다(SDD 2~3장). 날씨·공유 등 후속 연결은 미구현이다.
세션 조회→조건 분석/확인→검색·날씨→배치→검증→설명·출처→결과/제안 반환을 조정한다.
실패 시 상태 보존, revision 검사, 생성 도중 프로필 변경 감지를 sessions와 함께 담당한다.
FR-013·014 제안과 FR-019 공유(Could)의 제어도 이 계층에 둔다. 후속 API는 계약 검토 전 노출하지 않는다.

## FR-014 ① 기본값 조정 제안 (#26)

suggestions.py는 최종 적용 Profile과 capabilities에서 DEFAULT·값 있음·수정 가능한 기존 카드 필드를 골라 최대 3개의 EDIT_PROFILE을 생성한다. CourseService의 정규화 후 성공 코스에서만 사용하며 후보 부족은 빈 목록이다. id는 edit-default-{field}, field는 기존 카드 항목이며 label은 사용자 원문을 포함하지 않는다. 클릭만으로 값을 바꾸지 않고 카드 저장 후 USER 출처·최신 revision으로 재생성한다. 체류시간·정보 없음·날씨 제안은 제외한다. [구현·검증·인계 기록](../../../docs/ISSUE26_SUGGESTIONS_IMPLEMENTATION.md).
