# DB 기반 코스 평가 실행 준비 — FR-009 / AI-REQ-01·05

2026-11-21. 실제 공유 DB 수령·SHA 확인 및 #75 COMP-06 연결 후 CS-01~10 자동 평가를 수행했다. 결과와 남은 수동 확인은 아래 최신 기록과 `docs/ISSUE23_COURSES_IMPLEMENTATION.md`를 따른다. 아래 이전 대기·가상 기록은 당시 상태다. 서버 활성화·실제 데이터 인수·병합 완료가 아니다. 기존 `run.py --output ...`의 가상 4개 모드 실행은 유지한다.

## 선행 입력

- PR #65의 `app.retrieval`과 `config/retrieval.json`·사후면세점 제외 파일은 최신 develop `aa1c715` 반영으로 이 브랜치에 포함됐다. 검색기를 별도 복제하거나 임시 경로로 주입하지 않는다. 검색기 의존성 누락 오류는 import 장애 주입으로 계속 검사한다.
- PR #53의 `evaluation/courses/cases.json`(CS-01~10). 이 브랜치에서 평가셋의 기대 결과를 바꾸거나 복제하지 않는다. `--cases`로 별도 파일 경로도 지정할 수 있다. 초안의 방문 날짜를 실행일로 자동 변경하지 않는다.
- 공유 DB 파일 및 SHA-256. 빈 DB를 자동 생성하지 않는다. 연결은 읽기 전용이고 조회마다 별도 연결을 열어 worker thread 간 연결을 공유하지 않는다.
- 찬용 담당 COMP-06: `TravelTimeProvider.estimate(origin, destination, *, injury)`가 `TravelEstimate(minutes)` 또는 계산 불가 시 None을 반환한다. 오류는 예외로 전달한다. 계산식·일반/부상 속도·반올림·보정은 찬용과 합의할 후속이다. 이번 변경은 계산기를 구현하지 않으며 FakeTravel로 자동 대체하지 않는다.

## 연결 준비

`app.application.course_connection.prepare_course_connection(db_path, travel_provider=...)`는 Repository·검색기·CourseService를 만들어 반환한다. FastAPI 앱 생성·실행·일반 capabilities 활성화는 하지 않는다.

- 기본 설정은 #65 로더로 읽는다. 필수 제외 설정 누락을 빈 목록으로 바꾸지 않는다.
- 검색의 `BUSANFIT_WALK_RADIUS_M` 값을 CourseSettings와 Scheduler·Validator에 함께 전달한다. 일반 CourseSettings 기본값은 그대로 유지한다. 평가셋 CS-01~10의 공식 반경은 1500m이며 다른 반경 시험은 별도 가상 검증이다.
- 공식 DB 평가기는 실행 전에 검색·검증 반경이 모두 1500m인지, 중심이 DEC-023의 해운대해수욕장(35.159084, 129.160279)인지 검사한다. 다른 반경·중심이면 ValueError/CLI 종료 코드 2로 거절하고 사례 PASS나 결과 파일을 생성하지 않는다. synthetic=True인 평가 호출에도 동일하게 적용한다. 다른 반경의 연결 시험은 서비스 단위에서 별도로 검증하며 공식 CS 결과로 기록하지 않는다.
- DEC-029의 APPROVED/true 설정만 허용한 scorer를 주입한다. 기존 가상 제안 검토 로더는 PROPOSAL/false도 계속 지원한다. 일반 서버 점수 함수는 바꾸지 않는다.
- #70의 미확인 접근성 후보 풀·동의·CONDITIONAL 및 일반 활성화는 이번 연결 준비와 별도다. 이 브랜치는 #70 코드를 포함하지 않는다.

## 실행 방법

기존 가상 검증(외부 호출 없음):

```text
.venv/Scripts/python.exe evaluation/courses/run.py --mode synthetic --output evaluation/courses/results/synthetic-local.json
```

DB 모드는 위 선행 입력이 모두 준비된 뒤에 사용한다. `--travel-provider`는 **찬용과 합의한 구현의 `모듈:무인자팩토리`**를 받아 실제 포트 객체를 만든다. 이 브랜치에는 #75의 실제 구현 `app.travel.walking:create_travel_provider`가 반영됐다. 가상 테스트 팩토리를 실제 보고서에 쓰지 않는다.

```text
# PowerShell: 키/.env는 필요 없으며 읽지 않는다.
$env:BUSANFIT_DB_PATH = '<공유 DB 절대 경로>'
.venv/Scripts/python.exe evaluation/courses/run.py --mode real --cases evaluation/courses/cases.json --travel-provider app.travel.walking:create_travel_provider --expected-db-sha256 '<공유 파일 SHA-256>' --output evaluation/courses/results/real-2026-11-21.json
```

