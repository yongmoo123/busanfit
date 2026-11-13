# FR-009 / 이슈 #23 스케줄러·검증기·코스 생성 API

작성: 2026-11-13(KST). 김영무 담당 부분을 구현하고, #22 후보 검색·이동시간은 가짜 제공자로 먼저 검증했다. 실제 해운대 데이터 인수 완료를 뜻하지 않는다.

## 기준·재사용

- 최신 원격 develop `22f1a03` 확인 후 별도 `issue23-courses` clone, `feature/FR-009-course-generation` 브랜치에서 작업했다.
- #20/#21 구현인 `432da7e`(PR #49, 선행 #48 포함)를 재사용했다. 세션의 begin_course/check_current/finish_read와 #21 체류시간 기본값·이동제약 정규화를 다시 구현하지 않았다.
- PR #15 `07ad02c5285539c6f2e56edeecec8eb19e0442b2`의 `domain/place.py`, `domain/__init__.py`, `data/repository.py`, `data/place_id.py`를 원문 그대로 선택 재사용했다. 공통 업무 모델을 중복 정의하지 않았으며 SQLite 구현·공간 검색·수집 파이프라인은 가져오지 않았다. 이 선택 복사는 #15 또는 #22 승인·병합을 의미하지 않는다.
- 기준 문서의 기존 DB 안내와 DEC-005가 달라 data README는 SQLite 확정 결정으로 정정했다. 이번 코스 엔진은 DB를 직접 호출하지 않는다.
- 관련: FR-009, AI-REQ-01·05, NFR-001·002·003·005, DEC-001·014·015·016·021. 스프린트 2 HAEUNDAE/WALK 범위를 유지한다.

## 구현 흐름

1. API는 sessionId/profileRevision을 받고 세션·요청 제한·프로필 필수 정보·확인 대기·revision을 검사한다.
2. CourseService가 기존 기본값 정책을 적용하고 지원하지 않는 활성 제약을 거절한다. 예산·선호 태그·동행 HARD·미확인 접근성 포함 등을 무시한 채 성공으로 바꾸지 않는다.
3. 주입한 CandidateRetriever에서 후보를 받고 최대 20개로 제한한다. 각 ID를 Repository.get_place로 다시 조회해 원래 장소 사실을 사용한다. 후보 제공자의 오래된/잘못된 속성을 신뢰해 덮어쓰지 않는다.
4. 검증된 운영시간·지역·반경·제외 카테고리·항목별 접근성을 확인하고 미확인 정보를 필요한 하드 조건의 통과로 바꾸지 않는다. 현재 계약에서 필수인 주소가 없는 장소도 임의 문자열로 채우지 않고 제외·집계한다.
5. CourseScheduler가 모든 시작 후보와 유효 prefix를 비교해 시간 안에 체류·이동·대기를 배치한다. 결과는 기존 계약의 2~6곳이며 시간을 모두 채울 필요는 없다.
6. CourseValidator가 장소 실존·현재 사실·영업시간·시간창·이동제약·이동시간 근거·부상 구간당 최대 10분·방문 중복/구조를 별도로 검증한다.
7. 초안이 실패하면 위반 장소를 제외하고 최대 3회 교체·재배치·재검증한다. 출처 조회 중 장소 사실이 바뀌는 경우도 마지막에 재검사한다. 통과한 두 곳을 만들지 못하면 INSUFFICIENT_PLACES/course=null이다. 위반한 부분을 성공 코스에 남기거나 CONDITIONAL로 우회하지 않는다.
8. 검증한 장소·출처를 기존 응답 형식으로 변환하고, 반환 직전 session revision/만료를 다시 검사한다. 성공·후보 부족 모두 프로필 revision은 그대로이며 TTL만 갱신한다. 실패는 TTL·프로필·revision을 갱신하지 않는다.

### 배치·점수·시간

