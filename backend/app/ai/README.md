# AIService·Provider — 김영무 · COMP-09
FR-002 일부, NFR-002·006, AI-REQ-02·03. 2026-11-08 내부 골격 구현. 실제 LLM·HTTP chat·세션·규칙 파서 자동 연결은 미구현입니다.

## 인터페이스

`Provider.complete(AIRequest) -> str`은 취소 가능한 비동기 호출이며 JSON 문자열을 반환합니다. `AIService.complete(purpose, output_model, user_message=..., context=...)`가 목적별 프롬프트와 Pydantic 출력 스키마를 전달하고 엄격한 JSON 검증을 수행합니다. 업무 출력 모델은 호출자가 전달합니다. 스키마 검증은 업무 의미·HARD 검증·사실 검증을 대신하지 않습니다.

- Purpose.EXTRACT: 조건 추출, 사용자 원문 허용.
- Purpose.MODIFY: 수정 해석, 사용자 원문과 범주화된 CourseContext 허용.
- Purpose.EXPLAIN: 사용자 원문 인자를 거절하고 CourseContext만 허용. 현재 컨텍스트는 장소 ID와 이동제약 범주만 받습니다. 실제 장소 사실을 담는 설명 컨텍스트와 출력 모델은 후속 구현 대상입니다.

CourseContext에는 자유 형식의 건강 요약·대화 이력을 받는 필드가 없습니다. 호출자는 검증된 DB 장소 ID와 WHEELCHAIR/STROLLER/INJURY 범주만 전달해야 합니다(DEC-006). 임의 문자열인 장소 ID 내부의 민감 내용을 자동 탐지·정제하는 기능은 아닙니다. request/context/result 기본 repr에 원문을 표시하지 않고 이 계층은 로그를 출력하지 않습니다. 호출부·배포 로그는 별도 검증해야 합니다.

## 실패 처리

기본 **각 시도당 10초**, 실패 후 **1회 재시도**, 최대 2회 호출입니다. 두 번 지연되면 합계 약 20초와 취소 정리 시간이 걸릴 수 있습니다. SRS 성능 목표 충족을 검증한 결과가 아닙니다. Provider는 이벤트 루프를 막지 않고 취소에 협조해야 합니다. 취소를 무시하는 SDK를 강제 종료하는 기능은 아닙니다.

timeout_seconds는 양의 유한 int/float만 허용합니다. NaN·무한대·bool·0 이하·문자열·None·float로 표현할 수 없는 큰 정수는 Provider 호출 전에 ValueError로 거절합니다. 기본 10초와 1회 재시도 정책은 유지합니다(2026-11-09 보완).

타임아웃·스키마 불일치·Provider 오류를 재시도하고 AIResult에 data 또는 failure(TIMEOUT/INVALID_OUTPUT/PROVIDER_FAILURE)와 attempts를 반환합니다. 스키마 재요청에는 알려진 스키마 필드 이름만 넣고 입력값·오류 원문은 복사하지 않습니다. 외부 asyncio 취소는 재시도하지 않고 전파합니다.

내부 실패 결과는 HTTP 503 판정이 아닙니다. 규칙 파서 호출·기존 조건 병합·미확인 HARD 생성 차단·API 응답 변환은 후속 작업입니다. HTTP 429 backoff와 실Provider 예외 분류도 아직 연결하지 않았습니다.

## 테스트와 미완료

fake.py의 FakeProvider는 FakeReply로 정상·지연·실패를 재현하고 받은 요청을 보관하지 않습니다. 네트워크·API 키·모델 비용이 없으며 응답은 가상 값만 사용합니다.

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_ai_service.py -q
```

실모델·요금·이용조건을 선택하지 않았습니다. 실제 LLM 연결·추천 이유 완성·전체 오류 복구·보안 검증 완료를 뜻하지 않습니다.