실행기는 서버 포트를 열지 않고 TestClient에서 세션 생성 → 전체 PUT → READY의 새 revision POST → 세션 삭제를 수행한다. 추출·이유 생성을 위해 외부 AI를 호출하지 않는다. capabilities는 이 평가용 앱 내부에서만 해운대·도보 및 검증 필드를 사용하고 일반 `app.main:app`은 그대로 닫혀 있다. 실내 HARD 등 requiresSupport 미지원 사례는 EXCLUDED로 기록하고 실행·성능 분모에서 제외한다.

## 결과 해석

- 실행일(KST), Git 커밋·작업 폴더 수정 여부, DB·평가셋 SHA-256, 가중치 버전, 반경, 계산기 클래스, 사례별 POST 응답시간을 기록한다.
- 평가 중심 좌표도 보고서 evaluationCenter에 기록하며 독립 감사는 실행 설정과 별개인 공식 1500m 기준을 사용한다.
- 성공 코스는 기존 독립 감사기로 DB 실존·시간·운영시간·거리·접근성·가격·출처·이동시간·부상 규칙을 검사한다. 사후면세점 제외도 확인한다. 예상 savedProfile도 비교한다.
- SUCCESS_OR_INSUFFICIENT에서만 정상적인 INSUFFICIENT_PLACES를 통과시킨다. HTTP 오류·프로필 저장 실패·감사 실패를 후보 부족이나 위반 0건으로 바꾸지 않는다.
- 성능은 실행 사례 중 POST가 15초 이내인 비율 90% 이상을 계산한다. 오류로 POST를 수행하지 못한 실행 사례도 분모에서 빠지지 않는다. CLI는 자동 검사 또는 성능 기준 미달 시 종료 코드 1, 선행 입력 실패 시 2다.
- DB 해시가 실행 전후 달라지면 결과를 저장하지 않는다. 세션 ID·프로필·전체 응답·키·예외 원문은 보고서에 저장하지 않는다. 입력 cases의 result는 수정하지 않는다.
- `syntheticOnly=true`인 테스트 결과는 가상 검증이다. DB 모드도 자동 실행만으로 `realDataVerified`·`realTravelVerified`·`acceptanceComplete`를 true로 만들지 않는다. 공유 DB SHA 확인·계산기 합의·PC/모바일·수동 extraChecks·전체 수용 판단은 별도다. `manualChecksPending`은 자동 검사 완료와 구분한다.

## 이전 대기 기록 (11/20)

- #65 검색기는 develop 반영 완료. #53 평가셋 통합 및 찬용 계산기 구현/계약 확인은 후속이다.
- 공유 DB 수령·SHA 확인 후 CS-01~10 실제 실행.
- 실제 데이터·이동시간·성능·PC/모바일 검증과 활성화 승인. 이번 작업에서 활성화·병합하지 않는다.

## 수행한 검사 (2026-11-20)

- 작업 기준: develop `af0b86f`. 전체 `pytest -q`: **1239 passed, 5 skipped, 1 warning**. skip에는 아직 없는 #65 의존 결합 검사가 포함된다. 경고는 기존 Starlette/httpx 경고다.
- 별도 임시 폴더에서 #65 `753eafd`와 이 연결부를 조합해 관련 테스트: **88 passed, 1 skipped, 1 warning**. 이때 skip 1개는 “#65 없음” 오류 검사이며, 검색기가 실제로 있으므로 제외했다. 실제 브랜치·PR을 병합한 결과가 아니다.
- #53 `5a579ea`의 CS-01~10 입력을 가상 SQLite·명시적 FakeTravel로 실행: **9개 자동 검사 통과, 실내 미지원 1개 EXCLUDED**. `syntheticOnly=true`, 실제 데이터/이동시간 인수 값은 false다. 평가셋 result는 수정하지 않았다.
- 기존 가상 모드 40회: 위반 0건, 15초 기준 충족(가상 성능만). 계약 6 operations·31 schemas·20 examples·15 정책 사례 및 참고 문서 JSON 동기화 통과. `git diff --check` 통과.
- `.env`·실제 키 파일·실제 DB·데이터/모델 API는 사용하지 않았다. 일반 서버 및 #70 지원을 활성화하지 않았고 병합·배포하지 않았다.

### #53 대조 후 공식 범위 회귀 수정 (2026-11-20)

