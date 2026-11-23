# #32 대화형 부분 수정 — 계약·기본 서버 구현

관련: FR-015, API-005, AC-007, AI-REQ-07 / DEC-006·007·021·024·025·027·030·033.

## 상태

서버 기본 구현과 가상 검증 단계다. **일반 `supportsCourseAdjustment=false`를 유지**한다. 실제 Provider 호출·새 API 키 읽기·일반 활성화·병합은 수행하지 않는다. 테스트에서는 명시적인 DI와 가상 capability만 사용한다. 이 문서는 구현·연결 참고이며 PM 확정 결정 문서를 대신하지 않는다.

## 요청·응답

`POST /api/courses/{courseId}/adjust`

```json
{
  "sessionId": "11111111-1111-4111-8111-111111111111",
  "expectedProfileRevision": 3,
  "message": "2번 빼줘"
}
```

응답은 `AdjustmentResponse`다. 기존 전체 `Course`, `suggestions`, `warnings`, `excludedUnknown`, `sessionExpiresAt`, `requestId`를 재사용하고 `profileRevision`, `changes`, `questions`를 추가한다. 완전한 가상 예시는 `contracts/examples/07-adjust.*.json`을 참조한다.

| status | course | changes / questions |
|---|---|---|
| SUCCESS | 새 ID의 수정된 전체 코스 | 제거·교체·시각 변경 itemId. 첫 요청 적용 후 후속 questions도 가능 |
| NEEDS_INPUT | 기존 코스 그대로 | changes는 빈 목록, 대상/분/의도 질문 또는 조건 카드·#30 확인창 안내 |
| NOT_APPLIED | 기존 코스 그대로 | changes는 빈 목록, 불가 사유·대안 경고 |

`questions.field`는 기존 ProfileField 전용 질문과 다른 수정 전용 모델이다. `adjustment.target/minutes/message/followUp` 또는 `profile.<ProfileField>`를 사용한다. 표시 순서는 1부터 다시 부여하며 유지된 항목의 itemId는 보존한다. 교체된 항목은 새 itemId와 oldItemId/newItemId 매핑을 반환한다. 프론트는 index가 아니라 itemId로 변경을 강조한다.

## 코스 버전·원자성

- 성공한 일반 코스 생성부터 마지막 코스를 **세션 메모리에만** 보관한다. 요청 원문·전체 대화·건강 상세·세션 ID를 새 로그/DB에 저장하지 않는다. 세션 만료·삭제·서버 종료 때 함께 폐기한다.
- 수정 성공은 새 courseId를 발급하고 profileRevision은 유지한다. 별도 공개 courseRevision은 두지 않는다.
- 채팅/PUT이 프로필 revision을 올리면 마지막 코스·후속 수정 질문을 무효화한다. 새 코스를 생성해야 조정할 수 있다.
- 시작 및 저장 직전 profileRevision·마지막 코스·내부 epoch를 검사한다. 동시 수정·동시 일반 생성·느린 LLM 뒤 조건 변경이 최신 결과를 덮어쓰지 못한다.
- HTTP 오류는 프로필·코스·TTL을 바꾸지 않는다(기존 요청 제한 카운터는 소비). HTTP200이면 TTL을 갱신한다. NEEDS_INPUT은 프로필 준비 상태를 바꾸지 않고 별도 정규화된 수정 질문 문맥만 보관한다.
- 409이면 대기 중인 성공 응답을 먼저 반영한다. 복구 불가 시 사용자에게 새 생성/새 세션을 안내한다. 수정 응답 유실 때 자동 재전송하지 않는다. 같은 코스의 요청은 순차 처리하고 전송 중 버튼을 잠근다.

## 구현한 연산

- **REMOVE**: 지정 대상만 삭제한다. 남은 장소·상대 순서·방문 시각·체류시간을 보존하고 연결 구간만 재계산한다. 2곳 미만이 되거나 새 구간이 조건을 위반하면 미적용. 자동으로 장소를 추가하지 않는다.
- **REPLACE**: 사용자 확인 범위대로 대상의 시작·종료·체류시간 및 나머지 모든 일정을 고정한다. 현재 프로필·후보 제외 규칙과 고정 슬롯을 만족하는 다른 후보만 선택한다. 카테고리 미지정이면 제한 없음. 후보 기본 체류시간에 맞춘 일정 변경은 하지 않는다.
- **EXTEND_STAY**: 대상의 시작 시각은 유지하고 요청한 분만큼 늘린다. 앞 장소는 그대로, 뒤 장소는 장소·순서·체류시간을 유지하고 이동에 필요한 만큼 시각만 뒤로 민다. 기존 대기시간으로 흡수할 수 있으면 불필요하게 밀지 않는다. 영업시간·시간창을 넘거나 이동을 검증하지 못하면 기존 코스 유지. 연장 분 미입력은 질문하고 추측하지 않는다.
- 새 후보·기존 방문 모두 Repository 사실, 실제 거리 근거, 이동시간, 기존 CourseValidator로 재검증한다. 전체 재생성으로 부분 수정 조건을 우회하지 않는다.
- 기존 명시적 동의와 capability가 있을 때만 접근성 null을 유지할 수 있다. 실제 null을 포함하면 CONDITIONAL과 정확한 UNKNOWN_ACCESSIBILITY_INCLUDED.placeIds를 다시 구성한다. 접근성 false·운영시간 누락 등 다른 하드 조건은 유지한다.

