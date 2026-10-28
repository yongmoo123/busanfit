# 공유 업무 모델
현재 미구현. 김영무·이찬용 공동 검토. SDD 4.1 도메인 모델 그림을 바탕으로 ConstraintProfile·Constraint·Anchor·Course·CourseItem·Suggestion·ChangeOp·Place·Accessibility·DataSource의 내부 모델을 정의할 위치다.
외부 API 모델은 contracts에 맞춰 api에서 변환한다. 그림의 단일 source/ID 타입과 후속 JSON 계약 차이를 그대로 혼합하지 않는다.
HTTP·DB·LLM 라이브러리에 의존하지 않는 단순 데이터 모델부터 작성한다. Anchor·ChangeOp 등 후속 모델이 있다는 사실은 현재 API 지원을 뜻하지 않는다.
