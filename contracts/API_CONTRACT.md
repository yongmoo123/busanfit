# 부산핏 공통 API 계약 v0.1.0
기존 SDD v0.1 및 첫 주 개발 계획에 따른 **팀 합의용 초안**. 서버 구현물이나 실제 API 검증 결과는 아니다. DEC-019~021은 PM의 2026-11-09 명시적 결정에 따라 2026-11-10 계약 의미에 반영했다. 근거는 PR #13 PM 댓글과 PR #18 결정 기록이며, PR #18은 확인 시점에 미병합이다. 이 반영은 다른 초안 항목의 승인이나 서버 구현 완료를 뜻하지 않는다.

## 파일 구성
- openapi.json: OpenAPI 3.1 요청·응답 스키마와 예시.
- examples/: 기존 가상 JSON 예시. policy-cases.json: DEC-019~021의 가상 사전 상태·요청·기대 응답 사례(실행 결과 아님).
- example-index.json: 예시별 대응 스키마.
- validate_contract.py: 외부 패키지 없는 계약·예시 일관성 검사. 전체 OpenAPI 표준 검증기나 서버 통합 테스트는 아니다.

**모든 예시 장소·기관·좌표·운영시간·출처는 가상 fixture다.**
example.invalid는 의도적으로 사용할 수 없는 출처 주소다. 실제 공공데이터로 제출·사용하지 않는다.
데이터 담당자는 확인한 실제 레코드와 이용조건으로 교체해야 한다.

## 1. 첫 주 API
| 메서드·경로 | 요청 | 응답 |
|---|---|---|
| POST /api/sessions | {} | sessionId, expiresAt, capabilities, requestId |
| POST /api/chat | sessionId, message, expectedProfileRevision | status, reply, profile, profileRevision, questions, warnings, sessionExpiresAt, requestId |
| PUT /api/sessions/{sessionId}/profile | expectedProfileRevision, profile | status, profile, profileRevision, questions, warnings, sessionExpiresAt, requestId |
| POST /api/courses | sessionId, profileRevision | status, course, suggestions, warnings, excludedUnknown, sessionExpiresAt, requestId |
| GET /api/places/{placeId} | 경로의 placeId | place, sources, warnings, requestId |

서버 주소는 로컬 예시 http://localhost:8000. 경로에 /api가 이미 포함되어 있다.
세션 생성만 HTTP 201, 나머지 성공은 200. 성공 응답은 별도 data 래퍼 없이 반환한다.

## 2. 공통 형식
- application/json, UTF-8, camelCase. 문서에 없는 필드는 거절한다.
- 날짜·시각은 offset 포함 RFC3339. 예: 2026-11-06T13:00:00+09:00. 표시와 상대 날짜 해석은 Asia/Seoul.
- 시간 범위는 startAt < endAt. 첫 주에는 같은 현지 날짜만 지원한다. 자정 넘는 요청은 422 INVALID_PROFILE.
- 시간은 정수 분, 금액은 정수 원(KRW). latitude=위도, longitude=경도.
- ID는 불투명 문자열로 취급한다. sessionId/course.id/requestId는 UUID, place.id는 문자열.
- 모든 필드는 스키마대로 포함한다. 정보 없음=null, 빈 목록=[], 확인된 부정=false. null을 false·0·무료로 바꾸지 않는다.
- 모든 응답의 requestId는 실제 서버에서 새로 만든다. 고정 예시 ID와 날짜는 테스트 전용이다.
- FastAPI 기본 422 형식도 아래 공통 ErrorResponse로 변환한다.