- 설정은 `config/courses.json`의 반경 1500m, 후보 20, 방문 6, 교체 재시도 3회다. 반경은 #22가 반환한 권역 중심으로부터의 거리 근거를 검사하며, 실제 중심 좌표/거리 계산은 이찬용의 #7/#22 책임이다.
- 기본 정렬은 재현 가능한 휴리스틱이며 전역 최적해를 보장하지 않는다. 일반 모드는 방문 수→SOFT 점수→체류시간→짧은 이동, 부상 모드는 적은 방문 수→SOFT 점수→짧은 이동→체류시간 우선이다. 부상은 마지막 방문의 확인된 영업 구간·시간창 안에서 체류를 늘린다. 이 선호가 하드 조건을 완화하지 않는다.
- 기본 SOFT 점수는 명시한 실내/실외 선호의 이진 일치만 사용한다. #27 가중치 값은 정하지 않고 scorer 주입 지점을 제공했다. PM 확인이 필요한 동행 가중치는 이번에 확정하지 않았다.
- #21 resolve_stay를 사용해 시설 기본 체류시간을 반영한다. 이동시간은 이찬용의 제공자가 계산하며 이 구현에는 거리 공식·반올림·속도 계산이 없다. INJURY 플래그를 제공자에 전달하고 검증기는 10분 제한을 적용한다.
- 운영시간은 PR #15의 정규화된 mon..sun 구간을 사용한다. 표시 문자열은 근거로 사용하지 않는다. 누락 요일/파싱 불가와 확인된 휴무([]), 휴게시간, 전날부터 이어진 야간 영업, 24:00을 구분한다. 검증 가능한 구간이 없는 장소는 사용하지 않는다.
- 정수 분 합계를 정확히 유지하기 위해 초/마이크로초가 있는 도착 시각은 다음 분으로 올린다. 체류시간을 줄이거나 시간창을 초과하지 않는다. 첫 장소 이전·마지막 장소 이후 이동은 합계에 포함하지 않고 경고로 알린다.
- #29의 앵커 구현은 하지 않았다. 후속 오케스트레이터가 좁은 가용 시간창을 넘길 수 있는 available_window 인자만 준비했다. 앵커 API·구간 합치기·교차 구간 검증은 후속이다.

### 응답·실패·민감정보

- 요청은 `CourseRequest.profileRevision`이며 chat/profile의 expectedProfileRevision을 대신 받지 않는다.
- SUCCESS는 검증된 course를 포함하고 INSUFFICIENT_PLACES는 course=null이다. 새 외부 상태나 JSON 필드를 추가하지 않았다.
- items.order·고유 item ID·N-1 legs·이동/체류/대기 합계·sources 참조를 구성한다. 가격은 UNKNOWN/null이고 일부 가격 합을 총비용으로 표시하지 않는다.
- 장소 접근성은 wheelchair/stroller 항목으로 판단한다. 등급만으로 필터하지 않는다. 경로의 계단·경사는 확인하지 못하므로 routeAccessibility=UNVERIFIED와 경고를 유지한다. PASSED는 checkedHardConstraints의 데이터·추정 방식 기준이며 전체 경로 검증 완료가 아니다.
- 이유는 DB 사실을 벗어나지 않는 최소 TEMPLATE 문장이다. #25의 LLM 설명 기능을 구현한 것이 아니다. suggestions=[]는 #26 연결 전 범위다.
- 누락 이동시간은 0분으로 바꾸지 않는다. 조회/이동시간/출처 오류는 기존 500 INTERNAL_ERROR이며 후보 부족·AI 장애로 숨기지 않는다. 예외 원문을 응답·로그에 복사하지 않는다. 변경된 revision/만료는 늦은 결과와 오류보다 우선한다.
- 코스 생성은 사용자 원문을 받지 않고 LLM을 호출하지 않는다. 결과 코스와 건강 프로필을 DB에 저장하지 않는다. 코스 ID는 현재 응답 식별자이며 #32 수정용 저장 기능은 별도다. 배포 프록시·호스팅 로그는 실제 연결 후 별도 점검한다.

