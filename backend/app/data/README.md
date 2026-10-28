# DB·PlaceRepository — 이찬용 · COMP-10
FR-007·008·012·020. 현재 미구현.
입력: 정규화된 실제 장소/출처, 지원 검색 조건. 출력: 계약의 Place·Source 및 내부 운영시간 구간.
원본 SRS 2.3·SDD ADR-007 기준은 PostgreSQL+PostGIS입니다. SQLite는 계획서의 대안이며 채택 시 별도 변경 합의가 필요합니다. 김영무와 Repository 입출력·복수 출처 매핑을 맞춥니다. 후보 판단은 retrieval/COMP-04에서 분리합니다.
좌표·원본 ID·중복·출처 연결·누락을 검증하고 UNKNOWN은 그대로 유지합니다.
외부 수집은 pipelines, 요청 시 검색은 이 영역입니다. 초기 적재 재현은 pipelines와 함께 검수합니다.
FR-017의 역·주차장·엘리베이터·보관함 조회도 담당합니다. FR-019 공유 저장은 Could 후속이며 세션/건강 원문 저장과 구분합니다.
