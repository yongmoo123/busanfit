# DB·PlaceRepository — 이찬용 · COMP-10
FR-007·008·012·020. 스키마만 있음, Repository 구현은 진행 중(이슈 #7).
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
상대 경로는 명령을 실행한 폴더 기준입니다(위 예시는 `backend/data/busanfit.sqlite3`). 같은 경로에 파일이 있으면 덮어쓰지 않고 오류를 냅니다. 다시 만들려면 기존 파일을 직접 지운 뒤 실행합니다. 생성 도중 실패하면 부분 파일을 남기지 않으므로 같은 명령으로 다시 실행할 수 있습니다. 지금은 빈 스키마만 만들며, 해운대 표본 적재 명령은 이슈 #7 작업 C에서 추가합니다.
좌표·원본 ID·중복·출처 연결·누락을 검증하고 UNKNOWN은 그대로 유지합니다.

## 반경 검색 (작업 D)
- `SqlitePlaceRepository(conn)` (`sqlite_repository.py`): `db.connect()`로 연 연결을 받아 읽기만 합니다. 연결은 호출한 쪽이 닫습니다.
- `find_within_radius`는 ① `geo.bounding_box`의 위경도 사각형(경도 폭은 cos(위도)로 보정)으로 `idx_places_lat_lon`을 쓰는 SQL 1차 필터, ② `geo.haversine_m` 2차 필터 순서입니다. 거리 ≤ 반경이면 포함합니다.
- 반경은 호출자가 `settings.walk_radius_m()`(환경변수 `BUSANFIT_WALK_RADIUS_M`, 비우면 1500 m, DEC-001)로 읽어 넘깁니다. 잘못된 값은 기본값으로 바꾸지 않고 오류입니다.
- SQLite 오류(테이블 없음, 닫힌 연결 등)와 규칙에 어긋난 저장 행은 `RepositoryError`입니다. 빈 목록은 "조건에 맞는 장소 없음"만 뜻합니다.

## 장소 ID (DEC-017)
API의 place.id는 `{data_sources.code}:{places.source_place_id}`입니다(예: `tourapi-kor:126508`). DB 내부 정수 `places.id`는 DB를 새로 만들면 바뀌므로 내보내지 않습니다. `data_sources.code`는 적재 스크립트가 고정 값으로 넣으며(관광정보 `tourapi-kor`, 무장애 `tourapi-barrierfree`) 소문자·숫자·하이픈만 허용합니다. `source_place_id`는 영문 대소문자·숫자·`_`·`-`만, 1~64자입니다. 그 밖의 글자(`?` `#` `%` `/` 공백 `.` 한글 등)가 있는 원본 ID는 바꾸지 않고 적재를 거절합니다. 만들기·나누기는 `place_id.py`의 `make_place_id`·`parse_place_id`를 씁니다.
외부 수집은 pipelines, 요청 시 검색은 이 영역입니다. 초기 적재 재현은 pipelines와 함께 검수합니다.
FR-017의 역·주차장·엘리베이터·보관함 조회도 담당합니다. FR-019 공유 저장은 Could 후속이며 세션/건강 원문 저장과 구분합니다.