## 연결 포트 — 실제 구현과 맞춰야 할 제안

`domain/course.py`의 다음 형태는 가짜 제공자 검증을 위해 정한 내부 연결 제안이다. 실제 #22/이동시간 함수 이름을 일방적으로 확정한 것이 아니며 이찬용과 어댑터에서 맞춘다.

| 포트 | 입력/출력 | 실패 의미 |
|---|---|---|
| CandidateRetriever.retrieve | Profile → RetrievalResult(PlaceCandidate tuple, 제외 UNKNOWN의 고유 ID/필드) | 빈 후보는 실제 후보 없음, 저장소 오류는 예외 |
| TravelTimeProvider.estimate | PlaceRecord 2개 + injury bool → TravelEstimate(정수 분) 또는 None | None은 계산 불가, 실제 계산/저장소 오류는 예외. 0은 실제로 확인한 0분만 허용 |
| PlaceRepository | PR #15의 get_place/existing_place_ids/get_sources | 없는 ID와 저장소 오류/깨진 출처 참조를 구분 |

진짜 #22는 정규화 운영 구간·권역 중심 거리·무장애 항목값을 전달해야 한다. 출처는 places와 accessibility의 source_id를 합친다. 실제 후보·운영시간 처리의 PM 결정·이동시간 반올림/보정·DB 이용조건을 확인한 뒤 연결한다. 도보 추정 어댑터는 DISTANCE_ESTIMATE/isEstimate=true를 만족해야 한다.

일반 `create_app()`에는 course_service가 없고 capabilities는 계속 비활성이다. 가짜 제공자를 자동 설치하지 않는다. 실제 연결·검증 후 CourseService와 ProfileSupport를 함께 주입하는 것은 후속 작업이다.

## 실행

