# DB·PlaceRepository — 이찬용 · COMP-10
FR-007·008·012·020. 스키마·DB 생성 명령·`SqlitePlaceRepository`(반경 검색, 장소 조회, 장소 ID 존재 확인, 출처 조회)가 있음. 해운대 표본 적재 명령은 `pipelines/haeundae_sample.py`(이슈 #7 작업 C)에 있음.
입력: 정규화된 실제 장소/출처, 지원 검색 조건. 출력: 계약의 Place·Source 및 내부 운영시간 구간.
DB는 SQLite입니다(DEC-005, SDD ADR-008). 좌표는 latitude/longitude REAL, 반경 검색은 위경도 사각형 1차 필터 후 하버사인 2차 필터입니다. 김영무와 Repository 입출력·복수 출처 매핑을 맞춥니다. 후보 판단은 retrieval/COMP-04에서 분리합니다.

## DB 만들기
- 스키마: `schema.sql` (SDD 5.2·그림 5-1). 새 파일에 한 번 적용하며, 갱신은 새 DB 파일을 만든 뒤 교체합니다.
- DB 경로는 환경변수 `BUSANFIT_DB_PATH`로만 받습니다(필수, 기본값 없음). 이름은 루트 `.env.example`에 있습니다. 현재 앱은 `.env`를 자동으로 읽지 않으므로 셸에서 설정합니다.
- DB 파일은 커밋하지 않습니다(`.gitignore`의 `*.sqlite*`, `*.db`).

```text
# PowerShell, 저장소 루트
$env:BUSANFIT_DB_PATH = "data/busanfit.sqlite3"
cd backend; ../.venv/Scripts/python.exe -m app.data.db create; cd ..
```
상대 경로는 명령을 실행한 폴더 기준입니다(위 예시는 `backend/data/busanfit.sqlite3`). 같은 경로에 파일이 있으면 덮어쓰지 않고 오류를 냅니다. 다시 만들려면 기존 파일을 직접 지운 뒤 실행합니다. 생성 도중 실패하면 부분 파일을 남기지 않으므로 같은 명령으로 다시 실행할 수 있습니다. `db create`는 빈 스키마만 만듭니다. 해운대 표본은 저장소 루트에서 `.venv/Scripts/python.exe -m pipelines.haeundae_sample build --db data/haeundae_sample.sqlite3`로 새 DB 파일에 적재합니다(`--report <경로>`로 보고서 JSON 저장 가능). build는 네트워크 없이 수집 원본(기본 `data/raw/tourapi/`)만 읽고, 같은 경로에 파일이 있으면 덮어쓰지 않고 거절합니다. 원본 수집(`fetch`)과 키 설정은 `pipelines/README.md`를 따릅니다.
좌표·원본 ID·중복·출처 연결·누락을 검증하고 UNKNOWN은 그대로 유지합니다.

## DB 받는 방법 (4개 권역 v3)
DB 파일은 용량과 재현성 때문에 git에 커밋하지 않습니다. 공유 파일을 받거나, 수집 원본(`data/raw/`)이 있으면 직접 만듭니다.

**(a) 공유받은 파일 쓰기** — 최신은 v3입니다. 파일 이름은 `busanfit_v3.sqlite3`, 같이 받은 `busanfit_v3.txt`에 SHA-256·크기·권역별 장소 수·운영시간 NULL 수·무장애 행 수·grade 분포·원 밖이라 건너뛴 수·백화점 예외 목록이 있습니다. v3는 4개 권역(해운대·서면·광안리·남포) 중심에서 반경 1500 m 안의 장소만 들어 있고(PM 결정 11/21, 중심은 `config/retrieval.json` `areaCenters`), `places.area`가 원 기준 권역입니다. 해운대 107곳은 v2의 해운대해수욕장 1500 m 안 107곳과 같습니다(장소 칸·무장애 행·#65 후보 ID 모두 같음). v2(`haeundae_sample_v2.sqlite3`)는 해운대구 전체 275곳(원 밖 포함)이고, v1은 grade가 모두 UNKNOWN·license NULL입니다. 저장소 루트 `data/share/`에 두면 `.gitignore`(`*.sqlite*`)로 커밋되지 않습니다. 앱은 `BUSANFIT_DB_PATH` 환경변수로만 DB를 찾고 `.env`를 자동으로 읽지 않으므로 셸에서 설정합니다. 상대 경로는 명령을 실행한 폴더 기준이라 절대 경로를 권장합니다.
```text
# Windows PowerShell, 저장소 루트
$env:BUSANFIT_DB_PATH = (Resolve-Path data/share/busanfit_v3.sqlite3).Path
# macOS/Linux, 저장소 루트
export BUSANFIT_DB_PATH="$(pwd)/data/share/busanfit_v3.sqlite3"
```
- 권역을 앱에서 켜는 코드(`supportedAreas` 등)는 v3와 별도입니다(김영무 확인 대기). 지금 API는 v3를 연결해도 해운대만 받습니다.

**(b) 직접 만들기** (부산 시군구 원본 `data/raw/tourapi/`·`data/raw/tourapi/<권역>/`·`data/raw/tourapi/sigungu/<코드>/`가 있는 사람, 네트워크 없음) — 사후면세점 제외 목록을 원 기준으로 만든 뒤 `circle_build`로 장소·무장애 값·grade·license를 한 번에 넣습니다(운영시간 파서·카테고리는 `mapping.build_rows`, 무장애 판정·grade는 `accessibility_judge`의 DEC-026 규칙 그대로, license는 `pipelines/mapping.py`의 `PORTAL_LICENSE` 한 곳). 같은 경로에 파일이 있으면 거절합니다. 원본 수집 명령과 자세한 규칙은 `pipelines/README.md` "권역 확장".
```text
.venv/Scripts/python.exe pipelines/duty_free_ids.py --check     # 제외 목록이 원본과 같은지 (다르면 --check 없이 다시 생성)
.venv/Scripts/python.exe -m pipelines.circle_build --db data/busanfit_v3.sqlite3
```
해운대만 있는 v2 방식(`haeundae_sample build` + `accessibility_judge load`)도 그대로 쓸 수 있습니다(`pipelines/README.md`).

**(c) 파일 확인 (SHA-256)** — 결과가 `.txt`의 SHA-256과 같아야 합니다(대소문자 무관).
```text
# Windows PowerShell
(Get-FileHash data/share/busanfit_v3.sqlite3 -Algorithm SHA256).Hash
# macOS
shasum -a 256 data/share/busanfit_v3.sqlite3
# Linux
sha256sum data/share/busanfit_v3.sqlite3
```
v3: `e8bd5c5142af936e819e71036a7919fa0c847a707dceec94d9b5e6a4a219a6fc`, 839680 바이트 (places 630 = 해운대 107·서면 258·광안리 64·남포 201, `open_hours` NULL 296, accessibility 77행, data_sources 2행, grade VERIFIED 63곳·UNSUITABLE 1곳·UNKNOWN 566곳). 직접 만들면 파일 SHA는 다를 수 있으나 테이블 내용은 같습니다(두 번 만들어 `iterdump` 비교 확인).
v2(이전, 해운대구 전체): `2ff6a71a6cb4a7a51bdba39d0a92f164985c30cc138cbe5fbcfc05caedf67898`, 491520 바이트. v1: `c2b178beb1e2b136c5fba07b33646598fed9da48e73b6443641d8ead1193ec75`, 491520 바이트.

**(d) 연결 점검** — places 건수와 반경 검색 1회(해운대해수욕장 35.159084, 129.160279 반경 1500 m). `BUSANFIT_DB_PATH`를 설정한 셸에서 실행합니다. v3 기준 `places 630`, `within_1500m 107`(v2와 같음, 다른 권역 원은 해운대 원과 겹치지 않음).
```text
# Windows PowerShell, 저장소 루트
cd backend; ../.venv/Scripts/python.exe -c "from app.data import db; from app.data.sqlite_repository import SqlitePlaceRepository as R; c = db.connect(); print('places', c.execute('select count(*) from places').fetchone()[0]); print('within_1500m', len(R(c).find_within_radius(35.159084, 129.160279, 1500))); c.close()"; cd ..
# macOS/Linux, 저장소 루트
(cd backend && ../.venv/bin/python -c "from app.data import db; from app.data.sqlite_repository import SqlitePlaceRepository as R; c = db.connect(); print('places', c.execute('select count(*) from places').fetchone()[0]); print('within_1500m', len(R(c).find_within_radius(35.159084, 129.160279, 1500))); c.close()")
```

**(e) 이용조건과 주의**
- 데이터 이용허락범위: 제한 없음(공공데이터포털 기준, 국문 관광정보·무장애 여행 정보 모두). 두 출처의 `data_sources.license`에 "이용허락범위 제한 없음(공공데이터포털)"으로 기록(NFR-009, v2부터). 출처 표시: 한국관광공사, 화면 문구는 SDD 7.3 "출처: 제공기관·데이터명(기준일)". DB 파일은 용량과 재현성 때문에 git에 커밋하지 않음.
- 무장애 값은 DEC-026 확정 규칙(#64 표현 목록, 11/19 PM 확인, #58) 기준. grade는 DEC-026 ③ 규칙으로 계산(휠체어·유모차 두 항목만: 하나라도 true면 VERIFIED, true 없이 false가 있으면 UNSUITABLE, 둘 다 null이면 UNKNOWN). 등급은 표시용이고 후보 판정은 항목값으로 함(DEC-015).
- 사후면세점(SH040300)은 `config/duty-free-exclusion.proposal.json`의 ID로 후보에서 제외(DEC-023 ④). 백화점 본점 항목은 `config/duty-free-exceptions.json`으로 제외하지 않음(PM 11/21). 롯데백화점 부산본점은 2908259(SH040300, 예외)와 132607(SH010100)의 두 항목으로 들어 있음(`busanfit_v3.txt` 참고).

## 반경 검색 (작업 D)
- `SqlitePlaceRepository(conn)` (`sqlite_repository.py`): `db.connect()`로 연 연결을 받아 읽기만 합니다. 연결은 호출한 쪽이 닫습니다.
- `find_within_radius`는 ① `geo.bounding_box`의 위경도 사각형(경도 폭은 cos(위도)로 보정)으로 `idx_places_lat_lon`을 쓰는 SQL 1차 필터, ② `geo.haversine_m` 2차 필터 순서입니다. 거리 ≤ 반경이면 포함합니다.
- 반경은 호출자가 `settings.walk_radius_m()`(환경변수 `BUSANFIT_WALK_RADIUS_M`, 비우면 1500 m, DEC-001)로 읽어 넘깁니다. 잘못된 값은 기본값으로 바꾸지 않고 오류입니다.
- SQLite 오류(테이블 없음, 닫힌 연결 등)와 규칙에 어긋난 저장 행은 `RepositoryError`입니다. 빈 목록은 "조건에 맞는 장소 없음"만 뜻합니다.

## 장소 ID (DEC-017)
API의 place.id는 `{data_sources.code}:{places.source_place_id}`입니다(예: `tourapi-kor:126508`). DB 내부 정수 `places.id`는 DB를 새로 만들면 바뀌므로 내보내지 않습니다. `data_sources.code`는 고정 값이며 소문자·숫자·하이픈만 허용합니다. 관광정보 `tourapi-kor`는 `pipelines.haeundae_sample build`가 넣고, 무장애 `tourapi-barrierfree`는 `pipelines.accessibility_judge load`가 없을 때만 추가합니다. 장소 ID는 `places.source_id`의 출처(`tourapi-kor`)로 만들고, `tourapi-barrierfree`는 accessibility 행의 출처로만 쓰입니다. `source_place_id`는 영문 대소문자·숫자·`_`·`-`만, 1~64자입니다. 그 밖의 글자(`?` `#` `%` `/` 공백 `.` 한글 등)가 있는 원본 ID는 바꾸지 않고 적재를 거절합니다. 만들기·나누기는 `place_id.py`의 `make_place_id`·`parse_place_id`를 씁니다.
외부 수집은 pipelines, 요청 시 검색은 이 영역입니다. 초기 적재 재현은 pipelines와 함께 검수합니다.
FR-017의 역·주차장·엘리베이터·보관함 조회도 담당합니다. FR-019 공유 저장은 Could 후속이며 세션/건강 원문 저장과 구분합니다.

2026-11-17: 기존 PR #50에서 PR #41(451b3f0)의 db/geo/memory/schema/settings/sqlite_repository와 공통 검사를 재사용했다. application/sqlite_adapter.ConnectionPerCallRepository(path)는 호출한 worker thread에서 연결을 열고 닫는다. 테스트 행·후보·이동시간은 가상이고 일반 앱은 자동 연결하지 않는다. 주소 nullable인 원본 스키마의 DEC-023 반영은 데이터 담당 후속이다.