## 3. 세션·동시 요청
- 세션 비활동 만료는 30분. 유효한 세션 작업이 활동 시간을 갱신하고 sessionExpiresAt을 반환한다. 공개 장소 조회는 갱신하지 않는다.
- sessionId는 비밀 토큰이다. 실제 배포는 HTTPS. 민감한 응답은 Cache-Control: no-store.
- 프론트는 세션·대화·프로필을 메모리로 관리하고 브라우저 영구 저장소에 저장하지 않는다.
- URL 접근 로그에서도 sessionId를 마스킹한다. 원문·프로필·건강 정보를 로그·DB에 남기지 않는다.
- 생성 직후 내부 profileRevision=0. chat/PUT 성공마다 원자적으로 1 증가한다. 실패는 프로필·revision·대화 상태를 변경하지 않는다.
- chat/PUT의 expectedProfileRevision이 서버와 다르면 409. 코스 요청 profileRevision도 서버 최신값과 일치해야 한다.
- 생성 중 프로필이 바뀌면 이전 결과를 최신 코스처럼 반환하지 않고 409 처리한다.
- 첫 주 프론트는 한 세션의 요청을 순차 처리하고 전송 중 버튼을 잠근다.
- 프로필 GET은 이번 범위에 없다. 409이면 대기 중인 성공 응답을 먼저 반영한다. 최신 상태를 복구할 수 없으면 새 세션을 시작한다.
- 응답 유실 시 변경 요청을 무조건 자동 재전송하지 않는다.

## 4. 프로필 의미
각 조건은 {value, source, strength}다.
- source: USER / DEFAULT / UNSET. null 값과 UNSET은 서로 대응해야 한다.
- strength: HARD(필수) / SOFT(선호).
- area/timeWindow는 코스 생성 필수이고 HARD다.
- mobility=null은 미입력. []는 사용자가 이동 제약이 없다고 명시한 경우다. 미입력을 제약 없음으로 확정하지 않는다.
- “실내 위주”는 SOFT, “실외는 절대 안 돼”는 HARD. 단어 하나만 보고 부정 표현을 오해하지 않는다.
- DEC-002·020: companions.hasInfant=true이고 mobility=null/UNSET이면 [STROLLER]/DEFAULT/HARD를 자동 적용한다. 추가 확인 질문은 하지 않는다.
- mobility.source=USER는 자동 기본값보다 우선한다. USER의 []와 비어 있지 않은 목록을 유지하고 STROLLER를 자동 추가하지 않는다.
- 영유아 동반이지만 USER 목록에 STROLLER가 없으면 STROLLER_NOT_APPLIED 경고를 붙인다. 이는 질문 수 한도를 소비하지 않는다.
- 카드에서 STROLLER만 해제하면 다른 이동제약을 유지하고 USER로 저장한다. 해제 상태는 이후 대화에서 자동 재적용하지 않는다. 명시적으로 유모차 사용을 요청하면 기존 제약을 보존하며 STROLLER를 USER/HARD로 추가한다.
- mobility를 null/UNSET으로 초기화하면 영유아 동반 시 기본값 적용 대상으로 돌아간다. 영유아 동반 취소 시 DEFAULT로 적용된 STROLLER만 제거하며 USER 조건은 유지한다. 제거 뒤 남은 값이 없으면 null/UNSET으로 표현한다. 이를 USER의 명시적 [] 선택으로 바꾸지 않는다.
- budget은 amount, currency, basis(PER_PERSON/TOTAL), includes(ADMISSION/FOOD/TRANSPORT)를 함께 저장한다.
- DEC-001: 스프린트 2 기본 이동수단은 WALK/DEFAULT이며 카드에 표시한다. 스프린트 3 PUBLIC 지원과 함께 기본값을 PUBLIC으로 전환한다. 최종 기본값은 PUBLIC이다. 명시적 미지원 요청을 기본값으로 대체하지 않는다.
- chat은 언급된 조건만 기존 프로필에 반영한다. “카페는 빼줘”가 기존 시간을 지우면 안 된다. 파서의 UNSET으로 기존 USER/HARD 조건을 덮어쓰지 않는다. 변경 의도를 해석하지 못했다면 기존 값은 보존하되 UNCONFIRMED_CHANGE와 해당 field 질문으로 확인하고, 확인 전에는 기존 값으로도 코스를 생성하지 않는다.
- PUT은 전체 교체다. 삭제할 값은 null/UNSET으로 명시한다. 카드에서 바꾼 값은 USER로 표시한다.
- 서버는 클라이언트의 source/strength도 검증한다. 지역·시간의 HARD를 임의로 낮추지 못하게 한다.
- DEC-021 NEEDS_INPUT: 생성 필수 정보가 부족하거나 미확인 HARD 조건·변경 의도가 남아 있다. questions는 해당 field를 지정하여 1~2개씩 반환한다. 지역·시간이 있어도 미확인 항목이 남으면 NEEDS_INPUT이다.
- 새 외부 상태·필드는 추가하지 않는다. 서버는 아직 질문하지 못한 항목을 포함해 내부 확인 대기 상태를 유지하며, 질문 2개를 답했다고 다른 미확인 항목을 지우지 않는다. warnings가 없거나 questions에 현재 표시되지 않는다는 이유로 확인 완료로 판정하지 않는다.
- READY: 생성 필수 정보와 확인 대기 항목이 모두 해소된 상태이며 questions=[]. 후보 존재나 코스 성공을 보장하지 않는다. 코스 생성은 서버 최신 revision과 READY를 함께 확인한다. NEEDS_INPUT이면 422 PROFILE_INCOMPLETE로 생성하지 않는다.
- 질문은 최대 2개씩 한다. 불확실한 중요한 조건을 기본값으로 덮어쓰지 않는다.

