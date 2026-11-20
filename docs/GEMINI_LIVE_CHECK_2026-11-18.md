# Gemini 실제 조건 추출 확인 — 2026-11-18

관련: FR-002·FR-003, AI-REQ-02·03, DEC-006·007·021. 기존 공개 API 계약과 결정은 변경하지 않는다.

## 원인과 수정

수정 전 실제 응답에서 미입력 `mobility`가 `value=null`, `strength=SOFT`로 반환되어
`hard condition required` 검증에 실패했다. 기존 프롬프트와 서버 검증은 이동제약을 HARD로
요구했지만, 모델에 전달한 공통 Profile JSON 스키마는 해당 필드에도 HARD·SOFT를 모두 허용했다.
루트 모델의 사후 검증 오류라 재시도에 보낼 필드명도 확보하지 못했다.

- 추출 전용 `ExtractionProfile`과 `HardExtractionCondition`으로 `area`, `timeWindow`,
  `mobility`, `budget`, `excludedCategories`의 `strength`를 `Literal['HARD']`로 제한한다.
- 프롬프트에 미입력 null/UNSET도 해당 다섯 필드는 HARD라는 규칙과 mobility 예시를 추가한다.
- 값·출처를 사후 보정하거나 하드 제약을 완화하지 않는다. 잘못된 강도는 필드 위치를 포함한
  검증 오류로 거절하고 기존 1회 재시도·규칙 대체 정책을 따른다.
- 공개 `Profile` 및 API 계약은 그대로다. 이동수단 등 SOFT 필드의 명시적 HARD 승격도 유지한다.

## 실제 호출 결과

검증 경로: 로컬 `.env` → 기존 `GeminiProvider` REST 어댑터 → `AIService` →
`ExtractionOutput`의 JSON·업무 검증. 가짜 Provider와 규칙 파서는 사용하지 않았다.
일반 서버 capabilities를 활성화하거나 실제 장소 DB를 연결하지 않았다.

- 모델: `gemini-3.5-flash-lite` (무료 구간 테스트; 결제 설정 변경 없음).
- 성공 시각: 2026-11-18 23:22:04 KST.
- 가상 입력 조건: 2026-11-23 13:00~17:00 KST, 해운대, 도보, 친구 포함 총 2명, 영유아 없음.
- 실제 응답 검증 성공, `failure=null`, 규칙 대체 미사용.
- 지역·이동수단·시간창·동행 검증 모두 통과.
- 2회 시도로 성공, 총 19,625ms. 첫 시도 성공이나 15초 이내 성능 달성을 주장하지 않는다.
- 기반 커밋은 `4c536f12d4367fe669625d09be9cddbbca0ed721`이며 위 수정이 있는 로컬 작업 트리에서 실행했다.
  최종 커밋 SHA는 이후 커밋 시 기록한다.

키·입력 원문·모델 응답 전문·세션 ID는 기록하지 않는다.
집계 증빙: [실제 호출 결과 JSON](evidence/gemini/live-check-2026-11-18.json).

## 로컬 검증

- 신규 회귀 검사로 수정 전 스키마의 HARD 제한 누락을 재현했다.
- 추출·AI 경계·신규 검사 74 passed.
- 전체 pytest 746 passed, 기존 Starlette/httpx deprecation 경고 1건.
- 계약: 6 operations·31 schemas·20 JSON examples·15 정책 사례/negative controls 통과.
- 참고 문서 JSON 동기화·`git diff --check` 통과.

전체 AI 평가셋 정확도·반복 호출 안정성·실제 LLM을 연결한 브라우저/실데이터 인수는 아직 수행하지 않았다.
현재 서버 과부하·타임아웃은 별개로 재발할 수 있다. 이 단일 성공을 평가 정확도 85%나 서비스 전체 완료로 해석하지 않는다.