## 의도 해석·기본 예외

- 기존 AIService MODIFY 경계(시도당10초·재시도1회·계측/연결 재사용)를 사용한다. 사용자 메시지와 검증된 순서·공개 장소명·카테고리·실내 여부·시각 및 건강 범주만 전달한다. 원문은 문맥/세션/로그에 보관하지 않는다. 장소 선택·시간 계산은 LLM에 맡기지 않는다.
- 두 번 실패하면 완전한 단일 `N번 빼줘` 등 삭제 패턴만 규칙 처리하고, 나머지는 NEEDS_INPUT이다. 모호한 대상·없는 번호를 다른 장소로 바꾸지 않는다.
- 여러 수정은 첫 연산만 적용하고 나머지를 정규화된 구조로 보관·질문한다. 삭제로 표시 순번이 변하면 살아남은 itemId를 기준으로 후속 대상을 다시 연결한다. 대상이 사라졌다면 다시 질문한다.
- `PROFILE_CHANGE`는 현재 프로필을 바꾸지 않고 조건 카드/채팅→재생성을 안내한다. `INCLUDE_UNKNOWN`은 #30 확인창→명시적 수락→전체 PUT→새 revision POST를 안내하며, 해석 결과만으로 동의하지 않는다.
- `INDOOR` 실제 교체는 기본 3연산 범위 밖이므로 미적용 안내를 반환한다. 별도 적용·활성화하지 않는다.

## 오류

기존 ErrorResponse와 Cache-Control: no-store를 유지한다. `COURSE_NOT_FOUND`(404, 수정할 세션 코스 없음), `COURSE_CONFLICT`(409, 최신 코스 아님/동시 처리)가 추가된다. 기존 400/422 INVALID_REQUEST, 409 REVISION_CONFLICT, 410 SESSION_EXPIRED, 422 PROFILE_INCOMPLETE/UNSUPPORTED_CONSTRAINT, 429 RATE_LIMITED 및 Retry-After, 500 INTERNAL_ERROR를 사용한다. 비활성 API는 실제 해석 전에422를 반환한다. 해석 불가 자체는 500/503이 아니라200 NEEDS_INPUT이다.

## 미합의·후속

- **미합의 유지:** REPLACE 후 후보 기본 체류시간 적용, 다른 방문 시각 당김/밀림, 일정 재배치. 이번 구현은 고정 슬롯만 지원한다.
- 프론트와 새 응답 상태·질문 field·changes 표시·코스 ID 교체·409 복구 흐름의 실제 연결 확인이 필요하다.
- INDOOR 실제 교체, #55 체류 칩 연결, 실제 LLM20개 평가(80% 목표), 화면 캡처와 일반 활성화는 별도 후속이다. 평가셋 형식 변경은 계약 공유 후 PM 담당이다. 이번 작업에서 평가 결과를 임의로 통과 처리하지 않는다.

정식 지원 전에는 가상 응답으로 화면을 준비하고, 실제 연결 안내와 capability가 true인 것을 확인한 뒤 연결한다.


## 2026-11-23 로컬 검증

- Python3.12 전체 `pytest -q`: **1650 passed, 1 warning**(기존 Starlette/httpx), 82.50초. 기본 커밋187063a 위 수정 작업 트리에서 실행했으며 미커밋 상태다.
- 수정 API·AI 연결 재사용·기존 추천 이유 경계 집중 검사58 passed. 삭제/고정 슬롯 교체/연장, 영업시간·최소2곳, 동시 수정·프로필 변경·삭제, 조건부 코스·경고ID, 후속 원래 대상 매핑, 프로필·동의 미변경, 가상 타임아웃·실패·규칙 대체·문맥 민감정보 미저장을 포함한다.
- 계약 검사7 operations·37 schemas·28 가상 JSON examples·15 정책 사례 PASS. source JSON 동기화·diff 검사 PASS. Python3.11 문법 정적 검사 통과는 런타임3.11 테스트 통과를 의미하지 않는다.
- 전체 검사에서 기존 AI 수명주기 테스트의 해운대1곳 기대값을 현재 설정 권역으로 보정했다. 수정용 문맥은 MODIFY에만 보내고 EXPLAIN wire 기존3필드 형식은 유지한다.
- 실제 LLM20개 평가·실제 프론트 인수는 미실행. 일반 supportsCourseAdjustment=false 유지. 실제 모델 API·키/.env·DECISIONS.md·DB 변경·서비스 활성화·커밋/push·병합 없음.
