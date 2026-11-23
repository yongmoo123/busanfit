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
| DELETE /api/sessions/{sessionId} | 경로 UUID, 본문 없음 | 204, 본문 없음 (DEC-009) |
| POST /api/chat | sessionId, message, expectedProfileRevision | status, reply, profile, profileRevision, questions, warnings, sessionExpiresAt, requestId |
| PUT /api/sessions/{sessionId}/profile | expectedProfileRevision, profile | status, profile, profileRevision, questions, warnings, sessionExpiresAt, requestId |
| POST /api/courses | sessionId, profileRevision | status, course, suggestions, warnings, excludedUnknown, sessionExpiresAt, requestId |
| POST /api/courses/{courseId}/adjust | sessionId, expectedProfileRevision, message | status, course, profileRevision, changes, questions, suggestions, warnings, excludedUnknown, sessionExpiresAt, requestId (FR-015, 일반 비활성) |
| GET /api/places/{placeId} | 경로의 placeId | place, sources, warnings, requestId |

서버 주소는 로컬 예시 http://localhost:8000. 경로에 /api가 이미 포함되어 있다.
세션 생성은 HTTP 201, 세션 종료는 본문 없는 204, 나머지 성공은 200. 성공 응답은 별도 data 래퍼 없이 반환한다.

## 2. 공통 형식
- application/json, UTF-8, camelCase. 문서에 없는 필드는 거절한다.
- 날짜·시각은 offset 포함 RFC3339. 예: 2026-11-06T13:00:00+09:00. 표시와 상대 날짜 해석은 Asia/Seoul.
- 시간 범위는 startAt < endAt. 첫 주에는 같은 현지 날짜만 지원한다. 자정 넘는 요청은 422 INVALID_PROFILE.
- 시간은 정수 분, 금액은 정수 원(KRW). latitude=위도, longitude=경도.
- ID는 불투명 문자열로 취급한다. sessionId/course.id/requestId는 UUID, place.id는 문자열.
- 모든 필드는 스키마대로 포함한다. 정보 없음=null, 빈 목록=[], 확인된 부정=false. null을 false·0·무료로 바꾸지 않는다.
- JSON 응답의 requestId는 실제 서버에서 새로 만든다. 세션 종료 204는 본문이 없어 requestId 필드를 반환하지 않는다. 고정 예시 ID와 날짜는 테스트 전용이다.
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

### 세션 명시적 종료 — DEC-009 (2026-11-08 반영)
- DELETE /api/sessions/{sessionId}, 요청 본문·revision 없음. UUID 형식 오류는 422 INVALID_REQUEST.
- 성공은 204와 Cache-Control: no-store, JSON·빈 객체·requestId 응답 본문 없음. 이미 없는 세션·만료된 세션·재호출도 204.
- 저장소에서 프로필·이력·revision·세션별 요청 제한 상태를 제거한다. 다른 세션과 IP별 생성 제한 기록은 유지한다. 종료는 TTL을 갱신하지 않고 세션 작업 제한에 막히지 않는다.
- 종료 이후 시작하거나 완료되는 세션 작업의 최신 상태 확인은 410. 종료 전에 이미 완료된 작업의 응답 전달 순서까지 보장하는 것은 아니다.
- 프론트는 새로 시작 시 종료를 호출하고 로컬 세션·프로필·진행 중 응답을 정리한다. 탭 종료 호출은 가능한 범위에서만 시도하며 30분 TTL이 최종 수단이다. 실제 프론트 연결은 별도 확인한다.
- 예시: contracts/examples/06-session-delete.http. 204는 본문이 없으므로 가짜 응답 JSON을 만들지 않는다. 이 변경은 DEC-009 반영이며 다른 미합의 정책을 확정하지 않는다.

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
일반 `app.main:app` 서버는 시작 시 `BUSANFIT_DB_PATH`의 읽기 전용 DB·#65 검색기·실제 COMP-06·DEC-029 승인 동행 점수 연결이 성공하면 4개 권역(HAEUNDAE/SEOMYEON/GWANGALLI/NAMPO, `config/retrieval.json` areaCenters 기준)·WALK 및 area,timeWindow,transport,mobility,companions,excludedCategories를 지원한다. DB/설정/승인 가중치 오류와 지원 권역 중 하나라도 중심 좌표가 없거나 반경 조회가 실패하는 경우는 시작 실패이며 가상 데이터나 빈 DB로 대체하지 않는다. indoorPreference/budget/preferenceTags 및 정보 없음 포함·날씨·코스 수정은 지원하지 않는다. 실제 호출은 세션 응답의 capabilities를 따른다.
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
- includeUnknownAccessibility=true는 세션 capabilities.supportsUnknownAccessibilityInclusion=true일 때만 허용한다. #72 일반 서버는 실제 검색기·동의/조건부 검증 후 사용자 요청으로 이를 활성화했다. 미지원 앱에서는 true PUT이 422이며, 지원 앱에서도 명시적 동의·이동제약 변경 시 초기화 정책을 따른다. 아래 FR-013·FR-014② 항목 참조.
- 권역/이동수단도 capabilities로 검증한다. 구현되지 않은 조건을 지원한다고 표시하지 않는다.
- 이는 최종 SRS Must 요구사항의 삭제가 아니다. 이후 검증을 마친 기능부터 지원 범위를 넓힌다.