## 5. capabilities와 첫 주 지원
예시 capabilities는 HAEUNDAE/WALK 및 area,timeWindow,transport,indoorPreference,companions,excludedCategories를 지원한다.
budget/mobility/preferenceTags도 최종 프로필 모양에는 있으나 예시 서버의 첫 주 활성 조건 지원 범위에는 없다.
- 미지원 필드가 null/빈 목록이면 미설정으로 취급할 수 있다.
- 일반 규칙: 비어 있지 않은 미지원 조건은 HARD/SOFT 모두 422 UNSUPPORTED_CONSTRAINT이며 요청 전체를 저장하지 않고 관련 field만 오류 details로 안내한다. 원문을 복사하지 않는다.
- DEC-019 카드 PUT: 미지원 이동수단도 위 규칙대로 422, 요청 전체 미저장 및 기존 프로필·revision·대화·TTL 유지.
- DEC-019 채팅 예외(이동수단만): 해석한 나머지 조건이 유효하면 반영하고 revision을 1 증가시킨다. 미지원 이동수단은 반영하지 않고 questions(field=transport)와 UNSUPPORTED_TRANSPORT 경고를 반환한다. 사용자 수락 전 NEEDS_INPUT이며 기존 이동수단이 있어도 코스를 생성하지 않는다.
- transport 확인 대기 중 시간 등 다른 항목만 수정한 전체 PUT은 기존 WALK/USER가 함께 전송돼도 수락이 아니다. 같은 transport.value의 재전송·source/strength만 변경해도 질문·경고·NEEDS_INPUT을 유지한다. 다른 지원 값으로 실제 변경한 USER 카드 PUT은 해당 대기를 해소한다.
- 같은 도보 값을 다시 선택하는 명시적 수락은 POST /api/chat에 `message="도보로 이동할게요"`와 최신 `expectedProfileRevision`을 보낸다. 카드 저장 후라면 그 응답의 revision을 사용한다. 프론트는 이 문장을 사용자의 명시적 선택 때만 전송하며 경고 닫기·시간 저장에서 자동 전송하지 않는다. 409·422·503 또는 네트워크 실패를 수락 성공으로 표시하지 않고 서버 최신 status·revision을 따른다. 새 외부 필드는 추가하지 않는다.
- 채팅에서 미지원 이동수단을 WALK로 자동 변경하거나 새 DEFAULT를 넣어 수락한 것으로 처리하지 않는다. 기존 값이 없다면 transport=null/UNSET, 기존 값이 있으면 보존한다. 사용자가 명시적으로 수락하면 그때 지원되는 값을 USER로 저장하고 해당 확인 대기를 해소한다.
- 다른 미지원 조건까지 함께 들어온 경우에는 일반 422 규칙을 유지한다. 이동수단 예외가 지역·이동제약 등 모든 미지원 조건을 허용하는 예외는 아니다.
- includeUnknownAccessibility는 첫 주 false만 허용한다. true 요청은 422.
- 권역/이동수단도 capabilities로 검증한다. 구현되지 않은 조건을 지원한다고 표시하지 않는다.
- 이는 최종 SRS Must 요구사항의 삭제가 아니다. 이후 검증을 마친 기능부터 지원 범위를 넓힌다.

