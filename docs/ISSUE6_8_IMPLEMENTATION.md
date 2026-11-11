# 이슈 #6·#8 구현 보완 — 2026-11-11

관련: FR-002·004·005·006·018, NFR-002·003·008, AI-REQ-02 / DEC-001·002·007·019~021.

## 변경 결과

- 기존 PR #17: 시간과 무관한 제외 표현·인사말의 부정 오인 수정, DEC-020 유모차 정규화와 상태 전이 테스트.
- 기존 PR #13: AIService → 규칙 파서 → 기존 조건 병합 → 정규화 → 지원 검증 → 503/NEEDS_INPUT/READY → 원자적 저장. 계약의 POST /api/chat을 구현하고 PUT에도 정규화를 적용.
- 기존 PR #11: test_schema*.py 공동 소유자와 공개 전환 후 플랜 문구 보완.
- PR #12 세션 종료 구현은 변경하지 않음. develop/main·PR·작업 브랜치 간 병합 없음. 새 PR 없음.

## 의존성·실행

PR #13은 #17의 AIService·RuleBasedParser·normalize_mobility를 사용한다. 두 작업 브랜치 이력을 합치지 않는다. 검토·향후 병합 순서는 #18 결정 기록 및 #17 모듈을 반영한 뒤 #13이다. 실제 병합은 이번 요청에서 수행하지 않는다.

#13 단독으로는 기존 세션·카드 API가 유지되고 chat은 등록되지 않는다. #17이 함께 있으면 chat을 등록하고 새 카드 정책을 적용한다. Provider는 아직 미설정이며 AIService의 재시도 소진 후 규칙 파서로 처리한다. 실제 모델 호출·API 키·새 환경변수는 추가하지 않았다. 테스트는 가짜 Provider를 주입한다.

## 안전한 상태 전이

- chat의 UNSET은 기존 값을 지우지 않는다. 새 DEFAULT도 기존 값과 미확인 요청을 덮어쓰지 않는다. USER 이동제약 추가는 기존 목록을 보존한다. 기존 HARD를 SOFT로 자동 낮추지 않는다.
- 미지원 transport는 chat에서 미반영하고 나머지 유효 조건만 저장한다. 질문·UNSUPPORTED_TRANSPORT를 유지하며, 명시적 USER 지원 값 선택으로 해소한다. 카드에서는 기존대로 422 전체 미저장.
- 유모차는 USER []·목록 우선, null 초기화 시 DEFAULT/HARD 재적용, 영유아 취소 시 DEFAULT의 STROLLER만 제거. USER 목록에 유모차가 없으면 STROLLER_NOT_APPLIED. 질문 수를 소비하지 않는다.
- 불완전한 동행 힌트는 내부 메모리의 범주값으로 유지한다. 영유아가 명확하면 유모차는 적용하되 동행 종류·인원·영유아 부재를 만들지 않고 companions 확인을 요청한다.
- pending_fields는 표시되지 않은 질문까지 모두 보존한다. 최대 2개 질문에 답해도 숨은 항목은 지우지 않는다. PUT은 표시된 USER 확인 항목 또는 실제 수정한 항목만 해소하며 경고 닫기는 API 저장 동작이 아니다.
- fallback 때 기존 값 포함 지역·시간이 둘 다 없을 때만 503. 실패 시 profile·revision·history·TTL은 그대로다. 409·410·422·429를 503으로 바꾸지 않는다.
- slow AI 반환 후 revision/만료를 재확인하고, commit_profile이 원자적으로 다시 검사한다. raw 메시지를 history·오류·확인 항목에 저장하지 않는다.
- SessionStore.begin_course는 revision·만료·요청 제한과 필수 값·pending을 검사하고 미확인이면 422 PROFILE_INCOMPLETE다. 코스 엔진은 이 진입점을 사용해야 한다. 코스 HTTP API·스케줄러는 아직 구현하지 않았다.

## capabilities 인계 계획

현재 지원 배열은 계속 비어 있다. 이번 변경만으로 HAEUNDAE/WALK 지원을 켜지 않는다. 활성화 계획은 이슈 #21 B에 맞춰 두 단계로 구분한다. #15·#16·#41 실제 데이터/Repository 검증과 #22 후보 검색·항목별 하드 판정이 실제 연결되고 해당 필드 검증을 통과하면 HAEUNDAE/WALK를 켜서 카드·채팅을 실서버에서 검증한다. #23 코스 생성·이동시간·검증기·생성 진입 guard와 end-to-end 검증은 코스 생성 흐름을 여는 별도 조건이다. #23 완료를 카드·채팅 지원 목록 활성화의 추가 선행 조건으로 두지 않는다. 담당자는 API 김영무, 데이터·이동시간 이찬용, 표시·선택 배진호다. 이 조건이 충족되는 PR에서 지원 배열·실제 검증 결과·활성화 시점을 함께 갱신한다. 확정되지 않은 활성화 날짜는 만들지 않는다.

## 인터페이스 재검토 기록 (#8 A)

PR #15 head 07ad02c, #16 head fbcc9a8을 재검토했다. #15 293개, #16 153개 테스트 통과. 기존 중첩 격리·입력 예외·정수/NULL·실패 복구·URL ID 지적은 보완됐다.

