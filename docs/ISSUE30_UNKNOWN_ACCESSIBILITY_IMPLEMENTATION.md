# #30·#31② 서버 사전 구현 — FR-013·014②

2026-11-19. 사용자 요청: 카톡 초안에서 구현 가능한 서버 부분을 먼저 진행하고 프론트 추가 합의 항목은 남긴다. develop `700dcb0`에서 별도 `feature/FR-013-unknown-accessibility` 브랜치로 작업했다. `.env`·키를 읽거나 실 데이터/LLM API를 호출하지 않았다. DECISIONS.md는 변경하지 않았다. 계약 합의·일반 활성화·실데이터 인수·병합과 사전 구현 PR 게시는 구분한다.

## 구현한 부분

- Suggestion의 새 타입 `INCLUDE_UNKNOWN_ACCESSIBILITY`, field=`includeUnknownAccessibility`, 고정 id=`include-unknown-accessibility`. 기존 EDIT_PROFILE 필드와 서로 바꿔 쓸 수 없다. 최대 3개 외부 배열 구조는 유지.
- 명시적 capability가 있는 검증용 서버에서 기존 프로필 전체 PUT으로 boolean 저장 가능. mobility value/source/HARD는 유지. READY 응답 revision으로 기존 POST courses 재생성. 별도 adjust API나 chipId 요청은 추가하지 않음.
- 동의 없이 필요한 접근성 null은 여전히 제외. 동의 후 null만 허용하고 false·다른 필수 조건 위반은 계속 제외. 일반 모드에서 원래 허용하던 null을 새로 ‘동의 포함’으로 간주하지 않음.
- 독립 검증 결과는 accepted(확인된 위반 없음)와 passed(동의한 미확인도 없음)를 구분. 실제 null이 포함되면 CONDITIONAL·mobility.wheelchair/stroller unverifiedFields·UNKNOWN_ACCESSIBILITY_INCLUDED(placeIds) 경고. grade·null·routeAccessibility=UNVERIFIED·가격 UNKNOWN·출처 유지.
- 조회·출처 조립 중 사실이 달라지면 최종 독립 검증·기존 교체/재배치로 재확인. 제안 대상 자격도 응답 직전에 Repository에서 재확인.
- PUT 성공 후 POST 실패 시 저장한 flag·revision은 유지하며 POST만 재시도. 기존 409/410·TTL·세션 종료·revision guard 재사용.
- 기존 OpenAPI·API_CONTRACT·참고 스키마 문서·SRS/SDD 구현 추적과 가상 예시 3개를 함께 갱신. 목표 기능의 완전한 활성화·인수 완료로 표시하지 않음.

## 일반 서비스는 아직 비활성

일반 create_app()은 `supportsUnknownAccessibilityInclusion=false`이며 PUT true를 422로 거절한다. ProfileSupport에 `unknown_accessibility_verified=False`를 추가했다. 검증용 root에서 검색 연결·mobility 검증·해당 검증 증거를 모두 명시해야 지원을 켤 수 있다. 기본값·환경변수로 자동 켜지지 않는다. 실제 DB·화면·최종 정책 합의 전에는 일반 root에서 설정하지 않는다.

이 구현은 단순히 capabilities 값만 true로 만드는 작업이 아니다. 검색기 포트 생산자·서버·독립 Validator·표시·동의 흐름까지 통합 검증해야 일반 활성화할 수 있다. 프론트 #68은 기존 EDIT_PROFILE 전용이며 별도 분기와 CONDITIONAL 표시가 필요하다.

## 찬용과 연결할 #22 내부 포트

현재 develop에는 #65 PlaceRetriever가 아직 병합되지 않았다. #65 브랜치와 데이터 담당 구현을 임의로 복사하거나 수정하지 않았다.

`RetrievalResult`의 기존 세 필드는 유지하고 선택 필드를 추가했다.

```python
unknown_accessibility_candidates: tuple[PlaceCandidate, ...] = ()
```