Python 3.12 환경에서 backend/requirements-lock.txt를 설치한다. 이번 검사는 기존 issue20-chat 가상환경의 동일 lock 의존성을 재사용했다. 새 의존성 추가는 없다.

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe contracts/validate_contract.py
.venv/Scripts/python.exe contracts/validate_source_sync.py
.venv/Scripts/python.exe evaluation/courses/run.py --output evaluation/courses/results/synthetic-2026-11-13.json
```

기준 문서/검사에 assert가 있어 Python -O는 사용하지 않는다. Windows 샌드박스에서 비동기 테스트가 정지하는 제한 때문에 네트워크 없는 검사도 제한 밖에서 실행했다. 현재 프론트 코드는 변경하지 않았으며 이번 작업에서 프론트 검사를 새로 실행하지 않았다.

가상 전용 실제 HTTP 서버:

```powershell
.venv/Scripts/python.exe -m uvicorn app.course_demo:app --app-dir backend --host 127.0.0.1 --port 8002 --no-access-log
```

http://127.0.0.1:8002/docs 에서 세션 생성→프로필 PUT→반환된 profileRevision으로 POST /api/courses 순서다. sourceIds와 장소 이름은 모두 synthetic/[가상]이며 실제 여행 추천에 사용하지 않는다. 일반 app.main과 달리 이 데모만 가짜 제공자와 가상 지원 범위를 명시적으로 주입한다. 기존 프론트 버튼은 여전히 가상 미리보기이며 #24 화면 연결은 하지 않았다.

## 검증 결과와 한계

- 전체 pytest 결과는 아래 최종 검사 기록을 따른다. 기존 Starlette/httpx deprecation 경고 1건. Python 3.12.14에서 실행했으며 이번 원격 CI/Python 3.11 검사는 아직 실행하지 않았다.
- 기존 계약 5 operations·31 schemas·20 examples·15 정책 사례/negative control 및 참고 문서 JSON 동기화 통과. HTTP 응답도 기존 CourseResponse 스키마와 대조했다.
- API 테스트는 4개 이동제약 시나리오, 원본 사실 재조회, 시간/운영 구간 경계, 이동시간 None, 부상 10/11분, 정보 없음 집계, 400/409/410/422/429/500, revision/만료 경쟁, 실패 시 TTL 유지, 초기 초안+최대 3회 교체, 누락 출처·가격 UNKNOWN을 검사한다.
- 검증기 단독 오류 주입은 시간창 초과·겹침·체류 불일치·중복 장소·잘못된 이동시간·미존재 ID·반경 초과·접근성/운영시간 미확인·제외 카테고리 등을 거절하는지 검사한다.
- `evaluation/courses/audit.py`는 CourseValidator와 운영시간 병합 코드를 호출하지 않는 독립 응답 검사기다. Repository 사실·매 점유 분의 운영 여부·이동시간·합계·출처·미확인 HARD를 확인한다. 이 검사기의 4개 정상 시나리오, 잘못된 성공 응답 및 미지원 활성 프로필 거절도 pytest에 포함했다.
- 평가 실행기는 8개 가상 후보(운영시간/접근성 미확인 포함)에서 일반·휠체어·유모차·부상별 10회, 총 **40회 HTTP/ASGI 요청**, 하드 위반 **0건**, 가상 Repository 미존재 장소 **0건**을 확인했다. 원격 해운대 데이터가 아니라 명시적인 가상 Repository 기준이다.
- 가상 지연 측정 40회는 모두 15초 이내였다. 최종 max/min/mean과 코드 revision·수정 여부·실행일은 [결과 JSON](../evaluation/courses/results/synthetic-2026-11-13.json)을 따른다. 이는 실제 DB·이동시간·호스팅·LLM 지연을 포함한 NFR-001 충족 증거가 아니다.
- 별도 Uvicorn HTTP smoke는 데모의 4개 가상 장소로 실행했다. 일반/휠체어/유모차 각각 4곳, 부상 2곳, 모두 SUCCESS·PASSED·경로 UNVERIFIED·synthetic ID만 반환했다. 세션 ID는 결과 파일/콘솔에 남기지 않았다.

## 남은 작업

1. 이찬용의 실제 #22·TravelTimeEstimator·Repository를 어댑터로 연결하고 후보 형태·거리 근거·운영 구간·반올림/보정을 합의한다. 실제 검색/이동시간 구현은 이찬용 담당이다.
2. 실제 해운대 일반·휠체어·유모차·부상 4개 시나리오에서 독립 검사기의 하드 위반 0건·미존재 ID 0건과 UNKNOWN 제외 집계를 확인한다.
3. 실제 데이터/호스팅에서 15초 목표를 측정한다. 외부 모듈의 I/O 취소·타임아웃은 실제 연결 때 확인해야 하며 현재 동기 포트는 worker thread에서 실행한다.
4. 검증된 필드만 #21 ProfileSupport로 일반 서버에 활성화하고, #24 프론트 코스 요청·결과 화면을 연결한다.
5. #25 추천 이유/장소 상세, #26 조정 제안, #27 PM 확인 가중치, #29 앵커, #32 수정 기능은 후속이다.
6. 선행 #49/#48/#15 및 본 변경 리뷰·병합 후 develop 기준 재검증. 본 작업에서는 PR 게시·원격 CI·이슈 종료를 하지 않았다.

## 최종 검사 기록

2026-11-13(KST), Python 3.12.14: **331 passed** (기존 251 + #23 관련 80), 기존 Starlette/httpx 경고 1건. 계약·참고 문서 JSON 동기화·git diff --check 통과. 최종 가상 40회 결과 JSON은 구현 커밋 기준으로 다시 실행해 코드 revision과 작업 트리 상태를 기록한다. 프론트 코드와 실제 LLM·DB·검색·이동시간·원격 CI는 이번 검사 대상이 아니다.
