# 공동 API 계약

API_CONTRACT.md·openapi.json·example-index.json·examples는 기존 초안에서 시작했습니다. 2026-11-10 DEC-019~021은 PR #13의 PM 명시적 결정(2026-11-09)과 PR #18의 결정 기록을 근거로 의미 규칙·스키마 설명·가상 정책 사례에 반영했습니다. PR #18은 확인 시점 미병합이며, 다른 초안 항목이나 실제 서버 기능이 일괄 승인·완료된 것은 아닙니다.
담당: 김영무·배진호, 장소/출처는 이찬용 공동 검토.

validate_contract.py는 기존 검사, validate_source_sync.py는 docs/sources/04번 문서의 JSON과 비교합니다. 후자의 기본 파일 경로만 새 저장소 배치에 맞게 수정했습니다.
예시 장소·출처·시간은 모두 가상입니다. API 구현 현황은 backend/README.md를 확인합니다.

`policy-cases.json`은 14개 가상 계약 시나리오입니다. before·extractedProfile·pendingFields·assumedCapabilities는 검수 메타데이터이며 HTTP 필드가 아닙니다. 기대 요청·응답만 기존 스키마로 검사합니다. 예시의 지원 범위는 현재 서버 capabilities를 활성화하지 않습니다.
`policy_contract.py`는 정적 기대 사례의 상태·출처·질문·경고·revision을 검사하고 잘못된 사례를 넣은 negative control도 확인합니다. 실행은 기존 `python contracts/validate_contract.py`에 포함됩니다. `validate_source_sync.py`는 04번 참고 문서의 정책 사례도 비교합니다. 이 검사들은 서버의 정책 처리 구현을 검증하지 않습니다.

DEC-009 세션 종료는 별도 PR #12의 변경으로, 아직 이 브랜치 기준 develop 계약에는 포함되지 않았습니다. 이 작업은 기존 5 operations·31 schemas의 필드·타입·enum을 유지합니다.
