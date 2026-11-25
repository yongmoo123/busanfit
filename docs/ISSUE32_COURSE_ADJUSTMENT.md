# #32 대화형 부분 수정 — 계약·기본 서버 구현

관련: FR-015, API-005, AC-007, AI-REQ-07 / DEC-006·007·021·024·025·027·030·033.

## 상태

2026-11-25 사용자 요청으로 **일반 시작 연결 성공 후 `supportsCourseAdjustment=true`를 공개**한다. 실제 DB·검색기·계산기·승인 가중치 준비가 실패하면 시작하지 않고 종료 시 false로 초기화한다. 주입 앱은 별도 검증 설정 없이는 기본 false다. 실제 Provider 호출·키/.env 읽기·PR 병합은 하지 않는다. 가상 Provider 자동 검사와 실제 DB·계산기 연결 검증을 구분한다. 이 문서는 구현·연결 참고이며 PM 확정 결정 문서를 대신하지 않는다.

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

## 확정 범위·후속

- **DEC-035 확정:** REPLACE는 원래 시작·종료·체류시간과 다른 방문을 고정한다. 시각 재배치는 범위 밖이고 더 머무르기는 별도 EXTEND_STAY다. 후보가 없으면 NOT_APPLIED와 이유·빼기/체류 늘리기 대안을 반환한다.
- 프론트와 새 응답 상태·질문 field·changes 표시·코스 ID 교체·409 복구 흐름의 실제 연결 확인이 필요하다.
- INDOOR 실제 교체, #55 체류 칩 연결, 실제 LLM20개 평가(80% 목표), 화면 캡처는 별도 후속이다. 평가셋 형식 변경은 계약 공유 후 PM 담당이다. 이번 작업에서 평가 결과를 임의로 통과 처리하지 않는다.