동행 보완(DEC-022): 혼자·친구·연인·기타의 영유아 미언급은 false로 처리하며 묻지 않는다. 혼자=1명, 연인=2명이고, 다른 동행 인원을 모르면 companions는 null/UNSET으로 유지하되 인원만을 위한 질문은 하지 않는다. 가족 또는 '아이' 언급에서 영유아 여부가 미확인이면 companions 질문을 한 번 표시한다(지역·시간 우선, 총 최대 2개). 실제 표시된 질문 뒤 다음 채팅에서도 답하지 않으면 false로 처리하고 UNCONFIRMED_CHANGE 경고로 '영유아 동반이면 조건 카드에서 바꿔 주세요.'를 안내한다. 질문 표시 여부와 부분 동행 정보는 세션 내부 상태이며 외부 JSON 필드를 추가하지 않는다. 영유아가 명시되면 인원이 없어도 DEC-020 이동제약 정책은 적용한다.

조건 추출에서 이동제약·제외 카테고리를 추가 언급하면 기존 목록에 합쳐 기존 HARD 제외를 유지한다. 명시적 빈 USER 목록 또는 카드 전체 교체로 목록을 해제할 수 있다. 이동수단 미언급 시 WALK/DEFAULT를 적용하되 기존 값과 미지원·미확인 이동수단 확인 대기는 보존한다.

## 6. 코스 의미·검증

FR-005·006 구현 보완: 카드 PUT에서 transport=null/UNSET이면 지원되는 WALK/DEFAULT를 서버가 적용한다. 미지원 이동수단 확인 대기가 있으면 기본값을 넣어 수락 처리하지 않는다. mobility의 비어 있지 않은 값과 명시적 []는 HARD이며 SOFT 입력은 422 INVALID_PROFILE이다. 예산 미입력은 null/UNSET으로 유지하고 화면에서 '제한 없음(기본 동작)'으로 표시한다. 이는 0원·무료·가격 정보 없음과 다르며 DEFAULT 출처의 null을 만들지 않는다. 체류시간과 부상 초기 설정은 config/defaults.json을 따르고, 체류시간의 source는 내부 계산 결과에서 관리한다. 프로필에 새 체류시간·출처 필드를 추가하지 않는다.
- SUCCESS는 course가 존재, INSUFFICIENT_PLACES는 HTTP 200 + course=null.
- 첫 주 후보가 두 곳 미만이면 후보 부족이다. 시간 안에 못 넣는 장소를 무리하게 채우지 않는다.
- suggestions는 최대 3개. EDIT_PROFILE 클릭은 조건 입력 카드를 열며 자동으로 조건을 변경하지 않는다. 검증용 포함 기능은 별도 type=INCLUDE_UNKNOWN_ACCESSIBILITY로 확인 화면을 열며 클릭만으로 동의·저장하지 않는다. 일반 앱은 포함 제안을 반환하지 않는다.
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
- CONDITIONAL은 명시적으로 지원을 켠 FR-013 검증용 서버에서 동의한 접근성 미확인 항목이 최종 코스에 실제 포함될 때 사용한다. 일반 앱에서는 반환하지 않으며 확인된 HARD 위반을 허용하는 수단이 아니다.
- excludedUnknown.count는 필수 판단 정보 부족으로 제외한 고유 장소 수. fields는 이유 목록이다.
- sourceIds/evidence.sourceId는 응답 sources에 모두 존재해야 한다. sources의 id는 중복하지 않는다.
- license/baseDate=null은 미확인 표현용이다. 실제 공개 전 이용조건을 확인해야 한다. 제공 기준일과 retrievedAt(조회일)을 구분한다.
- 출처는 시스템이 DB에서 붙인다. LLM이 가격·시간·출처를 만들어내지 않는다.
- 추천 이유 생성 실패는 TEMPLATE 설명과 warnings로 처리할 수 있다.