동행 보완(DEC-022): 혼자·친구·연인·기타의 영유아 미언급은 false로 처리하며 묻지 않는다. 혼자=1명, 연인=2명이고, 다른 동행 인원을 모르면 companions는 null/UNSET으로 유지하되 인원만을 위한 질문은 하지 않는다. 가족 또는 '아이' 언급에서 영유아 여부가 미확인이면 companions 질문을 한 번 표시한다(지역·시간 우선, 총 최대 2개). 실제 표시된 질문 뒤 다음 채팅에서도 답하지 않으면 false로 처리하고 UNCONFIRMED_CHANGE 경고로 '영유아 동반이면 조건 카드에서 바꿔 주세요.'를 안내한다. 질문 표시 여부와 부분 동행 정보는 세션 내부 상태이며 외부 JSON 필드를 추가하지 않는다. 영유아가 명시되면 인원이 없어도 DEC-020 이동제약 정책은 적용한다.

조건 추출에서 이동제약·제외 카테고리를 추가 언급하면 기존 목록에 합쳐 기존 HARD 제외를 유지한다. 명시적 빈 USER 목록 또는 카드 전체 교체로 목록을 해제할 수 있다. 이동수단 미언급 시 WALK/DEFAULT를 적용하되 기존 값과 미지원·미확인 이동수단 확인 대기는 보존한다.

## 6. 코스 의미·검증
- SUCCESS는 course가 존재, INSUFFICIENT_PLACES는 HTTP 200 + course=null.
- 첫 주 후보가 두 곳 미만이면 후보 부족이다. 시간 안에 못 넣는 장소를 무리하게 채우지 않는다.
- suggestions는 최대 3개, 첫 주 type=EDIT_PROFILE만 허용. 클릭은 조건 입력 카드를 열며 자동으로 조건을 변경하지 않는다.
- course.availableWindow는 사용자의 허용 시간, startAt/endAt은 실제 첫 방문 시작/마지막 방문 종료. 시간을 모두 채울 필요는 없다.
- items.order는 1부터 연속, item.id는 코스 내 고유값. place.id와 구분한다.
- N개 방문이면 legs는 N-1개이며 인접 item.id를 연결한다.
- 다음 방문 시작 >= 이전 방문 종료 + 이동시간. 남는 차이는 대기시간이다.
- totalMinutes = totalStayMinutes + totalTravelMinutes + totalWaitingMinutes = 종료-시작.
- 출발지/귀가 목적지는 첫 주에 받지 않는다. 첫 장소 이전과 마지막 장소 이후 이동은 합계에서 제외한다고 화면에 표시한다.
- 지도 연결선은 방문 순서다. DISTANCE_ESTIMATE를 실제 보행 경로로 표현하지 않는다.
- 이동시간의 method/isEstimate 및 경로 접근성 미검증 상태를 표시한다.
- price.status=UNKNOWN이면 amount=null, basis=UNKNOWN. KNOWN이면 금액 및 PER_PERSON/TOTAL 기준이 필요하다.
- 일부 가격의 합을 전체 예산으로 표시하지 않는다. 가격 수준 등급만으로 원 단위 예산 충족을 주장하지 않는다.
- openHours.UNKNOWN이면 description=null. KNOWN의 문자열은 표시용이며 백엔드는 별도 정규화한 날짜·요일별 운영 구간으로 검증한다.
- HARD 판단에 필요한 운영시간·가격·접근성 정보가 없으면 충족으로 인정하지 않는다.
- accessibility 항목은 true/false/null, VERIFIED는 관련 근거가 있어야 한다. 시설 정보가 전체 경로 접근성을 보장하지 않는다.
- mobility 미입력 일반 코스에는 접근성 UNKNOWN 장소가 포함될 수 있다. 이동제약을 확인한 코스로 표시하면 안 된다.
- validation.PASSED는 checkedHardConstraints에 나열한 조건이 데이터와 추정 방식 기준으로 통과했다는 의미다.
- unverifiedFields가 활성 HARD 조건과 겹치면 PASSED 금지.
- CONDITIONAL은 추후 미확인 정보 포함 동의 기능의 예약 값이다. 첫 주에는 반환하지 않으며 HARD 위반 우회 수단이 아니다.
- excludedUnknown.count는 필수 판단 정보 부족으로 제외한 고유 장소 수. fields는 이유 목록이다.
- sourceIds/evidence.sourceId는 응답 sources에 모두 존재해야 한다. sources의 id는 중복하지 않는다.
- license/baseDate=null은 미확인 표현용이다. 실제 공개 전 이용조건을 확인해야 한다. 제공 기준일과 retrievedAt(조회일)을 구분한다.
- 출처는 시스템이 DB에서 붙인다. LLM이 가격·시간·출처를 만들어내지 않는다.
- 추천 이유 생성 실패는 TEMPLATE 설명과 warnings로 처리할 수 있다.

