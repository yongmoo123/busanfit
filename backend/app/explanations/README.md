# ExplanationGenerator — 김영무 · COMP-08
현재 미구현. FR-012, AI-REQ-01·02.
검증된 코스와 DB 장소 정보로 이유 1~2문장을 생성한다. ai/AIService는 모델 호출만 담당한다.
출처는 data/PlaceRepository의 근거로 시스템이 붙이고 가격·시간을 LLM이 새로 만들지 않는다.
설명 실패는 템플릿 대체가 가능하다. 조건 해석 실패와 같은 fallback으로 처리하지 않는다.
