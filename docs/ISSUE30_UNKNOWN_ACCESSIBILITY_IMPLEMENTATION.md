# #30·#31② 서버 사전 구현 — FR-013·014②

> 최신 상태: #72 실제 검색기 연결과 검증용 실제 DB 동의 흐름을 완료했다. 일반 서버의 포함 기능은 계속 비활성이며 화면 인수·활성화·PR 병합은 별도다. 아래 과거 선행 대기 기록은 당시 상태다.

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

일반 create_app()은 `supportsUnknownAccessibilityInclusion=false`이며 PUT true를 422로 거절한다. ProfileSupport에 `unknown_accessibility_verified=False`를 추가했다. 검증용 root에서 검색 연결·mobility 검증·해당 검증 증거를 모두 명시해야 지원을 켤 수 있다. 기본값·환경변수로 자동 켜지지 않는다. 실제 DB·화면 통합 검증 전에는 일반 root에서 설정하지 않는다.

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

## 프론트 리뷰·PM 확인 반영 (2026-11-20)

진호의 PR #70 리뷰와 사용자가 전달한 PM 확인에 따라 다음 세 정책을 계약·서버·테스트에 반영했다. DECISIONS.md는 변경하지 않았다.

| 항목 | 확인된 동작 |
|---|---|
| 후보 부족 화면 | 포함 가능한 미확인 접근성 후보가 있으면 INSUFFICIENT_PLACES에서도 포함 칩 1개 반환. 기본값 칩은 반환하지 않음 |
| 칩 3개 배분 | 포함 칩이 있으면 기존 순서의 기본값 최대 2개 + 포함 칩 1개. 포함 칩이 없으면 성공 응답의 기존 기본값 최대 3개 유지 |
| 이동제약 변경 후 동의 | 카드·채팅·영유아 유모차 기본값 추가/제거 정규화 후 실제 값 변경 시 false 초기화·재동의. 같은 요청의 true보다 초기화 우선 |

이동제약은 순서 없는 값 집합으로 비교하되 null(미입력)과 [](명시적 없음)은 구분한다. 순서나 source만 바뀌면 동의를 초기화하지 않는다. 초기화 후 반환된 최종 프로필·revision으로 별도 전체 PUT에서 재동의한다. 저장 전 확인 화면 취소는 요청하지 않는다. PUT 성공 후 POST 실패는 저장된 동의·revision을 유지하며 POST만 재시도하고, 화면 닫기를 동의 철회로 표시하지 않는다. 저장된 동의 철회는 false 전체 PUT 성공으로 처리한다.

일반 서비스는 계속 비활성이며 실제 검색·UI 통합 검증 전 활성화하지 않는다. 프론트 경고는 UNKNOWN_ACCESSIBILITY_INCLUDED.placeIds를 타임라인 place.id에 연결한다. 별도 정책을 추가하거나 자연어 수정 기능 #32 전체를 구현한 것은 아니며, 기존 조건 채팅 경로에도 동일한 초기화 규칙을 적용한다.

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

리뷰 정책 반영 검증 (2026-11-20): 전체 pytest **1240 passed, 1 warning**. 최종 코드 정리 후 관련 테스트 **47 passed, 1 warning**도 확인했다. 후보 부족 응답의 포함 칩 유무·계약 형식, 기본값 3개와 포함 칩 자리 배분, 카드·채팅·추출기 없는 카드 경로, 유모차 기본값 추가/제거, 순서/source 변경 보존, null/[] 구분, 별도 PUT 재동의를 검증했다. 계약·참고 문서 동기화·diff 검사 통과. 실제 DB·외부 모델 호출·화면 인수는 수행하지 않았다.

가상 계약 예시:
- `contracts/examples/06-course.unknown-proposal.response.json`: 성공 코스 뒤 포함 제안.
- `contracts/examples/06-profile.include-unknown.request.json`: 명시적 true 전체 PUT 예시.
- `contracts/examples/06-course.conditional.response.json`: 해당 null 유지·CONDITIONAL·장소별 경고.

## 다음 작업

- [x] 진호의 새 type/field·API 순서 리뷰 확인 및 사용자 전달 PM 확인에 따라 세 정책 반영(11/20).
- [ ] 찬용과 별도 후보 풀·거리·확정 제외 규칙 보존 연결 합의, #65 develop 반영 후 adapter 구현.
- [ ] 진호: 확인/취소·이전 칩 비활성·PUT/POST·경고 표시를 가상 응답으로 연결.
- [ ] 실제 DB의 일반·휠체어·유모차·부상·복수 제약에서 결과·부족·null 경고·false 제외 검증.
- [ ] 통합 검증·정책 반영 후에만 일반 지원 활성화 및 새 세션 capabilities 확인.

## #70 통합 시 구현 기록 이관 (2026-11-21)

