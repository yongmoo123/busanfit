# FR-005·006 / 이슈 #21 기본값·조건 카드 구현

2026-11-13(KST). #22 PlaceRetriever 구현은 이찬용 담당으로 유지하고, 김영무 담당의 기본값·카드 연결과 활성화 준비를 먼저 진행했다. 실제 #22 연결·검증 없이 일반 서버를 활성화하지 않았다.

## 작업 기준

- 최신 develop `22f1a03`에서 별도 로컬 clone과 `feature/FR-005-profile-defaults` 브랜치를 만들었다.
- 미병합 [PR #48](https://github.com/yongmoo123/busanfit/pull/48)의 `57c8d41`을 선행 코드로 재사용했다. #48 및 그 선행 #13·#17·#44를 원격 develop에 병합한 것은 아니다.
- 기준: FR-005·006, NFR-004·007, DEC-001·002·016·018~022, 기존 API 계약. 외부 경로·JSON 필드 추가 없음.

## 구현한 것

### 기본값

`config/defaults.json`은 서버와 프론트 안내가 함께 읽는 설정이다. 카페 60분·식사 70분·전시/문화 및 기타 카테고리 60분과 부상 안내의 초기 수치(일반 4km/h, 부상 3km/h, 구간당 10분)를 한 곳에서 관리한다. 부상 이동시간 계산·후보 필터 구현은 이번 변경에 포함하지 않는다.

`backend/app/constraints/defaults.py`의 `resolve_stay(category, facility_minutes=..., user_minutes=...)`는 정규화된 양의 정수만 받는다. 사용자 명시 체류 > 시설/TourAPI 관람소요시간 > 카테고리 설정 순으로 결정한다. 서버가 적용한 값은 DEFAULT, 명시한 사용자 값은 USER다. 0·음수·불리언·문자열을 정보 없음으로 조용히 바꾸지 않는다. 알 수 없는 카테고리를 OTHER로 숨기지도 않는다. 아직 스케줄러에 연결하지 않은 순수 함수이며, 장소 조회·SQL·DB·수집 코드는 추가하지 않았다.

조건 카드 PUT도 미입력 이동수단에 WALK/DEFAULT/SOFT를 적용한다. 지원 검증된 WALK일 때만 적용하며, 명시한 USER 값·미지원 이동수단 확인 대기는 보존한다. 클라이언트가 임의로 DEFAULT 출처를 만들면 기존 계약대로 거절한다. '도보 기본값으로 초기화'는 null/UNSET을 전송하고 서버가 기본값을 계산한다.

유모차는 기존 DEC-020 정규화를 재사용한다. 영유아 동반 + mobility=null이면 STROLLER/DEFAULT/HARD, USER 목록은 우선, USER []는 명시적 제약 없음이다. 카드에서 미입력으로 지우면 기본값 적용 대상으로 복귀하고, 유모차만 해제할 때는 다른 이동제약을 유지한다. 이동제약이 SOFT인 카드 입력은 INVALID_PROFILE로 거절하며 화면에도 강도를 변경하는 선택기를 제공하지 않는다.

**예산의 표현 주의:** FR-005의 '제한 없음'을 미입력 예산의 화면 기본 동작으로 표시한다. 외부 계약의 `null ↔ UNSET`을 유지하므로 budget은 null/UNSET이며 source=DEFAULT를 억지로 넣지 않는다. 화면의 '기본값'은 제한을 두지 않는 동작에 대한 설명이다. 0원 예산·무료 장소·가격 정보 없음과 구분한다. 이슈의 '모든 기본값 DEFAULT' 문구를 예산 null에도 적용하면 계약과 충돌하므로 이 차이를 명시했다. 계약 구조 변경이나 새로운 PM 결정을 만들지 않았으며, 이 표현은 담당자 리뷰 대상으로 남긴다.

### #22 후속 연결 지점

`application/profile_support.py`의 `ProfileSupport`를 `create_app(profile_support=...)`에 주입할 수 있게 했다. 기본 앱은 전달하지 않으므로 모두 비활성이다. HTTP 요청이나 환경변수로 지원 범위를 켜는 기능은 없다.

- 실제 후보 검색 연결과 area·timeWindow·transport 검증이 모두 확인돼야 HAEUNDAE/WALK를 연다.
- 첫 활성화 후보는 area·timeWindow·transport·mobility·companions·excludedCategories 중 검증한 항목뿐이다.
- mobility는 별도의 휠체어·유모차·부상 항목별 검증이 있어야 연다.
- budget·indoorPreference·preferenceTags 활성화는 허용하지 않는다. 미확인 접근성 포함·날씨·코스 수정도 false다.
- 이 객체는 연결 담당자가 검증 결과를 명시하는 내부 구성 입력이다. 실제 연결을 자동 탐지하거나 검증을 대신하지 않는다.

연결 담당자가 #22 결과를 받은 뒤 해야 할 일:

1. 실제 PlaceRetriever를 application/코스 흐름에 연결하고 Repository 오류와 후보 0건을 구분한다.
2. 실제 해운대 데이터의 일반·휠체어·유모차·부상 시나리오, UNKNOWN 미통과, 시간·제외 카테고리 검증을 확인한다.
3. 통과한 필드만 ProfileSupport에 지정하고, mobility_verified는 항목별 검증 후 지정한다.
4. 일반 서버의 세션 capabilities → 카드 수정 → READY를 실제 API로 재검증하고 배진호에게 활성화 범위·시점을 공유한다.
5. 스케줄러(#23)에 정규화된 시설 체류시간과 `resolve_stay`를 연결한다. 아직 합의하지 않은 후보 필드 이름은 연결 시 실제 모델과 맞춘다.

이번 가상 테스트·데모에서만 연결/검증 값을 가정했다. 실서버 연결 완료나 #22 구현 완료를 뜻하지 않는다.

### 조건 카드·접근성

- 도보·유모차 기본값 배지와 초기화, 예산 제한 없음, 체류시간 기본값 펼침 안내를 추가했다.
- 세션 capabilities를 표시하고 미지원 조건을 미리 안내하되, 서버의 422 판정을 숨기지 않는다.
- 422는 필드 그룹에 오류 설명·aria-invalid를 연결하고 첫 오류 입력으로 포커스를 옮긴다. 기존 409·410·429·503 처리와 DEC-019~021 질문·경고를 재사용한다.
- 부상을 선택하면 3km/h·구간당 최대 10분·장소의 휠체어 정보를 이용한 계단 회피·실제 경로의 계단/경사 미확인을 안내한다. 지원 전에는 저장할 수 없다는 설명도 표시한다.
- 기본값 안내와 체크박스·저장 버튼은 Enter/Space로 조작했다. 부상·지원 범위·체류시간 안내 대비는 각각 9.87·9.35·8.43:1로 확인했고, 4.15:1이던 실제 API 배지는 더 짙은 글자색으로 보정했다. 전체 서비스에 대한 접근성 인증을 뜻하지 않는다.
- 모바일 360px에서 body와 카드 내부 모두 가로 넘침이 없었다. 카드가 길어지면 세로로 스크롤한다.

## 실행·검증

이번 검사는 인접 `issue20-chat/.venv`의 Python 3.12.14·동일 lock 의존성을 재사용했다. 새 환경에서는 루트 README대로 `.venv`를 만들고 backend/requirements-lock.txt를 설치한다.

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe contracts/validate_contract.py
.venv/Scripts/python.exe contracts/validate_source_sync.py
```

가상 데모(실제 모델·DB·검색 없음):

```powershell
.venv/Scripts/python.exe -m uvicorn app.demo:app --app-dir backend --host 127.0.0.1 --port 8001 --no-access-log
```

다른 터미널:

```powershell
cd frontend
npm ci
$env:BUSANFIT_API_TARGET='http://127.0.0.1:8001'
npm run dev -- --host 127.0.0.1 --port 5174
```

BUSANFIT_API_TARGET은 Vite 개발 프록시 주소뿐이며 서버 capabilities를 바꾸지 않는다. 미지정 기본 주소는 기존 8000을 유지한다. 일반 서버는 app.main:app으로 실행하며 지원 배열은 계속 비어 있다.

가상 UI 재현: '해운대, 2026-11-13 13시부터 17시까지, 가족 3명, 아기 동반' → READY/도보·유모차 DEFAULT → 카드에서 부상 추가·유모차 해제 → USER/HARD와 유모차 미적용 경고 → 초기화·저장 → 유모차 DEFAULT 복원. 자차 선택·저장 시 422 transport 오류와 해당 입력 포커스를 확인했다.

[데스크톱 기본값](evidence/issue21/card-desktop-defaults.jpg), [모바일 360px 부상·예산 안내](evidence/issue21/card-mobile-injury.jpg), [422 필드 포커스](evidence/issue21/card-422-focus.jpg)는 전부 가상 데이터다. 서버에 실제로 연결된 가상 시나리오이며 실제 장소 데이터 사용 증거가 아니다.

## 남은 일

- #22 담당자 구현 결과를 받아 실제 검색을 연결하고 항목별 검증 후 일반 capabilities 활성화.
- 실제 데이터로 카드 수정→READY 캡처 및 프론트 담당자에게 활성화 범위 공유.
- #23 스케줄러의 체류시간 함수 연결과 실제 코스 생성 요청 흐름 검증. 현재 버튼은 기존 가상 코스 미리보기다.
- 예산 기본 동작 표현과 후보·스케줄러 입출력의 담당자 리뷰, #48 선행 병합 이후 develop 기준 재검증.
- PR 작성·원격 CI·담당 외 리뷰·병합은 아직 진행하지 않았다.

## 최종 검사 결과

2026-11-13(KST): **pytest 251 passed**, 기존 Starlette/httpx deprecation 경고 1건. 계약 5 operations·31 schemas·20 examples·15 정책 사례/negative control 통과. 참고 문서 JSON 동기화·git diff --check·프론트 lint·build 통과. 실제 LLM·DB·후보 검색·스케줄러 호출과 원격 CI는 실행하지 않았다. 가상 연결 증거로 일반 서비스 활성화 완료를 표시하지 않는다.
