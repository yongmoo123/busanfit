# 원본 요구사항 등록부와 구현 추적

기준: 원본 SRS v0.1 3·4·8장, SDD 3장. 작성일 2026-10-28.
아래 제목·기준은 요약이며 원문 상세 조건은 docs/sources/01의 SRS 부록을 함께 읽는다. 원본과 후속 계약의 차이는 ORIGINAL_REVIEW.md에서 관리한다.
**모든 업무 요구사항은 미완료다.** 아래 검증은 앞으로 수행할 계획이며 테스트 통과 기록이 아니다. 기존 HTTP 오류 테스트 6개는 일부 기술 골격 검증이며 NFR 전체 완료를 뜻하지 않는다. 김세민은 전 항목의 검수·증거 관리를 총괄한다.

## 기능 요구사항
경로는 frontend, backend/app 아래 해당 영역, pipelines를 뜻한다. TC-001~020은 원본 SRS 10장의 계획 ID이며 실행 테스트 파일이 아니다.

| ID | 원본 우선순위·요구 | 담당·위치 | 검증 계획 / 원본 TC |
|---|---|---|---|
| FR-001 | Must 채팅·대화 맥락 | 배진호 frontend, 김영무 api/application/sessions | 입력·세션 내 맥락 유지 / TC-001 |
| FR-002 | Must 제약 프로필 추출 | 김영무 constraints/ai/domain | 시간·앵커·이동·예산·선호·날씨 민감도·동행 추출 / TC-002 |
| FR-003 | Must 하드/소프트 분류 | 김영무 constraints | 원본 표 3-1, 부정 문맥·강도 승격 / TC-003 |
| FR-004 | Must 누락 되묻기 | 김영무 constraints, 배진호 frontend | 시간/지역 누락 질문, 한 번에 최대 2개 / TC-004 |
| FR-005 | Must 기본값·표시 | 김영무 constraints, 배진호 frontend | 카페 60·식사 70·전시 시설별/60분·대중교통·예산 무제한, 기본값 표시 / TC-005 |
| FR-006 | Must 조건 확인·수정 | 김영무 api/application/sessions, 배진호 frontend | 카드 수정 후 프로필 일치·잘못된 값 거절 / TC-006 |
| FR-007 | Must 필수 조건 후보 검색 | 이찬용 retrieval/data | 지역·시간·접근성·예산·제외 조건 검증 / TC-007 |
| FR-008 | Must 접근성 3단계 | 이찬용 retrieval/pipelines | 확인됨·정보 없음·부적합 및 이동제약 기본 필터 / TC-008 |
| FR-009 | Must 시간 계산·코스 검증 | 김영무 courses, 이찬용 travel/data | 체류+이동·영업시간·시간창, HARD 위반 0 / TC-009 |
| FR-010 | Should 고정 일정 공백 | 김영무 courses/domain | 앵커 시각 불변·이동시간 제외 가용 구간 / TC-010 |
| FR-011 | Must 지도·타임라인 | 배진호 frontend | 번호 마커·방문 시각·체류 및 지도 실패 안내 / TC-011 |
| FR-012 | Must 이유·출처 | 김영무 explanations/ai, 이찬용 data, 배진호 frontend | 이유 1~2문장·실제 출처 연결 / TC-012 |
| FR-013 | Must UNKNOWN 재생성 제안 | 김영무 application, 이찬용 retrieval, 배진호 frontend | 제외 후 제안·동의·경고. 정책 충돌 해결 필요 / TC-013 |
| FR-014 | Must 최대 3개 제안 | 김영무 application/courses, 배진호 frontend | 기본값→UNKNOWN 제외→날씨 위험 우선순위 / TC-014 |
| FR-015 | Should 부분 수정 | 김영무 constraints/courses/application | 변경 연산·부분 재계산·비변경 구간 유지. 불가 시 대안 / TC-015 |
| FR-016 | Should 날씨 | 이찬용 weather/retrieval, 김영무 courses | 강수 60% 이상·특보 실외 제외, 기타 감점·실패 표시 / TC-016 |
| FR-017 | Should 편의시설 | 이찬용 data, 김영무 api, 배진호 frontend | 자차 주차장·운영시간·장애인 주차·역 엘리베이터·보관함 / TC-017 |
| FR-018 | Must 동행 | 김영무 constraints/courses | 동행별 가중치. 영유아→유모차 원본/계약 충돌 해결 필요 / TC-018 |
| FR-019 | Could 공유 | 김영무 application/api, 이찬용 data, 배진호 frontend | 읽기 전용·건강정보 제외·만료 / TC-019 |
| FR-020 | Should 데이터 갱신 | 이찬용 pipelines/data | 수집·정제·중복·좌표·DB 갱신·비민감 배치 로그 / TC-020 |