## 7. 오류

FR-009 구현 연결: POST /api/courses는 CourseRequest의 sessionId·profileRevision만 받으며 expectedProfileRevision을 대신 받지 않는다. READY·미확인 항목·요청 제한·revision을 먼저 확인하고 생성 후 최신 revision·만료를 다시 검사한다. 성공과 후보 부족 모두 프로필 revision은 변경하지 않고 세션 TTL만 갱신한다. 실패는 프로필·revision·TTL을 갱신하지 않는다. 조회 장애·이동시간 오류·출처 누락은 후보 부족으로 숨기지 않고 기존 500 INTERNAL_ERROR로 처리하며, AI 장애로 분류하지 않는다. 스케줄러 초안 뒤 최대 3회 교체·재배치를 허용하고 검증을 통과한 2~6곳만 SUCCESS로 반환한다. 두 곳을 확보하지 못하면 INSUFFICIENT_PLACES/course=null이다. 부분 성공 상태·확인된 위반 코스는 추가하지 않는다. FR-013의 명시적 동의와 capability가 함께 있을 때만 접근성 null에 한정해 CONDITIONAL로 반환한다. 최소 템플릿 이유와 suggestions=[]는 #25·#26 연결 전의 범위다. 실제 검색·이동시간 검증 완료와 가상 API 검증은 별개다.
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
| INJURY_RULES | 코스 요청의 정규화된 이동제약에 INJURY 포함, 후보 부족 응답에도 표시 | 구간당 최대 도보시간(현재 설정 10분)과 이동이 힘들면 택시·대중교통 이용을 권하는 안내. 조건 관련 placeIds는 []. 경로 접근성 미확인 경고를 유지하며 자동 대중교통 경로 생성이나 도보 제한 완화를 뜻하지 않음 |
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
- GET /api/facilities
- POST /api/courses/{courseId}/share
- GET /api/share/{shareId}
- 관리자 배치 CLI
adjust는 아래 FR-015 기본 계약으로 별도 정의하며 일반 capability는 비활성 상태다. 장소 교체 후 시각 조정은 합의 전이므로 고정 방문 시간 안 교체만 지원한다.

## 10. 팀원별 시작점
- 김영무: 스키마 기반 요청/응답 모델, 예외 핸들러, 세션 revision 검사.
- 이찬용: Place/Source/Accessibility 형식에 맞춘 실제 DB 변환, 운영시간 내부 정규화.
- 배진호: examples로 mock 연결, 상태별 화면 분기, 지원 범위 표시.
- 김세민: 예시별 검수 시나리오, 실제 데이터·출처 확인, SRS/SDD 변경 기록.
GitHub에 합의 버전을 커밋하고 필드·enum·상태 의미 변경은 프론트·백엔드 공동 PR 검토로 진행한다.

## 구현 상태 기록 (2026-11-11)

이 문서는 형식·의미 계약이며 실행 서버의 지원 선언은 capabilities를 따른다. 기존 PR #13에 조건 chat·카드 정책·내부 확인 대기·코스 진입 guard를 구현했다. #17 모듈을 함께 반영해야 새 처리를 등록하며, 아직 실제 LLM·코스 엔진·프론트는 연결하지 않았다. 기존 JSON 필드·타입·경로의 추가 변경은 없다. 단독/통합 검증과 지원 활성화 계획은 ../docs/ISSUE6_8_IMPLEMENTATION.md를 참고한다.


## FR-012 구현 상태 (2026-11-16, 이슈 #25)

