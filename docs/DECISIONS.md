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
- DB 선택·출처 관계 매핑·건강 원문 외부 전송 전 처리.
- 명시적 세션 종료 API/폐기 방식, UNKNOWN 접근성 포함 정책.
- 팀원 GitHub 계정·CODEOWNERS, 저장소 보호 규칙, 프로젝트 라이선스.

## 아직 구현하지 않은 것
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