#72 통합 과정에서 SRS·SDD의 구현 상태 기록을 이 문서로 이관했다. 아래는 11/19~20 당시 #70 단독 상태이며, 현재 #72의 일반 코스 활성화와 포함 기능 비활성 상태는 뒤의 최신 연결 기록을 따른다. SRS 요구사항 문구는 바꾸지 않고 SDD에는 기존 PUT→POST API 설계 설명만 유지한다.

| FR-013 | 정보 없음 장소 재생성 제안 | 이동제약 모드에서 '정보 없음'으로 제외된 장소가 있으면, 시스템은 코스 표시 후 "정보가 없는 장소도 포함해서 다시 만들어드릴까요?"를 제안해야 하며, 수락 시 해당 장소에 경고를 표시하여 코스를 재생성해야 한다. | Must | Test | 서버 사전 구현·가상 검증, 일반 활성화 전. [범위·확인된 정책](ISSUE30_UNKNOWN_ACCESSIBILITY_IMPLEMENTATION.md) |

### FR-013·FR-014② 서버 사전 구현 (2026-11-19)

새 Suggestion 타입 INCLUDE_UNKNOWN_ACCESSIBILITY는 명시적 확인 화면용이며 프로필을 자동 변경하지 않는다. 지원을 켠 검증용 서버에서 전체 PUT으로 includeUnknownAccessibility를 저장하고 반환된 revision으로 기존 POST courses를 호출한다. 검색기의 별도 미확인 접근성 후보 풀은 거리·Repository 사실로 재검사하며 null만 명시적 동의 시 허용한다. 독립 Validator는 미확인을 별도 기록해 PASSED 대신 CONDITIONAL로 반환하고 최종 포함 장소 ID 경고를 생성한다. false·다른 하드 위반·시간/부상 규칙은 유지한다. 11/20 프론트 리뷰와 사용자 전달 PM 확인에 따라 후보 부족 포함 칩·기본값 2개+포함 1개 배분·정규화 후 실제 이동제약 값 변경 시 동의 초기화를 반영했다. 카드·채팅·영유아 기본값 경로에 공통 적용하며 순서/source만 바뀌면 동의를 유지한다. 일반 앱은 계속 비활성이며 #22 실제 검색기 포트·UI 연결 및 통합 인수는 후속이다. [구현 범위와 연결 계약](ISSUE30_UNKNOWN_ACCESSIBILITY_IMPLEMENTATION.md).

## #72 실제 검색기 연결·동의 후 실제 DB 검증 (2026-11-21)

- 사용자 요청으로 #70 `80d625e` 기능을 #72 작업 브랜치에 통합하고 PlaceRetriever가 `unknown_accessibility_candidates`를 채우도록 연결했다. 코드 `2a91c130915cc797ad63e3dc72044a4283f6b636`. GitHub PR #70/#72의 develop 병합은 수행하지 않았다.
- 실제 검색기는 사후면세점·권역/반경·제외 카테고리·주소·운영시간/체류 가능 구간·접근성 false·실내 HARD 등 모든 확정 제외와 다른 미확인을 먼저 유지한다. 필요한 접근성 필드 null만 남은 후보를 실제 거리와 함께 별도 풀에 담는다. 일반 후보와 별도 거리·ID 정렬 후 각 max_candidates(기본 20)까지 전달하고 최종 배치 입력은 기존 합산 상한을 유지한다.
- 일반 서버의 기본 코스 연결은 유지하되 **포함 기능은 비활성**이다. `app.main:app`의 supportsUnknownAccessibilityInclusion=false 및 true PUT 422를 회귀 테스트에서 확인했다. 격리된 검증용 앱에서만 명시적 검증 증거를 주입한다. 일반 활성화 스위치·새 환경변수·API는 추가하지 않았다.
- 새 회귀 31 passed: 필요한 null만 풀에 전달, 확정 제외/다른 정보 누락 제외, 거리·정렬·상한·일반 후보 분리, 실제 검색기/계산기를 사용한 가상 Repository HTTP 동의/초기화, 조건부 응답 음성 대조. 전체 공유 DB 포함 **1510 passed, 1 warning**, 계약 6 operations·31 schemas·23 examples·15 정책 사례·문서 JSON 동기화·diff 검사 PASS.
- 독립 응답 감사기는 별도 opt-in 인수로 명시적 동의가 있을 때만 접근성 null을 허용한다. false는 항상 거절하고 null→true 변조, PASSED 오표시, 누락/잘못된 장소별 경고·미확인 필드, 다른 하드 미확인을 거절한다. 기존 엄격 감사 기본값은 유지한다.
- 실제 DB·실제 COMP-06·승인 scorer로 4개 이동제약(휠체어·유모차·부상·휠체어+유모차) × 3시간창 **12개 조합 검사 통과**. 7개는 동의 후 실제 null 장소를 포함한 CONDITIONAL, 1개는 기존 확인된 장소만 포함한 PASSED, 4개는 시간 부족으로 동의 후에도 INSUFFICIENT_PLACES였다. 동의가 성공 코스를 보장하지 않는다는 정책을 유지했다.
- 06~08시 4개 모드 모두 동의 전 후보 부족 → 동의 후 CONDITIONAL을 확인했다. 13~14:30 4개는 후보 부족이 유지되며 동의 전 포함 칩을 반환했다. 각 요청에서 PUT → 새 revision POST, POST만 재시도, 이동제약 값 변경 시 동의 false 초기화, 복수 제약의 순서 변경 시 동의 유지를 확인했다. 표의 포함 수는 실제 최종 코스에 들어간 null 장소 수다.
- 독립 감사 기준 하드 위반·미존재 장소 **0건**, 사후면세점/주소/운영시간/거리/가격 UNKNOWN·출처·부상 10분 규칙 유지, DB SHA-256 `c2b178beb1e2b136c5fba07b33646598fed9da48e73b6443641d8ead1193ec75` 실행 전후 동일. 원본 DB·평가셋은 수정하지 않았다.

