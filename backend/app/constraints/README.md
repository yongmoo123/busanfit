# ConstraintAnalyzer — 김영무 · COMP-03

FR-002~006·018 / DEC-001·002·019~021.

profile.py는 카드 의미·지원 범위를 검증한다. 파서·유모차 정규화는 기존 PR #17의 parser.py·mobility.py가 담당하고 application/condition_policy.py가 chat 병합·USER 우선·확인 대기와 상태 판정을 제어한다. 정책은 2026-11-09 PM 결정 완료이며 구현 검증·PR 병합과 구분한다.

스프린트2 기본 이동수단은 WALK/DEFAULT, 스프린트3 PUBLIC 지원과 함께 기본값 PUBLIC으로 전환한다(DEC-001). 영유아 동반·이동제약 null/UNSET이면 STROLLER/DEFAULT/HARD를 적용하고 USER []·목록은 보존한다(DEC-002·020). USER 목록에 유모차가 없으면 경고하며 별도 질문은 추가하지 않는다.

새 chat/카드 정책은 #17 의존 모듈이 있을 때 적용한다. 상세 동작·검증·capabilities 계획은 docs/ISSUE6_8_IMPLEMENTATION.md를 참고한다. 실제 LLM·코스 스케줄러는 미연결이다.