- 기존 retriever는 수정 없이 동작하며 새 필드 기본값은 빈 tuple이다.
- 실제 #22 adapter는 기존 확정 제외(사후면세점 ID·주소·운영시간·반경·카테고리 등)를 적용한 뒤, 필요한 접근성 null 때문에만 제외된 후보와 검증한 거리를 별도 풀로 전달해야 한다. 제외 코드/ID 규칙은 검색기가 계속 소유한다.
- 거리 증거가 없는 excluded_unknown_ids/count/fields만으로 장소를 재도입하지 않는다. 이 집계는 기존 표시용으로 보존한다.
- 서버는 별도 풀과 ordinary 후보의 Repository 사실을 strict 기준으로 재검사해 접근성 null 외의 위반이 있으면 포함하지 않는다. 각 풀에서 설정 max_candidates까지만 검사하며 최종 배치 입력은 합쳐서 기존 후보 상한을 넘지 않는다.
- 기존 ordinary 후보가 우선이며 후보 풀을 확장해도 코스가 반드시 늘어난다고 보장하지 않는다. 과다 후보에는 CANDIDATE_LIMIT 안내.
- 실제 검색기에서 이 새 필드를 채우는 연결과 실제 DB 검증은 아직 남아 있다. 지금은 가상 포트로 서버 동작을 검증한다.

## 진호와 추가 합의할 것 — 이번에 확정하지 않음

| 항목 | 현재 보존한 동작 | 카톡에서 제안한 변경 |
|---|---|---|
| 후보 부족 화면 | INSUFFICIENT_PLACES는 suggestions=[] | 포함 칩 1개 표시 |
| 칩 3개 배분 | 기존 기본값 칩 유지, 빈 슬롯에만 새 칩 추가 | 기본값 최대 2개 + 포함 칩 1개 예약 |
| 이동제약 변경 후 동의 | 기존 boolean 저장 규칙 유지, 자동 초기화 없음 | 변경 시 flag=false 및 재동의 |

일반 활성화 전에 합의 결과를 계약·서버·UI·테스트에 반영해야 한다. 이 구현의 테스트는 미합의 정책을 채택하는 대신 기존 동작 보존을 확인한다. 이동제약 자동 초기화를 아직 하지 않는다는 사실을 일반 서비스 배포 허가로 해석하지 않는다. 지원 서버는 합의·통합 검증 전 가상 테스트용이다.

날씨(#31③)·고정 일정·자연어 수정은 이번 범위에 없다. 11/25 판단 전 착수하지 않는다.

## 재현과 검증 범위

저장소 루트의 Python 3.12 환경에서:

```text
python -m pytest -q
python contracts/validate_contract.py
python contracts/validate_source_sync.py
git diff --check
```

신규 가상 검사는 #30 제안 자격·동의·네 이동 모드/복수 제약·null/false·타 하드 조건·조건부 결과·grade 표시·출처 조회 경합·새 revision·POST 재시도·명시적 취소 저장·세션 종료·일반 capability 비활성을 다룬다. 실제 장소·실모델·화면 인수와 응답시간 인수는 수행하지 않는다.

최종 코드 검증 (2026-11-19): 전체 pytest **1220 passed**, 기존 Starlette/httpx 경고 1건. 계약 검사 **6 operations·31 schemas·23 JSON examples·15 synthetic policy cases** 통과. 참고 문서 JSON 동기화와 `git diff --check` 통과. 원격 CI는 아직 실행하지 않았고, 실제 DB·프론트 통합 인수 결과가 아니다.

가상 계약 예시:
- `contracts/examples/06-course.unknown-proposal.response.json`: 성공 코스 뒤 포함 제안.
- `contracts/examples/06-profile.include-unknown.request.json`: 명시적 true 전체 PUT 예시.
- `contracts/examples/06-course.conditional.response.json`: 해당 null 유지·CONDITIONAL·장소별 경고.

## 다음 작업

- [ ] 진호·PM과 세 미합의 정책 및 새 type/field 합의.
- [ ] 찬용과 별도 후보 풀·거리·확정 제외 규칙 보존 연결 합의, #65 develop 반영 후 adapter 구현.
- [ ] 진호: 확인/취소·이전 칩 비활성·PUT/POST·경고 표시를 가상 응답으로 연결.
- [ ] 실제 DB의 일반·휠체어·유모차·부상·복수 제약에서 결과·부족·null 경고·false 제외 검증.
- [ ] 통합 검증·정책 반영 후에만 일반 지원 활성화 및 새 세션 capabilities 확인.