GET /api/places/{placeId}를 기존 PlaceResponse(place/sources/warnings/requestId)로 구현했다. 코스와 공통 변환을 사용하며 기본/접근성 출처는 합집합·중복 제거한다. 구조화 운영시간이 없으면 UNKNOWN, 원문은 description에 보존한다. 가격·접근성 미확인을 무료·이용 가능으로 바꾸지 않는다. 없는 ID는404, 저장소 장애·깨진 출처·유효하지 않은 저장 레코드는500이며 세션·LLM은 사용하지 않는다.

추천 이유는 기존 CourseItem.reason/reasonMethod에 있다. 최종 검증된 장소의 확인된 사실 키1~2개를 모델이 선택하면 시스템이 문장과 숫자를 조립한다. 임의 모델 문장·가격·영업시간·출처는 채택하지 않는다. 사용자 원문·세션·전체 프로필을 보내지 않고 개요는200자로 제한한다. 실패·미확인 출력은 TEMPLATE와 AI_FALLBACK으로 대체하며, 코스의 장소·시간·검증 결과는 바꾸지 않는다. 상세 화면은 코스 항목의 이유와 PlaceResponse를 함께 사용한다. 외부 JSON 필드·enum 변경은 없고 실제 DB·LLM·화면 검증은 후속이다.


## FR-014 ① 구현 상태 (2026-11-17, 이슈 #26)

성공 코스의 suggestions를 최종 적용 프로필에서 생성한다. 값이 null이 아니고 source=DEFAULT이며 capabilities와 기존 카드에서 지원하는 필드만 EDIT_PROFILE로 최대 3개 반환한다. area/transport는 지원 값 목록도 확인한다. 기존 카드 순서로 표시하며 필드별 중복은 없다. id는 edit-default-{field}이고 사용자 값·건강 원문을 문구에 넣지 않는다. USER·UNSET·미지원 항목은 제외하며 현재 실제 자동 기본값은 도보·영유아 동반 시 유모차다. 다른 필드에 새 기본값을 적용하지 않는다.

EDIT_PROFILE 칩 선택은 field에 해당하는 카드를 여는 동작이며 자동 변경·저장·하드 완화가 아니다. 사용자가 USER로 저장한 최신 profileRevision으로 재생성하면 해당 제안이 사라진다. 같은 DEFAULT를 유지하면 제안도 유지하며 최신 응답으로 칩을 교체한다. INSUFFICIENT_PLACES는 suggestions=[]이다. 프로필·revision·코스 내용을 제안 생성으로 변경하지 않는다. 체류시간 제안은 기존 프로필 필드가 없어 이번 범위에서 제외하고, 날씨 제안은 후속이다. FR-014① 자체의 외부 JSON 필드·enum 변경은 없으며 FR-013·014② 확장은 다음 절과 구분한다.

## FR-013·FR-014② 실제 연결 (일반 포함 지원 활성)

이 절은 프론트 리뷰와 사용자 전달 PM 확인을 반영한 서버 계약이다. #72 실제 검색기는 접근성 정보만 없어 제외된 장소를 거리 근거와 함께 별도 후보 풀로 전달한다. 실제 DB 동의/조건부 검증 후 사용자 요청으로 일반 app.main:app 시작 연결에서 supportsUnknownAccessibilityInclusion=true를 공개하고 true PUT을 허용한다. DB·설정·승인 점수 연결 검증이 실패하면 시작하지 않는다. 동의 전 null은 계속 제외하고 실제 포함 시에만 조건부 경고를 반환한다. 프론트 실제 연결·화면 인수와 PR 병합은 별도다.

Suggestion은 type과 field가 결합된 두 분기다. 기존 EDIT_PROFILE은 기존 ProfileField만, INCLUDE_UNKNOWN_ACCESSIBILITY는 field=includeUnknownAccessibility만 허용하며 두 타입을 서로 바꿔 쓰면 검증 실패다. 새 action의 id는 include-unknown-accessibility, label은 '접근성 정보가 없는 장소도 포함해서 다시 만들까요?'다. id는 수락 토큰이 아니며 POST에 전송하지 않는다.