## 7. 오류
형식: {"error":{"code":"...","message":"...","retryable":false,"details":[{"field":"...","reason":"..."}]},"requestId":"UUID"}
| HTTP | code | 처리 |
|---|---|---|
| 400 | INVALID_REQUEST | 잘못된 JSON |
| 404 | NOT_FOUND | 장소 없음 |
| 409 | REVISION_CONFLICT | 최신 조건 확인 |
| 410 | SESSION_EXPIRED | 새 세션 안내 |
| 422 | INVALID_REQUEST / INVALID_PROFILE / PROFILE_INCOMPLETE / UNSUPPORTED_CONSTRAINT | 해당 필드 수정 |
| 429 | RATE_LIMITED | Retry-After 헤더(초)를 참고해 재시도 |
| 503 | AI_UNAVAILABLE | 조건 카드 직접 입력/재시도 |
| 500 | INTERNAL_ERROR | 일반 오류 안내, 내부 스택 미노출 |

details에 민감한 원문을 넣지 않는다.
첫 주 세션당 분당 20회 제한, 세션 생성은 별도 IP 제한을 적용한다.
retryable=true는 즉시 자동 재전송하라는 뜻이 아니다.
AI 해석 실패 시 하드 조건을 지우고 일반 코스를 만들지 않는다.

### 7.1 DEC-021 LLM 실패·503 판정

LLM 지연(10초 초과)·스키마 불일치는 1회 재시도하고 재실패 시 규칙 파서로 대체한다. 해석하지 못한 HARD 판단 항목(지역·시간·이동제약·제외 카테고리·예산 상한)은 추측하지 않고 UNSET/확인 대상으로 두며 기존 USER/HARD 값을 삭제하지 않는다. 소프트 기본값도 확정된 기본값만 사용한다.

| 상황 | 응답·저장 규칙 |
|---|---|
| LLM 정상, 지역·시간 미입력 | 200 NEEDS_INPUT, 부족 항목 질문 |
| LLM 재실패 → 파서, 기존 유효 값을 포함해 지역도 시간도 없음 | 503 AI_UNAVAILABLE, 카드 직접 입력 안내. 프로필·revision·대화·TTL 미변경 |
| 대체 파서 결과·기존 값으로 하나만 확보 | 200 NEEDS_INPUT, 부족 항목 질문 및 AI_FALLBACK |
| 대체 파서 결과·기존 값으로 둘 다 확보 | 일반 검증 결과. 미확인 HARD·변경 의도가 있으면 200 NEEDS_INPUT, 모두 해소됐으면 READY, 미지원/잘못된 조건은 422 |

이 판정은 세션·revision·요청 제한·입력/지원 범위 검증을 대체하지 않는다. 409·410·422·429를 AI 성공/실패로 덮어쓰지 않는다. 503은 일반 ErrorResponse이며 ChatResponse나 warnings 필드를 추가하지 않는다. 응답 성공 시에만 chat/PUT revision 증가와 TTL 갱신을 적용한다.

200 대체 처리에서는 reply와 AI_FALLBACK 경고로 안내한다. Timeout 안내는 “응답이 늦어 일부 조건을 확인하지 못했어요. 조건 카드에서 확인해 주세요.”를 사용한다. Timeout 후 503이면 같은 안내와 직접 입력 안내를 error.message에 넣을 수 있다. 실패한 해석 결과를 일반 코스 생성에 사용하지 않으며 추천 이유 생성 실패는 기존 템플릿 방식으로 처리한다.

### 7.2 경고 코드 — 김영무 정의 (DEC-019~021 위임 범위)

Warning의 필드는 기존 code/message/placeIds를 유지한다. code는 기존 string 타입을 유지하며 아래 이름을 고정해 호출부·프론트에서 함께 사용한다. 다른 기존 경고 코드를 금지하는 enum 변경은 하지 않는다. 조건 관련 경고의 placeIds는 []이다.

