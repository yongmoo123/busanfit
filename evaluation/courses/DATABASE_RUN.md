# DB 기반 코스 평가 실행 준비 — FR-009 / AI-REQ-01·05

2026-11-20. 실제 DB와 COMP-06 계산기 없이 연결·실행기·가상 검증만 준비한 상태다. 서버 활성화·실제 데이터 인수·병합 완료가 아니다. 기존 `run.py --output ...`의 가상 4개 모드 실행은 유지한다.

## 선행 입력

- PR #65의 `app.retrieval`과 `config/retrieval.json`·사후면세점 제외 파일. 이 브랜치에서 #65를 복제하거나 병합하지 않는다. 없으면 연결 준비가 명확히 실패한다.
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

DB 모드는 위 선행 입력이 모두 준비된 뒤에 사용한다. `--travel-provider`는 **찬용과 합의한 구현의 `모듈:무인자팩토리`**를 받아 실제 포트 객체를 만든다. 현재 해당 구현은 없으므로 아래는 준비된 실행 형식이며 그대로 실행 가능한 명령이 아니다. 가상 테스트 팩토리를 실제 보고서에 쓰지 않는다.

```text
# PowerShell: 키/.env는 필요 없으며 읽지 않는다.
$env:BUSANFIT_DB_PATH = '<공유 DB 절대 경로>'
.venv/Scripts/python.exe evaluation/courses/run.py --mode real --cases evaluation/courses/cases.json --travel-provider '<합의한 모듈>:<팩토리>' --expected-db-sha256 '<공유 파일 SHA-256>' --output evaluation/courses/results/real-2026-11-21.json
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

## 남은 작업

- #65·#53 통합 및 찬용 계산기 구현/계약 확인.
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
