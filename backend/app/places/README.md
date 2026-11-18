# 장소 상세·공통 표시 — FR-012 / API-006

GET `/api/places/{placeId}`는 PlaceRepository의 get_place/get_sources만 사용하며 SQL·LLM·세션을 사용하지 않습니다. 성공 응답은 기존 `{place, sources, warnings, requestId}`, 없는 문자열 ID는 404 NOT_FOUND입니다. 저장소 장애·출처 참조 오류·유효하지 않은 레코드는 500이며 원문 예외를 노출하지 않습니다. 모든 응답은 Cache-Control: no-store입니다.

코스 API도 presentation.py의 Place/Source 변환을 사용합니다. 기본/접근성 출처는 합집합·중복 제거·기본 출처 우선이며 모든 sourceIds에 대응하는 Source가 있어야 합니다. 가격 UNKNOWN과 접근성 항목별 None/false/true를 유지합니다. grade는 표시용입니다.

운영시간 구조화 값이 없으면 UNKNOWN이며 원문은 description에 보존합니다. 원문을 상시 영업으로 해석하지 않습니다. 상세 조회는 운영시간 없는 장소도 보여 주지만 코스 후보 통과를 뜻하지 않습니다. 구조화 값이 잘못되면 데이터 오류입니다. 주소는 기존 계약의 필수 문자열이며 None을 가짜 주소나 빈 문자열로 채우지 않습니다(PM DEC-023, PR #51 참조).

프론트에서는 null을 ‘정보 없음’으로 표시하고 DATA_NOTICE·UNKNOWN 경고를 보여 줍니다. 추천 이유는 기존 계약상 CourseItem.reason/reasonMethod에 있습니다. UI-04는 선택한 코스 항목의 이유와 상세 정보를 함께 표시합니다. UI 구현·캡처는 배진호 담당이며 이번 변경에 포함되지 않습니다.
