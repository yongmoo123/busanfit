# 공유 업무 모델
김영무·이찬용 공동 검토. extraction.py에 외부 라이브러리에 의존하지 않는 부분 추출 힌트를 추가했습니다. API Profile의 중복 정의가 아니라 불완전한 동행 힌트·미확인 필드를 보존하는 내부 모델입니다. SDD 4.1의 완성된 ConstraintProfile·Anchor·Course·CourseItem·Suggestion·ChangeOp·Place·Accessibility·DataSource는 아직 미구현입니다.
외부 API 모델은 contracts에 맞춰 api에서 변환한다. 그림의 단일 source/ID 타입과 후속 JSON 계약 차이를 그대로 혼합하지 않는다.
HTTP·DB·LLM 라이브러리에 의존하지 않는 단순 데이터 모델부터 작성한다. Anchor·ChangeOp 등 후속 모델이 있다는 사실은 현재 API 지원을 뜻하지 않는다.