- 공식 평가의 반경·중심 확인과 고정 1500m 독립 감사를 추가했다. 조회·검증 반경 불일치 및 중심 변경은 사례 실행 전에 거절한다. #65 의존성 검사는 README 디렉터리가 아니라 실제 retriever 모듈 존재 여부를 확인하도록 보완했다.
- 최신 전체 pytest: **1244 passed, 4 skipped, 1 warning**. 별도 #65 결합 관련 검사: **92 passed, 1 skipped, 1 warning**.
- 약 1668m 장소·2000m 연결 설정이 공식 평가에서 오통과했던 원래 음성 대조를 다시 실행해, 이제 1500m 불일치로 거절됨을 확인했다.
- 승인된 중심·1500m에서 #53 원본 CS-01~10 가상 실행은 **9개 자동 검사 통과·실내 미지원 1개 제외**를 유지했다. 실제 데이터 인수가 아니며 입력 result는 변경하지 않았다.
- 계약·참고 문서 동기화·diff 검사 PASS. DB·계산기 대기, 일반 비활성·미병합 상태는 유지한다.

### 최신 develop 반영 및 #65 연결 확인 (2026-11-20)

- 사용자 요청으로 develop `aa1c715`를 #72 작업 브랜치에 충돌 없이 반영했다. 이는 #72 PR을 develop에 병합하거나 일반 서비스를 활성화하는 작업이 아니다.
- 이 브랜치의 실제 PlaceRetriever·기본 retrieval.json·사후면세점 제외 ID 112개·ConnectionPerCallRepository를 사용하고, SQLite 행과 이동시간만 명시적 가상 fixture/FakeTravel로 검증했다. 이전 임시 조합 폴더를 사용하지 않았다.
- `pytest -q -rs backend/tests/test_course_connection.py backend/tests/test_place_retriever.py backend/tests/test_place_retriever_haeundae.py`: **94 passed, 4 skipped, 1 warning**. 실제 해운대 DB가 없어 해당 4개만 skip했다. 실제 #65 연결 검사는 skip 없이 실행했고, 누락 의존성 오류 검사도 장애 주입으로 실행했다.
- 전체 pytest: **1315 passed, 4 skipped, 1 warning**. 계약 6 operations·31 schemas·20 examples·15 정책 사례, 참고 문서 JSON 동기화·diff 검사 PASS.
- #53 `5a579ea`의 외부 원본 CS-01~10을 읽어 현재 브랜치의 기본 검색 설정과 가상 SQLite/FakeTravel로 실행: **9개 자동 검사 통과·실내 미지원 1개 EXCLUDED**, 하드 위반·미존재 장소 0건(가상). 사례 파일을 복제하거나 결과 null을 바꾸지 않았다.
- 실제 공유 DB·찬용 COMP-06·PC/모바일·응답시간 인수는 미완료다. 일반 create_app은 CourseService 미연결·지원 비활성을 유지하는 검사도 통과했다. 실제 키·모델 API·유료 전환·배포·PR 병합은 수행하지 않았다.

## 실제 공유 DB·COMP-06 평가 (2026-11-21)

- 공유 DB SHA-256: `c2b178beb1e2b136c5fba07b33646598fed9da48e73b6443641d8ead1193ec75`, 491520바이트. 읽기 전용 연결, quick_check=ok, 외래키 위반 0건. places 275·운영시간 NULL 103·accessibility 53·출처 2행·반경 1500m 내 107곳을 확인했다. 실행 전후 해시가 같다. DB와 전달받은 txt 파일은 커밋하지 않는다.
- #75 `b926c6c`와 그 기반 develop `6d86ada`를 #72에 반영했다. 개발 브랜치 내 반영이며 GitHub PR #75/#72를 develop에 병합한 것이 아니다. #53의 최신 develop 평가셋을 사용하고 방문일·기대 결과·원본 result=null은 바꾸지 않았다.
- 계산기: `app.travel.walking:create_travel_provider`. 일반 4 km/h·부상 3 km/h, 우회 계수 1.0·분 단위 올림·허용 오차 1e-9분을 사용했다. 실제 보행 경로 검증은 아니다.
- 실행일: `2026-11-21T11:49:07.844002+09:00`. 실행 코드: `548aa7a9aa419d0b48553cfc21903aa60ac506f1`. `workingTreeModified=true`는 당시 전달받은 미추적 txt 파일이 있었기 때문이며, 계산기·실행기 코드는 해당 커밋에 기록되어 있었다. 결과 JSON은 실행 후 새로 생성했다.
- 평가셋 SHA-256: `cdd8d3f75f646707d8bfec65e61af5b894130ef9d47dffafc9011c8fb3213ccb`. 조회/검증 반경 1500m·DEC-023 해운대 중심을 고정했다.
- 자동 검사: **9개 통과, 실내 HARD 미지원 CS-06 1개 EXCLUDED**, SUCCESS 8개·정상 INSUFFICIENT_PLACES(CS-08) 1개. 하드 위반·DB 미존재 장소 각각 **0건**.
- POST 9개 모두 15초 이내(**100%**, 이번 실행 최대 **105.25ms**). 로컬 TestClient 측정이며 외부 LLM·브라우저·지도·호스팅 전체 흐름의 성능 근거가 아니다.
- 공유 경로를 기존 실제 DB 테스트도 `BUSANFIT_DB_PATH`로 선택하도록 보완했다. 실제 검색기 4개 모드 4 passed. 공유 DB를 지정한 최종 전체 pytest **1408 passed, 1 warning**, 계약·참고 문서 JSON 동기화·diff 검사 PASS. 기존 Starlette/httpx 경고 1건이다.