표시 조건: 지원 capability=true, includeUnknownAccessibility=false, 활성 HARD 이동제약이 있고, 다른 후보 하드 검사를 통과하며 필요한 접근성 항목 null 때문에만 제외된 후보가 있을 때. 집계 count나 fields 합집합만으로 자격을 추정하지 않는다. Repository 사실과 거리 증거를 재확인한다. 2026-11-20 사용자 전달 PM 확인 및 프론트 리뷰에 따라, 포함 칩이 있으면 기존 순서의 기본값 칩 최대 2개 다음에 포함 칩 1개를 반환한다(총 3개 이하). INSUFFICIENT_PLACES/course=null에서도 자격이 있으면 포함 칩 1개를 반환하며, 기본값 칩은 반환하지 않는다. 포함 칩이 없으면 성공 응답의 기존 기본값 칩 최대 3개를 유지한다. FR-014① 절의 후보 부족 suggestions=[] 설명은 포함 제안이 없는 경우에 해당한다.

동의 초기화: 카드 전체 PUT·채팅 수정·영유아 동반에 따른 유모차 기본값 추가/제거 모두, 정규화가 끝난 mobility.value를 직전 저장 값과 비교한다. 값 집합이 바뀌면 includeUnknownAccessibility=false로 저장·응답하며 재동의를 받는다. 같은 요청에 true를 함께 보내도 값 변경 시 초기화가 우선한다. 목록 순서·source만 바뀌면 기존 true 동의를 초기화하지 않는다. null(미입력)과 [](명시적 없음)은 구분한다. 초기화 후 반환된 프로필·새 revision으로 별도 PUT에서 명시적으로 재동의한다. 사용자가 false로 저장한 취소는 값 변경이 없어도 유지하며 AI 추출로 동의를 만들지 않는다.

수락 순서: 확인 화면에서 명시적으로 선택 → 최신 저장 프로필의 includeUnknownAccessibility만 true로 바꿔 전체 PUT /api/sessions/{id}/profile(expectedProfileRevision 포함) → READY 응답의 새 profileRevision으로 POST /api/courses. POST body는 기존 sessionId·profileRevision만 사용한다. mobility source·strength·value 등 다른 조건은 보존한다. 저장 전 확인 화면 취소는 요청 없음, PUT 실패·NEEDS_INPUT은 POST 없음. PUT 성공 후 POST 실패 시 저장한 동의·revision은 유지하고 POST만 재시도한다. 화면을 닫는 것만으로 이미 저장된 동의가 취소되었다고 표시하지 않는다. 저장된 동의를 철회하려면 최신 revision으로 false 전체 PUT을 별도로 성공시켜야 한다. 일반 미지원 서버의 PUT true는 422 UNSUPPORTED_CONSTRAINT이고 revision이 증가하지 않는다. 409/410·세션 폐기·TTL·동시성 처리 규칙은 기존과 같다. AI 추출로 동의를 만들지 않는다.

동의 후에도 필요한 항목 false와 주소·운영시간·반경·제외 카테고리·이동시간·시간창 등 다른 위반은 거절한다. 장소 접근성 null을 true로 바꾸거나 mobility를 SOFT/[]로 변경하지 않는다. INJURY의 wheelchair 대리 지표와 구간 도보 상한도 유지한다.

최종 코스에 해당 null이 실제 포함됐으면 validation.status=CONDITIONAL, unverifiedFields에 mobility.wheelchair/stroller를 추가하고 UNKNOWN_ACCESSIBILITY_INCLUDED 경고의 placeIds로 최종 포함 장소를 지정한다. routeAccessibility=UNVERIFIED·가격 미확인·출처는 보존한다. checkedHardConstraints는 검사한 조건의 목록이며 CONDITIONAL의 미확인 항목을 확인 완료로 표시하지 않는다. 다른 항목 때문에 grade=VERIFIED여도 필요한 null과 경고를 숨기지 않는다. flag=true지만 최종 장소가 모두 필요한 접근성 true이면 PASSED로 반환하고 포함 경고를 붙이지 않는다.

FR-013 포함 동의는 별도 adjust를 호출하지 않고 기존 PUT→POST를 사용한다. FR-015 수정 API는 아래 계약을 따른다. 새 action·조건부 예시는 contracts/examples/06-* 및 참고 문서에 있으며 모두 가상 검증용이다. 서버 기능 테스트·계약 검증은 실제 DB·화면 인수와 구분한다.


## FR-018 연결 상태 (이슈 #27 / DEC-029)

