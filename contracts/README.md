# 공동 API 계약

API_CONTRACT.md·openapi.json·example-index.json·examples는 기존 초안을 그대로 복사했습니다. 승인된 최종 계약으로 승격하지 않았습니다.
담당: 김영무·배진호, 장소/출처는 이찬용 공동 검토.

validate_contract.py는 기존 검사, validate_source_sync.py는 docs/sources/04번 문서의 JSON과 비교합니다. 후자의 기본 파일 경로만 새 저장소 배치에 맞게 수정했습니다.
예시 장소·출처·시간은 모두 가상입니다. API 구현 현황은 backend/README.md를 확인합니다.

2026-11-08 DEC-009 반영: DELETE /api/sessions/{sessionId}를 계약·구현·검사에 추가했습니다. 현재 6 operations이며 나머지 미합의 정책의 새 승인이 아닙니다. 종료 예시는 examples/06-session-delete.http이고 204 본문이 없어 JSON 예시 목록에는 추가하지 않습니다. 오류는 기존 ErrorResponse입니다.