| 사례 | 자동 판정 | 응답 | POST(ms) |
|---|---|---|---:|
| CS-01 | PASS | SUCCESS | 92.12 |
| CS-02 | PASS | SUCCESS | 73.97 |
| CS-03 | PASS | SUCCESS | 63.31 |
| CS-04 | PASS | SUCCESS | 47.77 |
| CS-05 | PASS | SUCCESS | 32.56 |
| CS-06 | EXCLUDED | 실내 HARD 미지원 | — |
| CS-07 | PASS | SUCCESS | 69.74 |
| CS-08 | PASS | INSUFFICIENT_PLACES | 49.54 |
| CS-09 | PASS | SUCCESS | 105.25 |
| CS-10 | PASS | SUCCESS | 38.87 |

### 남은 확인 / 제한

- 결과 JSON의 `realDataVerified`, `realTravelVerified`, `acceptanceComplete`는 기존 실행기 정책에 따라 false를 유지했다. 실제 공유 DB와 실제 계산기를 사용했지만 수동 extraChecks·전체 인수를 완료했다는 뜻은 아니다.
- **이전 실행 당시 CS-05의 부상 규칙 안내 경고는 미포함이었다(아래 후속에서 서버 반영 완료).** 자동 검사 PASS와 별개로 후속 서버 반영 및 화면 확인이 필요하다. CS-03·05·08·09 extraChecks의 수동 확인도 남아 있다. 자동 PASS를 모든 사례별 요구사항 완료로 해석하지 않는다.
- 일반 앱의 CourseService 미연결·capabilities 비활성은 회귀 테스트로 확인했다. #70 정보 없음 포함 기능·동행 가중치의 일반 서비스 활성화·브라우저/모바일 인수·배포·PR 병합은 수행하지 않았다. 평가용 앱 안에서만 승인된 동행 가중치를 사용했다.
- `.env`·실제 키를 읽지 않았고 모델/데이터 API를 호출하지 않았다. #28 댓글 게시와 활성화 판단은 별도 요청 전 수행하지 않는다.

결과: `evaluation/courses/results/real-2026-11-21.json`.

## 부상 안내 경고 후속 반영 (2026-11-21)

- 코드 `2edf98c`: 정규화된 이동제약에 INJURY가 있으면 기존 warnings에 `INJURY_RULES`를 한 번 추가한다. placeIds는 []이며 원문을 넣지 않는다. 문구는 “부상 조건으로 구간당 도보 10분 이내만 연결해요. 이동이 힘들면 택시·대중교통 이용을 권해요.”이다. 최대 시간은 기존 설정에서 읽고 계산기·도보 제한은 바꾸지 않았다.
- 성공/후보 부족 응답 모두 규칙을 안내한다. 코스가 없는 경우에도 “연결했어요”라고 완료를 주장하지 않는다. 부상 없는 요청에는 표시하지 않고 경로 접근성 미확인 경고를 유지한다. API 스키마는 기존 Warning을 그대로 사용하며 계약의 경고 표만 설명을 추가했다.
- 누락·잘못된 일반 코스 경고를 평가기가 거절하도록 검사와 음성 대조를 추가했다. 관련 124 passed, 실제 DB 지정 전체 **1422 passed, 1 warning**, 계약·참고 문서 JSON 동기화·diff 검사 PASS.
- 실제 공유 DB로 CS-01~10 재실행: **9개 자동 통과·실내 미지원 1개 제외**, 하드 위반·미존재 장소 0건, 15초 이내 9/9(최대 127.30ms). CS-05 warningCodes의 `INJURY_RULES`를 확인했다. 보고서 실행 코드 `2edf98c351007dd9afc71bf05a21a655f0e4ceed`, 실행일 `2026-11-21T11:56:54.151429+09:00`, 전달 txt로 workingTreeModified=true. DB 해시는 기존 공유값과 실행 전후 동일하다.
- 아래/위 이전 평가 기록의 부상 경고 미포함은 이 후속에서 서버 반영을 완료했다. 화면 표시와 기타 수동 extraChecks는 별도 미완료이며 전체 인수 플래그는 false로 유지한다. 일반 서비스·동행 가중치·#70 활성화·PR 병합·외부 API 호출은 하지 않았다.