코스 호출 담당 관점에서 find_within_radius/get_place/existing_place_ids/get_sources, 거리 m·좌표 도·체류 분, 후보 없음/없는 ID/저장소 실패 구분 및 메모리 대체 구현을 수용한다. 운영시간은 mon~sun, Asia/Seoul HH:mm, 열린 구간 목록, [] 휴무·키 없음 미확인, close 24:00·자정 넘김 시작 요일 기준으로 연결한다. 공휴일·휴게 구간 겹침·실제 영업 판정은 별도다. 이 기록은 코드 인터페이스의 기술 합의이며 PM 정책 승인·GitHub 승인 리뷰·PR 병합을 대신하지 않는다.

## 평가셋 인계 (#8 E / #10 C)

#10 작업 C와 evaluation/README.md를 확인했다. 이번 회귀 사례는 가상 입력만 사용하며 {value, source, strength}, 사전 상태, 기대 질문·경고·실제 HTTP 결과를 비교한다. contracts/policy-cases.json 14개도 scripted extraction을 통해 실제 HTTP 정책으로 검증했다. 이는 한국어 추출 정확도 평가가 아니라 정책 검증이다.

PM 초안의 사례 ID·요구사항·입력·사전 상태·기대/실제 결과·실행일·코드 revision·판정 필드를 유지해 같은 입력을 재사용할 수 있다. backend/tests/test_rule_parser.py와 test_chat_policy.py의 대응 사례를 교차 검토 입력으로 삼는다. PM 담당 30문장·최소 10문장 공동 리뷰는 팀원 확인이 남아 있으며 수행 완료로 표시하지 않는다.

## 실행한 검증

Python 3.12.14 / PYTEST_DISABLE_PLUGIN_AUTOLOAD=1:

- #17 단독: 147 passed.
- #13 단독: 47 passed, 1 skipped (#17 의존 통합 테스트 모듈).
- #13+#17 소스 검토 사본: 188 passed. 기존 정책 사례 14개 HTTP 검사 포함.
- 계약: 5 operations·31 schemas·20 examples·14 synthetic policy cases 및 negative control 통과. 참고 문서 JSON 동기화 통과.
- 공통 기존 Starlette/httpx deprecation 경고 1건. 실제 LLM·부산 데이터·프론트·코스 추천 통합은 미검증.

통합 사본에는 Git 메타데이터가 없으며 두 PR의 소스만 함께 적용했다. 이는 브랜치 또는 GitHub PR 병합이 아니다. 테스트 중 정상 AI 응답의 시간 필드가 strict JSON 검증에서 거절되는 문제를 발견해, RFC3339 문자열 검사 후 datetime으로 변환하도록 보완했다. epoch·naive 시간은 계속 거절한다.

## 2026-11-11 배진호 프론트 리뷰 후속

PR #13 issuecomment-6789513546의 시간만 수정한 PUT 재현을 회귀 테스트로 확인하고 수정했다. transport 값이 같으면 출처·강도 변경 또는 표시된 질문의 USER 재전송만으로 확인 대기를 지우지 않는다. 같은 도보 재선택은 사용자 클릭에만 최신 revision으로 chat `도보로 이동할게요`를 보낸다. 다른 지원 값의 실제 USER 카드 선택은 대기를 해소한다. 외부 필드를 추가하지 않았다.

현재 일반 서버는 지원 배열이 비어 있어 활성 조건을 422로 거절한다. #13+#17 의존 소스를 함께 적용한 격리 검토 사본의 가상 capabilities로 카드·채팅 정책 검증은 지금 가능하다. 이 설정은 실제 지원 선언이 아니다. 실서버에서 조건 입력을 저장하는 시점은 #22 실제 연결과 필드 검증 후의 #21 활성화 PR이다. 날짜는 그 선행 작업 완료 전 확정하지 않는다.

최초 활성화 대상은 supportedAreas=[HAEUNDAE], supportedTransports=[WALK]이며 supportedProfileFields는 area·timeWindow·transport·mobility·companions·excludedCategories를 대상으로 각 필드 검증을 통과한 것만 연다. mobility는 #22의 휠체어·유모차·부상 판정/UNKNOWN 미통과 검증이 선행한다. indoorPreference·preferenceTags·budget은 처리·지원 검증 전에는 열지 않는다. 기존 supportsUnknownAccessibilityInclusion·supportsCourseAdjustment·supportsWeather는 false를 유지한다. 실제 목록과 검증 결과는 #21 활성화 변경에서 확정해 공유한다. READY는 조건 확인 완료이며 코스 생성 지원 완료를 뜻하지 않는다.

수정 후 #13+#17 전체197개 테스트 통과(기존188개+프론트 회귀9개), 기존 경고1건. 이후 추가한 정책 사례의 HTTP 검증은 최종 실행 결과에 별도 기록한다. PR #12의 접근 로그 지적은 해당 브랜치의 deployment/SESSION_LOG_PRIVACY.md에서 배포 전 검수와 로컬 검증을 구분한다. 브랜치/PR 병합과 실제 프론트 연결은 하지 않았다.

최종 재검증: 정책 사례를15개로 늘린 후 #13+#17 소스 검토 사본198 passed, 계약5 operations·31 schemas·20 examples·15 policy cases/negative control 및 참고 문서 동기화 통과. #13 단독 결과는 별도 아래 최종 기록을 따른다.

#13 단독 최종 결과:47 passed, #17 의존 통합 테스트 모듈1개 skip. 기존 Starlette/httpx 경고1건. 실제 프론트·모델·배포 검증은 별도다.