백엔드는 `feature/FR-015-course-adjustment`(#86), 프론트는 `feature/FR-015-course-adjustment-ui`(#89)를 사용한다. 이 브랜치의 최신 커밋으로 서버를 재시작하고 새 세션의 capability=true를 확인한 뒤 연결한다. 기존 서버/세션의 courseId는 가져오지 말고 같은 프로세스에서 새 코스를 만든다. 환경변수로 capability만 강제하는 스위치는 없다. 모델 환경 설정이 없으면 단순 삭제만 규칙 처리하고 교체·연장은 NEEDS_INPUT이며, 실제 자연어 검증은 담당자가 별도로 수행한다.


## 2026-11-23 로컬 검증

- Python3.12 전체 `pytest -q`: **1650 passed, 1 warning**(기존 Starlette/httpx), 82.50초. 기본 커밋187063a 위 수정 작업 트리에서 실행했으며 미커밋 상태다.
- 수정 API·AI 연결 재사용·기존 추천 이유 경계 집중 검사58 passed. 삭제/고정 슬롯 교체/연장, 영업시간·최소2곳, 동시 수정·프로필 변경·삭제, 조건부 코스·경고ID, 후속 원래 대상 매핑, 프로필·동의 미변경, 가상 타임아웃·실패·규칙 대체·문맥 민감정보 미저장을 포함한다.
- 계약 검사7 operations·37 schemas·28 가상 JSON examples·15 정책 사례 PASS. source JSON 동기화·diff 검사 PASS. Python3.11 문법 정적 검사 통과는 런타임3.11 테스트 통과를 의미하지 않는다.
- 전체 검사에서 기존 AI 수명주기 테스트의 해운대1곳 기대값을 현재 설정 권역으로 보정했다. 수정용 문맥은 MODIFY에만 보내고 EXPLAIN wire 기존3필드 형식은 유지한다.
- 실제 LLM20개 평가·실제 프론트 인수는 미실행. 일반 supportsCourseAdjustment=false 유지. 실제 모델 API·키/.env·DECISIONS.md·DB 변경·서비스 활성화·커밋/push·병합 없음.


## 2026-11-25 일반 서버 활성화·연결 검증

이 절은 위 11/23 비활성 상태 기록을 대체하는 최신 상태다. 최신 develop `b890e88`과 DEC-035를 #86 작업 브랜치에 반영했으며 사용자 요청으로 시작 연결 성공 후 수정 지원을 켠다. DECISIONS.md에 별도 수정은 하지 않고 develop의 PM 결정만 통합했다.

- 전체 Python3.12 검사 **1663 passed, 1 warning**, 25.82초. 계약7 operations·37 schemas·28 examples·15 정책 사례와 source sync PASS. 수정 작업 트리에서 측정했으며 최종 커밋을 테스트 당시 커밋으로 소급 표시하지 않는다.
- 신규13개 검사는 명시적 검증·핵심 연결·이동제약 검증이 있어야 지원 공개, 엄격한 boolean, 일반 시작 연결 후 HTTP 삭제·교체·연장·되묻기, 종료 시 지원 해제, 모델 미설정 시 단순 삭제만 규칙 대체를 포함한다. 기존 시작 실패 검사도 지원 false를 확인한다.
- 실제 v3 DB SHA-256 `e8bd5c5142af936e819e71036a7919fa0c847a707dceec94d9b5e6a4a219a6fc`, 전후 해시 동일. 실제 검색기·도보 계산기와 **가상 모델 의도**로 4개 권역 각5건(삭제·교체·15분 연장·해석 불가·1440분 연장), 총20건 HTTP 검증. 실제 LLM 호출0건이다.
- 삭제4건 성공, 15분 연장은 해운대·서면2건 성공/광안리·남포2건 미적용. 고정 슬롯 교체4건은 맞는 후보가 없어 미적용이며 이유·빼기/체류 늘리기 대안 표시를 확인했다. 해석 불가4건은 질문, 과도한 연장4건은 미적용이다. **실제 DB 교체 성공을 확인한 것으로 표시하지 않는다.** 교체·연장 성공 경로는 별도 가상 SQLite+가상 모델 테스트에서 검증했다.
- 수정 성공 코스6개와 미적용/질문의 보존 코스14개를 독립 응답 감사로 검사해 하드 위반·미존재 장소0건. 일반 서버 활성 상태와 종료 후 false를 확인했다. 상세: [검증 결과](ISSUE32_RUNTIME_VALIDATION_20261125.json).
- 실제 LLM20문장 평가, 진호님의 실제 화면 연결·PC/모바일 인수는 후속이다. 실제 모델 호출·키/.env 읽기·유료 전환·GitHub 병합 없음.

### 진호님 실행 순서

1. 백엔드 `feature/FR-015-course-adjustment` 최신 커밋, 프론트 `feature/FR-015-course-adjustment-ui`를 각각 사용한다. 아직 develop에는 이 활성화가 없다.
2. 백엔드 저장소 루트에서 본인 v3 DB 위치를 `BUSANFIT_DB_PATH`로 지정하고 Python 환경으로 `python -m uvicorn app.main:app --app-dir backend --no-access-log --port 8000`을 실행한다. 기존 승인된 모델 환경 설정은 담당자가 사용한다. 이 실행은 실제 메시지 전송 시 LLM을 호출할 수 있으며 이번 검증에서는 호출하지 않았다. 모델 미설정 상태는 단순 삭제 규칙 외 수정이 NEEDS_INPUT이므로 자연어 교체/연장 성공 확인과 구분한다.
3. 프론트 dev 서버의 `/api` 프록시는 기본 `http://127.0.0.1:8000`이며 필요하면 `BUSANFIT_API_TARGET` 또는 `BUSANFIT_API_PROXY_TARGET`을 지정한다. #89 QA 화면 `/?qa=course-adjustment`는 여전히 가상 응답이다. 실제 API 호출 연결은 프론트 후속 작업이다.
4. 새 세션 생성 응답에서 `supportsCourseAdjustment=true`를 확인한다. 같은 서버 프로세스·세션에서 조건 저장과 코스 생성을 수행하고 최신 courseId/profileRevision으로 adjust한다. 서버 재시작 시 이전 세션/코스는 유효하지 않다.
5. SUCCESS는 새 courseId로 교체하고 profileRevision은 유지한다. SUCCESS에도 questions를 표시한다. NEEDS_INPUT/NOT_APPLIED는 기존 코스 유지, 추가 답변도 현재 courseId를 사용한다. 409·응답 유실은 자동 재전송하지 않고 기존 안내대로 복구한다.
