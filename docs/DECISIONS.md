# 결정·구현 상태 기록

## 2026-10-27 — 저장소 초기 구성
상태: 사용자 김영무의 저장소 구성 요청에 따라 준비. 팀 전체 기술·정책 합의와 구분합니다.
- 대상: https://github.com/yongmoo123/busanfit (원격 조회 시 빈 저장소 확인).
- 기능별 전체 폴더와 담당 안내, 기존 자료 보존 사본, 계약 검사·CI 정의·이슈/PR 양식, FastAPI 실행 및 오류 처리 골격을 추가합니다.
- 기존 API 경로·필드·타입·상태·revision 및 예시 JSON을 변경하지 않습니다. 스키마 동기화 검사 경로만 새 배치로 변경합니다.
- 역할 담당 변경 없음. 분리된 폴더는 하나의 앱 내부 책임 구분입니다.
- 초기 main/develop 등록 이후 기능 PR은 develop으로 진행합니다. 원격 업로드 결과·CI 상태는 실제 실행 결과로 별도 기록합니다.

## 미합의 유지
- SRS 대중교통 기본값과 첫 주 WALK 예외, 첫 권역 및 capabilities.
- 출처 관계 매핑·건강 원문 외부 전송 전 처리. DB는 원본 대조 후 PostgreSQL+PostGIS 기준으로 정정(아래 기록).
- 명시적 세션 종료 API/폐기 방식, UNKNOWN 접근성 포함 정책.
- 팀원 GitHub 계정·CODEOWNERS, 저장소 보호 규칙, 프로젝트 라이선스.

## 초기 구성 당시 미구현 범위 (2026-10-27)
5개 업무 API·세션·LLM·실DB·이동시간·날씨·프론트·지도·전체 평가. 앱이 실행되는 것으로 FR 완료를 주장하지 않습니다.
자동 검사 정의는 GitHub Actions 실행 성공과 구별합니다. 테스트 결과는 실행 후 기록합니다.

## 로컬 검증 결과 — 2026-10-27
- Python 3.12.14, 고정 의존성 backend/requirements-lock.txt 사용.
- 기존 계약 검사: 5 operations·31 schemas·20 JSON examples PASS.
- 문서 JSON 동기화: 31 schemas·20 examples PASS.
- HTTP 경계 테스트: 6 passed. /docs·구현 경로 목록·404·입력 타입/추가 필드 거절·잘못된 JSON·500에서 민감 원문 미반영 및 no-store/requestId 확인.
- 최초 HTTP 검사는 Windows 샌드박스의 asyncio 로컬 소켓 생성에서 정지하여, 권한 승인 후 샌드박스 밖에서 실행해 통과.
- Starlette가 TestClient의 httpx 사용에 대해 deprecation 경고 1건을 출력함. 테스트 실패는 아니며 향후 테스트 의존성 갱신 시 검토.
- 실LLM·DB·지도·5개 업무 API 및 GitHub Actions 실행 결과는 위 로컬 통과에 포함하지 않음.

## 2026-10-28 — 원본 대조 후 구조 보완
상태: 김영무의 원본 기준 구조화 요청에 따른 수정, 미합의 정책의 새 승인 아님.
- 10월 27일 원본 DOCX 3개의 본문·표 및 SRS 도식 2개·SDD 도식 9개 검토. 중지 후 28일 재개.
- application/constraints/explanations/retrieval/domain과 deployment 안내를 추가해 SDD의 책임을 구분. 역할 담당·단일 앱 구조 유지.
- SRS 2.3·SDD ADR-007은 PostgreSQL+PostGIS 기준임을 확인. 초기 안내에서 DB 전체를 미정으로 표시한 부분을 정정. 상세 DB/API 매핑은 미합의 유지.
- 원본 Python 3.11과 로컬 검증 3.12를 구분하고 CI에 두 버전 정의.
- SRS 전체 FR 20개·NFR 9개·AI 요구사항 7개의 위치와 미완료 상태를 등록. SDD 추적표에서 빠진 FR-018도 포함.
- 기존 API 계약·가상 JSON·실행 코드 변경 없음. 첫 주 5개 API가 원본 전체 기능을 대체하지 않음.
- 원본과 후속 초안의 기본값·영유아·UNKNOWN·실패 처리 차이는 ORIGINAL_REVIEW.md에 기록. 임의로 정책을 확정하지 않음.
- 원본 파일과 무가공 추출본은 저장소에 올리지 않음. 원본 DOCX 변경 없음.

## 2026-11-02 — 김영무 세션 기능 첫 구현
상태: develop 최신 반영 후 사용자 요청에 따른 구현. 생성 제한 수치·명시적 종료 정책의 팀 승인 아님.
- POST /api/sessions와 요청/응답 모델, 30분 메모리 TTL, 주기적 만료 정리, 종료 시 폐기, revision 원자 갱신 및 요청 제한 구현.
- FR-001·006, NFR-003·008 일부에 해당. chat/profile/course 연결·LLM·DB·명시적 종료 API는 미완료.
- 계약 경로·필드·타입 변경 없음. 현재 추천 기능이 없으므로 capabilities 배열은 빈 값, 지원 여부는 false. 첫 권역·이동수단의 합의를 대신하지 않음.
- 프론트는 생성 201과 422·429, expiresAt을 연결할 수 있음. 내부 409·410은 향후 업무 API에 연결하며 새 HTTP 경로를 만들지 않음.
- 개발용 기본 생성 제한: 접속 IP당 20회/분, 최대 세션·IP 버킷 각 1,000개. 단일 worker 사용. 공유 네트워크·프록시 배포 전 정책 검토 필요.
- Python 3.12 로컬 테스트 16개 통과. 생성 응답의 기존 계약 적합성, TTL 경계·갱신, 복사본 격리·충돌 시 상태 보존, 동시 수정 한 건 반영, 오래된 코스 revision 거절, 요청 제한, 유휴 정리·종료 폐기 확인.
- 기존 Starlette/httpx deprecation 경고 1건 유지. 실제 LLM·DB·배포 검증을 수행했다는 의미가 아님.
