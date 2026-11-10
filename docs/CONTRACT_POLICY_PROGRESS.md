# DEC-019~021 API 계약 반영 기록

- 날짜: 2026-11-10
- 상태: 로컬 계약 수정·검증, 커밋·push·PR 미수행. 서버 정책 구현과 프론트 연결은 미완료.
- 관련: 이슈 #6 / FR-001·002·004·005·006·018, NFR-002·003, AI-REQ-02
- 근거: [PR #13 PM 결정 댓글](https://github.com/yongmoo123/busanfit/pull/13#issuecomment-6734033507), [PR #18](https://github.com/yongmoo123/busanfit/pull/18) head 9320ffa500f86a9cf1a2eb66986f4e736e3db1fa의 DEC-019~021.
- 결정일/결정자: 2026-11-09 / 김세민(PM). 명시적 결정과 문서 PR의 병합 상태를 구분하며 PR #18·#13은 조회 시점 미병합.

## 실제 반영

- API_CONTRACT §4: USER 이동제약 우선, 영유아 유모차 DEFAULT/HARD·해제·초기화·취소·경고, NEEDS_INPUT 확장과 서버 확인 대기 보호.
- §5: 카드 PUT의 미지원 이동수단은 422 전체 미저장, 채팅은 해당 이동수단만 미반영하고 나머지 유효 조건 반영·질문/경고. 수락 전 WALK로 자동 변경하지 않음.
- §7: 기존 값 포함 지역·시간이 모두 없고 LLM 재실패 후 파서 대체인 경우만 503, 일반 미입력 및 하나만 확보 시 NEEDS_INPUT, 기존 HARD 보존·미확인 변경 시 생성 차단.
- 경고 코드 이름: 김영무에게 위임된 범위에서 UNSUPPORTED_TRANSPORT·STROLLER_NOT_APPLIED·AI_FALLBACK·UNCONFIRMED_CHANGE로 정의. 기존 Warning.code string을 enum으로 바꾸지 않음.
- OpenAPI는 의미 설명과 기존 형식의 응답 예시만 갱신. 새 HTTP 경로·필드·타입·상태 enum 없음.
- 가상 정책 사례 14개와 정적 의미 검사·negative control 추가. 참고 문서에 같은 의미·스키마·정책 사례를 동기화.

## 담당 간 영향과 다음 구현

1. 김영무: 유모차 정규화, chat 입력/기존 값 병합, AIService→규칙 파서 대체 흐름, 503/NEEDS_INPUT/READY 판정, 내부 미확인 항목 유지·코스 생성 차단 구현.
2. 배진호: transport 수락 질문, 422 필드 안내, STROLLER_NOT_APPLIED 경고, 확인 질문 최대 2개씩, 503 카드 직접 입력 표시 연결. 경고 닫기를 확인 완료로 보내면 안 됨.
3. 질문이 두 개를 넘으면 남은 확인 항목은 서버 내부에 유지하고 차례로 질문. 외부에 pendingFields 같은 새 필드를 추가하지 않음.
4. 실제 조건 지원 검증 후 capabilities 활성화 시점을 함께 확인. 이 사례의 가상 지원 범위를 실제 서버 지원으로 표시하지 않음.
5. DECISIONS의 반영 체크박스는 실제 병합 후에만 갱신. PM 결정 문서 원본이나 기존 제안 문서는 이번에 수정하지 않음.

## 검증 범위

- 기존 5 operations·31 schemas·20 JSON examples 및 정책 사례 14개 정적 검증.
- 본문 의미·OpenAPI 설명·참고 문서 JSON 일치 확인. 스키마 구조 비교에서 설명을 제외한 components.schemas의 필드·타입·필수 항목·enum 변경 없음 확인.
- 기존 백엔드 회귀 테스트는 구현 변경 유무와 별개로 실행 결과를 아래에 기록. 가상 기대 응답은 실제 chat 호출 결과가 아님.
- 실제 LLM·DB·프론트 통합·새 정책 HTTP 처리는 미검증이며 이슈 #6 전체 완료가 아님.
- 실제 결과: 계약 검사(5 operations·31 schemas·기존 예시 20개·정책 사례 14개 및 negative control), 참고 문서 JSON 동기화, 스키마 구조 비교·git diff --check 통과. 최신 develop 기반 기존 백엔드 테스트 47개 통과, 기존 Starlette/httpx 경고 1건. AIService·파서는 별도 PR #17이므로 이 계약 브랜치에 포함하지 않음.

검사 명령:

```powershell
.\.venv\Scripts\python.exe contracts/validate_contract.py
.\.venv\Scripts\python.exe contracts/validate_source_sync.py
.\.venv\Scripts\python.exe -m pytest -q
```
