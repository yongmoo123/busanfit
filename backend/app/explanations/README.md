# ExplanationGenerator — 김영무 · COMP-08
FR-012, AI-REQ-01·02·03, NFR-009. #25의 추천 이유·출처·장소 상세 API를 구현했습니다. 실제 DB·모델·프론트 검증은 후속입니다.

`ExplanationGenerator(ai, repository).explain(course, mobility, remaining_seconds=...)`는 검증 완료된 코스만 받습니다. 최종 장소 ID·이름·카테고리·최대 200자 개요·허용된 사실 키와 이동제약 범주만 모델에 전달합니다. 사용자 원문·세션 ID·전체 프로필·접근성 raw는 보내지 않습니다.

모델 출력은 `{items: [{placeId, facts: ["CATEGORY", "STAY"]}]}`입니다. 장소별 1~2개의 확인된 사실을 모델이 선택하고 시스템이 1~2문장으로 바꿉니다. LLM 임의 문장은 채택하지 않습니다. 숫자는 확정 일정의 체류시간에서 시스템이 삽입하며, 가격·영업시간·새 장소·출처를 모델이 작성하지 않습니다. `reasonMethod=LLM`은 모델의 근거 선택이 반영됐다는 뜻입니다. 풍부한 개요 요약·분위기 판단은 이번 범위에 없습니다.

허용 사실: CATEGORY·STAY, 구조화 값이 일치할 때만 INDOOR·OUTDOOR·WHEELCHAIR·STROLLER. 장소 접근성은 경로 보장과 구분합니다. 모르는 ID는 버리고 누락·중복 ID/사실·미확인 근거는 해당 장소의 TEMPLATE로 대체합니다. 스키마 오류는 AIService가 1회 재시도하며, 재실패·모델 오류·시간 예산 소진은 템플릿과 AI_FALLBACK 경고로 처리합니다. LLM 때문에 코스 장소를 삭제하거나 변경하지 않습니다.

한 번의 배치 호출로 모든 장소를 처리합니다. AIService 시도당 10초·재시도 1회 정책을 재사용하되 설명 호출은 기본 최대 12초, 코스 요청 경과시간을 뺀 잔여 14초 범위에서 제한합니다. 시간이 없으면 호출하지 않습니다. 실제 DB I/O·호스팅까지 포함한 15초 목표는 미검증입니다.

설명 전후 Repository ID·Place·Source·방문 구간 영업시간과 레코드 변경을 확인합니다. 저장소 오류는 성공으로 숨기지 않으며 취소는 전파합니다. API는 설명 후에도 revision·만료를 확인하고 성공 시에만 TTL을 갱신합니다.

```text
python -m uvicorn app.explanation_demo:app --app-dir backend --port 8003 --no-access-log
python -m uvicorn app.explanation_demo:fallback_app --app-dir backend --port 8004 --no-access-log
python evaluation/explanations/run.py --output evaluation/explanations/results/synthetic-2026-11-16.json
```

첫 앱도 실제 LLM이 아니라 SyntheticExplanationProvider입니다. 두 번째 앱은 모델 미설정 실패를 주입합니다. DB·검색·이동시간은 모두 가상입니다. 일반 앱에는 가짜 제공자를 자동 등록하지 않습니다. 실제 연결은 같은 Repository를 사용하는 CourseService·ExplanationGenerator를 `create_app(course_service=..., place_repository=..., explanation_generator=...)`로 주입합니다. 모델은 기존 환경변수와 `AIService(configured_provider())`로 연결할 수 있으나 실제 모델 평가는 별도로 수행해야 합니다.

장소 상세 GET `/api/places/{placeId}`는 LLM 없이 공통 Place/Source 변환을 사용합니다. [전체 실행·검증·후속 기록](../../../docs/ISSUE25_EXPLANATIONS_IMPLEMENTATION.md).