FR-018은 SRS 추적표에는 있으나 SDD 11장 추적표에서 빠져 있어 COMP-03·05와 연결했다. 이는 요구사항 추가나 담당 변경이 아니다.
FR-013은 Must, FR-015는 Should다. 둘을 하나의 후속 작업으로 묶어 FR-013까지 선택 기능으로 취급하지 않는다.

## 비기능 요구사항
| ID | 원본 우선순위·기준 | 담당·위치 | 검증 계획 |
|---|---|---|---|
| NFR-001 | Must 추출 5초·생성 15초, 10개 중 90% | 김영무 application, 이찬용 data | 전체 응답 시간 측정·재시도 포함 |
| NFR-002 | Must LLM 재시도/복구·공공 API 장애 시 DB | 김영무 ai/application, 이찬용 data | 장애 주입, 원본/계약 fallback 정책 검토 |
| NFR-003 | Must 건강정보 메모리·종료/30분 폐기 | 김영무 sessions/application, 배진호 frontend | TTL 실제 폐기·로그/영구 저장 없음 |
| NFR-004 | Should Chrome/Edge·모바일 360px | 배진호 frontend | 가로 스크롤·브라우저별 동작 |
| NFR-005 | Should 처리시간·LLM 횟수·실패 비민감 로그 | 김영무 api/application/ai, 이찬용 pipelines | 로그 필드·원문/키/토큰 누출 검사 |
| NFR-006 | Must AIService 설정으로 제공자 교체 | 김영무 ai | Provider 교체 시 업무 모듈 수정 없음 |
| NFR-007 | Should 대비 4.5:1·키보드·대체 텍스트 | 배진호 frontend | 접근성 검수 |
| NFR-008 | Must 키 환경변수/Secrets·지도 키 도메인 제한 | 전체, deployment | 저장소·클라이언트·로그·키 제한 검수 |
| NFR-009 | Must 제공기관·데이터명·기준일·이용조건 | 이찬용 pipelines/data, 배진호 frontend | 메타데이터와 화면 출처 일치 |

## AI 요구사항
SRS 8장은 별도 Must/Should 열을 두지 않는다. AI-REQ-07은 FR-015 Should에 연결된다는 비고를 유지한다.

| ID | 원본 기준 요약 | 담당·위치 | 검증 계획 |
|---|---|---|---|
| AI-REQ-01 | DB 장소만, 근거 기반 설명·출처 | 김영무 courses/explanations, 이찬용 data | 코스 10개 DB 미존재 ID 0건 |
| AI-REQ-02 | 지연/스키마 실패 1회 재시도·대체 안내 | 김영무 ai/application | 장애 주입·HARD 보존·시간 예산 |
| AI-REQ-03 | 건강 범주값만 외부 전송·원문 로그 금지·무료 개발 가상 데이터 | 김영무 ai/constraints | 전송 전 범주화·로그 검토 |
| AI-REQ-04 | 추출 문장 30개, 필드 정확도 85% | 김영무 constraints, 김세민 evaluation | 정답 대비 항목별 평가 |
| AI-REQ-05 | 코스 HARD 위반 0% | 김영무 courses | 고정 입력 자동 검증 |
| AI-REQ-06 | 강도 85%·누락 되묻기 100%·2개 초과 질문 0 | 김영무 constraints, 김세민 evaluation | 강도/질문 세트 평가 |
| AI-REQ-07 | 수정 20개, 의도 정확도 80% | 김영무 constraints, 김세민 evaluation | 대상·변경 내용 평가, FR-015 Should |

## 실행 증거 연결 방식
각 이슈·PR에 요구사항 ID, 실제 테스트 경로/평가 결과, 코드 revision, 데이터·모델 버전, 실행일·검수자를 남긴다. SRS 9장의 AC-001~012도 최종 인수 때 대조한다. 단순 폴더·README 생성은 요구사항 완료 증거가 아니다.