| code | 발생 상황 | 표시·해소 |
|---|---|---|
| UNSUPPORTED_TRANSPORT | 채팅에서 미지원 이동수단을 반영하지 않음 | transport 질문과 함께 표시. 지원 값의 명시적 선택/수락으로 해소 |
| STROLLER_NOT_APPLIED | 영유아 동반 + USER 이동제약 목록에 STROLLER 없음([] 포함) | “유모차 조건은 자동으로 넣지 않았어요. 필요하면 조건 카드에서 추가해 주세요.” 질문을 만들지 않으며 이 경고만으로 NEEDS_INPUT을 강제하지 않음 |
| AI_FALLBACK | LLM 재실패 후 규칙 파서로 응답 | 대체 처리 사실 안내. 이 경고만으로 READY 여부를 판정하지 않음 |
| UNCONFIRMED_CHANGE | 변경 의도 또는 HARD 판단이 미확인 | 해당 field 질문과 NEEDS_INPUT. 확인 전 생성 금지 |

경고는 입력 원문·건강 원문을 복사하지 않는다. 확인 대기 해소는 서버 내부 조건 검증으로 판단하며 프론트가 경고를 닫았다는 이유로 READY가 되지 않는다.

## 8. 예시 사용 순서
기본 흐름:
1. 01-session.request → 01-session.response. 내부 revision=0.
2. 02-chat.request(expected=0) → 02-chat.ready.response(revision=1).
3. 04-course.request(revision=1) → 04-course.success.response.
4. 각 place.id로 상세 요청 → 05-place.response 형식.

조건 카드 수정 분기:
1~2 이후 03-profile.request(expected=1) → 03-profile.response(revision=2).
이후 코스 요청의 profileRevision도 2로 바꾼다. 제공된 04-course 파일은 수정 없는 기본 흐름용이다.
needs-input/insufficient/오류 파일은 서로 독립된 상태 예시다.
실제 서버는 고정 예시의 날짜/UUID/requestId를 그대로 반환하면 안 된다.

## 9. 기존 SDD와의 차이 및 후속 범위
경로는 유지했다. {id} 이름만 {sessionId}로 명확히 했다.
추가 합의 사항: 프로필 revision, capabilities, 상태·오류 형식, nullable 규칙, 여러 출처 sources/sourceIds, 미확인 가격/접근성, 도보 기본값을 쓰는 첫 주 축소 범위.
단일 source에서 여러 sources로 확장했으므로 DB 매핑도 함께 합의한다.
유보 API(이번 OpenAPI에 등록하지 않음):
- POST /api/courses/{courseId}/adjust
- GET /api/facilities
- POST /api/courses/{courseId}/share
- GET /api/share/{shareId}
- 관리자 배치 CLI
특히 adjust는 변경 후 시간 유지·재검증 정책을 합의한 뒤 정의한다.

## 10. 팀원별 시작점
- 김영무: 스키마 기반 요청/응답 모델, 예외 핸들러, 세션 revision 검사.
- 이찬용: Place/Source/Accessibility 형식에 맞춘 실제 DB 변환, 운영시간 내부 정규화.
- 배진호: examples로 mock 연결, 상태별 화면 분기, 지원 범위 표시.
- 김세민: 예시별 검수 시나리오, 실제 데이터·출처 확인, SRS/SDD 변경 기록.
GitHub에 합의 버전을 커밋하고 필드·enum·상태 의미 변경은 프론트·백엔드 공동 PR 검토로 진행한다.

## 구현 상태 기록 (2026-11-11)

이 문서는 형식·의미 계약이며 실행 서버의 지원 선언은 capabilities를 따른다. 기존 PR #13에 조건 chat·카드 정책·내부 확인 대기·코스 진입 guard를 구현했다. #17 모듈을 함께 반영해야 새 처리를 등록하며, 아직 실제 LLM·코스 엔진·프론트는 연결하지 않았다. 기존 JSON 필드·타입·경로의 추가 변경은 없다. 단독/통합 검증과 지원 활성화 계획은 ../docs/ISSUE6_8_IMPLEMENTATION.md를 참고한다.