| 이동제약 | 시간창 | 별도 풀 | 동의 전 | 동의 후 / 검증 | null 포함 수 |
|---|---|---:|---|---|---:|
| WHEELCHAIR | 13:00-18:00 | 20 | SUCCESS | SUCCESS / CONDITIONAL | 4 |
| WHEELCHAIR | 13:00-14:30 | 20 | INSUFFICIENT_PLACES | INSUFFICIENT_PLACES / — | 0 |
| WHEELCHAIR | 06:00-08:00 | 8 | INSUFFICIENT_PLACES | SUCCESS / CONDITIONAL | 2 |
| STROLLER | 13:00-18:00 | 20 | SUCCESS | SUCCESS / CONDITIONAL | 4 |
| STROLLER | 13:00-14:30 | 20 | INSUFFICIENT_PLACES | INSUFFICIENT_PLACES / — | 0 |
| STROLLER | 06:00-08:00 | 8 | INSUFFICIENT_PLACES | SUCCESS / CONDITIONAL | 2 |
| INJURY | 13:00-18:00 | 20 | SUCCESS | SUCCESS / PASSED | 0 |
| INJURY | 13:00-14:30 | 20 | INSUFFICIENT_PLACES | INSUFFICIENT_PLACES / — | 0 |
| INJURY | 06:00-08:00 | 8 | INSUFFICIENT_PLACES | SUCCESS / CONDITIONAL | 2 |
| WHEELCHAIR+STROLLER | 13:00-18:00 | 20 | SUCCESS | SUCCESS / CONDITIONAL | 4 |
| WHEELCHAIR+STROLLER | 13:00-14:30 | 20 | INSUFFICIENT_PLACES | INSUFFICIENT_PLACES / — | 0 |
| WHEELCHAIR+STROLLER | 06:00-08:00 | 8 | INSUFFICIENT_PLACES | SUCCESS / CONDITIONAL | 2 |

- 보고서 `evaluation/courses/results/unknown-inclusion-real-2026-11-21.json`, `testOnlyApp=true`, `ordinaryInclusionEnabled=false`, 실행일 `2026-11-21T13:07:05.483009+09:00`. 보고서의 실행 커밋과 workingTreeModified를 그대로 기록했다. 당시 결과 저장 전 미추적 공유 txt가 있었다.
- 통합 뒤 일반 서버의 기존 CS-01~10도 재실행해 **9개 자동 통과·실내 미지원 1개 제외**, 위반/미존재 0건을 유지했다. `runtime-real-2026-11-21.json`을 갱신했다.
- SRS의 구현 상태 메모·SDD 구현 기록은 이 문서로 이관했고 SDD에는 기존 PUT→POST API 설계 관계만 남겼다. DECISIONS.md는 수정하지 않았다.
- 프론트 실제 연결·PC/모바일·지도·화면 경고·수동/전체 인수와 **일반 포함 기능 활성화는 미완료**다. 모델/데이터 API 호출·.env/키 읽기·DB 커밋·유료 전환·PR 병합은 하지 않았다. 일반 포함 비활성 때문에 프론트에 실제 연결 활성화 안내를 보내지 않는다.

재현(설치 완료 후 저장소 루트):

```powershell
$env:BUSANFIT_DB_PATH = (Resolve-Path data/share/haeundae_sample_v1.sqlite3).Path
.venv/Scripts/python.exe evaluation/courses/unknown_inclusion.py --expected-db-sha256 c2b178beb1e2b136c5fba07b33646598fed9da48e73b6443641d8ead1193ec75 --output evaluation/courses/results/unknown-inclusion-local.json
```