일반 서버는 DEC-029 APPROVED/pmApproved=true 설정만 허용한 동행 카테고리 scorer를 코스 생성에 주입한다. 동행 미입력은 0점이며 기존 코드/필드 구조를 유지한다. 하드 동행은 미지원이고 동행 점수가 하드 제약을 완화하지 않는다. 분위기·야경·가성비·인원 적합성 추론은 하지 않는다. 실내 선호 지원은 별도로 닫혀 있다.

2026-11-21: 실제 공유 DB의 CS-01~10 자동 검사에서 하드 위반·미존재 장소 0건을 확인한 뒤 사용자 요청으로 일반 연결을 활성화했다. 검색/검증 반경은 같은 값을 전달하고 기존 외부 JSON·revision·하드 필터는 유지한다. #70 정보 없음 포함 기능과 화면/수동 인수는 별도다. [실행기와 선행 입력](../evaluation/courses/DATABASE_RUN.md).


## FR-015 부분 수정 기본 계약 — #32 (일반 비활성)

POST `/api/courses/{courseId}/adjust`: `{sessionId, expectedProfileRevision, message}`. 현재 세션의 최신 코스만 수정한다. 성공 시 새 courseId를 반환하고 profileRevision은 유지한다. 별도 공개 courseRevision은 없다. 프로필 변경은 저장 코스·후속 질문을 무효화하며 새 생성이 필요하다. 일반 생성과 수정은 저장 직전 프로필/코스 CAS 검사를 수행해 느린 결과의 덮어쓰기를 막는다.

응답은 기존 CourseResponse 자체가 아니라 전체 Course·공통 경고/제안/제외 수를 재사용한 **AdjustmentResponse**다. SUCCESS는 수정된 전체 코스, NEEDS_INPUT·NOT_APPLIED는 변경 없는 기존 코스를 반환한다. changes는 removedItemIds/replacedItems(oldItemId,newItemId)/timeChangedItemIds, questions는 수정 전용 field(adjustment.target/minutes/message/followUp 또는 profile.<ProfileField>)·message다. 첫 수정 성공 뒤 후속 질문이 남을 수 있으므로 SUCCESS에서도 questions를 표시한다. 연장 분을 추측하지 않고 물으며 코스 ID에 묶인 질문 문맥에서 답을 처리한다. 유지된 itemId는 보존하고 표시 order만 다시1부터 매긴다.

REMOVE는 다른 방문 시각을 보존한다. REPLACE는 대상과 다른 방문의 시각·체류시간을 모두 고정하는 합의 범위만 지원한다. EXTEND_STAY는 뒤 장소의 시각만 필요한 만큼 이동한다. 하드 조건·실제 이동·운영시간 재검증 실패는 미적용이며 전체 재생성으로 대체하지 않는다. 후보 기본 체류시간을 적용해 교체 후 일정을 바꾸는 정책은 미합의다.

PROFILE_CHANGE는 카드/조건 채팅 후 재생성으로 안내하고, INCLUDE_UNKNOWN은 #30 명시적 확인→전체 PUT→새 revision POST를 재사용한다. 해석만으로 동의하지 않는다. 기존 동의로 실제 null이 남는 코스는 CONDITIONAL과 장소별 경고를 유지한다. INDOOR 실제 교체는 이번 기본3연산에 포함하지 않는다.

오류는 기존 봉투와 no-store다. COURSE_NOT_FOUND(404)·COURSE_CONFLICT(409)를 추가한다. 기존 INVALID_REQUEST(400/422), REVISION_CONFLICT(409), SESSION_EXPIRED(410), PROFILE_INCOMPLETE/UNSUPPORTED_CONSTRAINT(422), RATE_LIMITED(429, Retry-After), INTERNAL_ERROR(500)를 유지한다. 비활성 상태는 해석 전에422. LLM 재시도 후 단순 삭제만 규칙 처리하며 나머지는200 NEEDS_INPUT이다. 오류는 코스·프로필·TTL 미변경,200은TTL 갱신이다. 응답 유실 시 수정 자동 재전송 금지,409 복구 불가 시 사용자 확인 후 새 생성/새 세션으로 진행한다.

완전한 가상 예시: `examples/07-adjust.*.json`, `error-409-course.response.json`. 일반 capability는false이며 실제 LLM 평가·프론트 연결·활성화는 별도 후속이다. [구현·검증·미합의 기록](../docs/ISSUE32_COURSE_ADJUSTMENT.md).
