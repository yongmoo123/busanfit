# 수집·정규화·적재 — 이찬용

관련 FR-007·008·012·020. 초기 적재는 첫 연결에 필요하고 자동 갱신은 별도 후속 작업입니다.
원본 식별자·제공기관·URL·기준일·조회일·이용조건·좌표계를 기록합니다. 키와 원본 데이터는 저장소에 넣지 않습니다.
운영시간 누락은 상시 영업, 가격 누락은 무료, 접근성 누락은 접근 가능으로 바꾸지 않습니다.

## 해운대 표본 적재 (이슈 #7 작업 C)

`haeundae_sample.py`는 **수집(fetch)과 적재(build)를 나눕니다.** fetch만 네트워크를 쓰고, build는 `data/raw/`만 읽어 새 SQLite 파일을 만듭니다. 같은 원본이면 같은 DB가 나옵니다.

| 파일 | 내용 |
|---|---|
| `env.py` | `.env`·환경변수에서 키를 읽음 (표준 라이브러리만). 값은 출력하지 않음 |
| `tourapi_client.py` | urllib 클라이언트. 키는 한 번만 인코딩, 출력 URL은 `serviceKey=***`, 호출 수 제한 |
| `haeundae_sample.py` | `check` / `fetch` / `build` 명령 |
| `mapping.py` | 원본 → `places` 행 변환 (카테고리·운영시간·가격 규칙) |
| 테스트 | `backend/tests/test_pipelines_haeundae.py` (CI가 실행하는 경로, 네트워크 없음) |

### 실행 (저장소 루트, Python 3.12 venv)

```text
# 1) 키: 저장소 루트 .env (커밋 금지) 또는 환경변수. 이름만 적는다
#    TOURAPI_SERVICE_KEY=...                  두 서비스에 같이 사용
#    TOURAPI_KOR_SERVICE_KEY=..., TOURAPI_WITH_SERVICE_KEY=...   서비스별 (있으면 우선)
#    Encoding 키·Decoding 키 어느 쪽이든 됨 (%가 있으면 한 번 풀고 한 번만 인코딩)

# 2) 키 확인: 서비스마다 1건 호출, HTTP 상태와 resultCode만 출력
.venv/Scripts/python.exe -m pipelines.haeundae_sample check

# 3) 수집: data/raw/tourapi/ 에 원본 저장. 받은 파일은 다시 받지 않으므로 끝날 때까지 반복 실행
.venv/Scripts/python.exe -m pipelines.haeundae_sample fetch --max-calls 200
#    "fetch complete"가 나올 때까지 (해운대 전체는 호출 약 554번 = 200 + 200 + 154)

# 4) 적재: 네트워크 없이 새 DB 파일 생성 (같은 경로에 파일이 있으면 거절 → 지우고 다시)
.venv/Scripts/python.exe -m pipelines.haeundae_sample build --db data/haeundae_sample.sqlite3 --report data/processed/haeundae_report.json

# 5) 앱이 쓰도록 연결
$env:BUSANFIT_DB_PATH = "data/haeundae_sample.sqlite3"     # PowerShell (backend 기준 상대경로면 경로 주의)
```

`data/raw/`, `data/processed/`, `*.sqlite*`, `.env`는 `.gitignore` 대상입니다(`git check-ignore`로 확인). 원본 폴더는 `--raw`로 바꿀 수 있습니다.

### 확인한 API 사양 (출처)

엔드포인트·파라미터·응답 필드 이름은 저장소 문서에 없어서 **공공데이터포털 페이지에 들어 있는 Swagger 정의**로 확인했습니다(2026-11-12).
- 국문 관광정보 서비스_GW: <https://www.data.go.kr/data/15101578/openapi.do> — `https://apis.data.go.kr/B551011/KorService2`
- 무장애 여행 정보_GW: <https://www.data.go.kr/data/15101897/openapi.do> — `https://apis.data.go.kr/B551011/KorWithService2`

| 단계 | 오퍼레이션 | 주요 파라미터 |
|---|---|---|
| 법정동 코드 | `ldongCode2` | `lDongRegnCd`(시도), `lDongListYn=N` |
| 분류체계 코드 | `lclsSystmCode2` | `lclsSystmListYn=Y` |
| 해운대 목록 | `areaBasedList2` | `lDongRegnCd=26`, `lDongSignguCd=350`, `arrange=A`, `numOfRows=1000` |
| 공통정보 | `detailCommon2` | `contentId` (개요·주소·좌표) |
| 소개정보 | `detailIntro2` | `contentId`, `contentTypeId` (이용시간·쉬는날·이용요금) |
| 무장애 (구조 확인만) | `detailWithTour2` | `contentId` |

- 공통: `serviceKey`, `MobileOS=ETC`, `MobileApp=BusanFit`, `_type=json`.
- 지역 필터 `areaCode`·`sigunguCode`는 Swagger에 "미사용항목(삭제예정-법정동 코드 대체)"으로 표시되어 법정동 코드를 씁니다. 부산 `26`, 해운대구 `350`은 `ldongCode2` 응답에서 확인했습니다(추측 값 아님).
- 좌표: `mapx` = 경도, `mapy` = 위도 (위치기반조회 파라미터 설명 "mapX: WGS84 경도").
- **일일 호출 한도: 문서에 없음.** 포털 페이지와 응답 어디에도 숫자가 없습니다. 공공데이터포털 마이페이지 > 개발계정 상세보기에서 확인해야 합니다.

### 보고서 (2026-11-12 수집)

| 항목 | 값 |
|---|---|
| 해운대구 목록 (`areaBasedList2`) | 335건 (관광지 41, 문화시설 19, 축제공연행사 23, 레포츠 12, 숙박 37, 쇼핑 117, 음식점 86) |
| 상세 수집 대상 | 275건 (관광지·문화시설·레포츠·쇼핑·음식점) |
| **적재** | **275곳** (건너뜀 0: 허용 문자 밖 contentid 0, 좌표 없음 0, 장소명 없음 0) |
| 제외 (대상 아닌 유형) | 축제공연행사 23, 숙박 37 — 기간 한정 행사·숙소는 놀거리 장소로 넣지 않음 (제안, PM 확인) |
| 호출 수 | 수집 554번 (200 + 200 + 154, 오류 0) + 키 확인 2번 = **556번** |
| 소요 시간 | 수집 약 89초 (30.9 + 33.7 + 24.2초), 적재 0.32초 |
| 재현성 | 같은 원본으로 두 번 만든 DB의 `iterdump`가 같음 (287줄). `SqlitePlaceRepository`로 275곳 모두 읽힘 |

#### ⚠ DEC-018 주소 필수 여부 판단용: **주소 누락 0건 / 275건 (0.0%)**
`addr1`이 빈 장소가 없었습니다. 해운대 표본 기준으로는 DEC-018의 "누락 0건이면 SDD를 NOT NULL로" 조건에 해당합니다. 다른 권역은 확인하지 않았습니다.

| 누락률 (적재 275곳 기준) | 건수 | 비율 |
|---|---|---|
| 주소 | 0 | 0.0% |
| 좌표 | 0 | 0.0% (좌표가 없으면 적재하지 않음) |
| 운영시간 원문 | 1 | 0.4% (소개정보 응답에 항목이 없던 1곳) |
| **운영시간 파싱 성공** | 98 / 274 (원문 있는 곳) | **35.8%** — 나머지는 `open_hours` NULL, 원문만 보존 |
| 가격 원문 | 259 | 94.2% 누락 (가격 필드는 문화시설 `usefee`·레포츠 `usefeeleports`에만 있고, 레포츠는 소개정보가 있는 11곳 모두 빈 값) |
| 개요 | 0 | 0.0% |
| 카테고리 매핑 (OTHER 아님) | 275 | 100% |
| 관람소요시간 (`spendtime`) | 문화시설 19곳 모두 빈 값 → 기본 체류시간 사용 (DEC-018) |
| 실내 여부 | 원본에 필드 없음 → 전부 NULL(미확인) |

운영시간 파싱 규칙 (확실한 것만): 이용시간이 시간 범위 하나(`10:00~18:00`, `10:30-20:00`) 또는 "상시 개방"이고, **쉬는날이 "연중무휴" / 명절만 / "매주 X요일" 하나**일 때만 구조화합니다. 쉬는날이 비어 있으면(쇼핑 48곳) 닫는 요일을 모르므로 매일 영업으로 채우지 않습니다. 원문은 `open_hours_text`에 "이용시간: …\n쉬는날: …"로 저장합니다.

**관찰:** 쇼핑 117곳 중 **112곳이 "사후면세점"**(분류체계 SH040300)입니다. 놀거리 코스 후보로 적절한지 PM 판단이 필요합니다(이번에는 그대로 SHOPPING으로 적재).

### 이슈 #7 "정할 것" 제안

**1. 해운대 중심 좌표** — 표본에서 후보를 골라 반경 1.5 km(DEC-001) 안 장소 수를 비교했습니다 (`SqlitePlaceRepository.find_within_radius`).

| 후보 (데이터에서 고름) | 위도, 경도 | 1.5 km 안 | 쇼핑 제외 |
|---|---|---|---|
| **해운대해수욕장 (contentid 126081)** — 제안 | 35.159084, 129.160279 | 107 | **76** |
| 적재 장소 좌표 중앙값 | 35.166667, 129.158453 | 97 | 63 |
| 1.5 km 안 장소가 가장 많은 점: 외식1번가 (850880, 센텀 쪽) | 35.166395, 129.141645 | 123 | 46 (쇼핑 77곳이 대부분 면세점) |

**2. 카테고리 매핑표** (DEC-013의 7개 값, 위에서부터 처음 맞는 규칙)

| 규칙 | 값 | 표본 건수 |
|---|---|---|
| 분류체계 `FD050100` (카페/찻집 > 카페) | CAFE | 9 |
| 음식점(39) 또는 분류체계 `FD*` | FOOD | 77 |
| 쇼핑(38) 또는 분류체계 `SH*` (관광지 유형의 백화점 1곳 포함) | SHOPPING | 118 |
| 문화시설(14) (미술관·전시관·공연장·도서관·수족관 등) | EXHIBITION | 19 |
| 관광지(12) 중 분류체계 `NA*`(자연관광) 또는 `VE03*`(도시공원) | PARK | 18 |
| 관광지(12)·레포츠(28) 나머지 (전망대·테마파크·요트·체험 등) | ATTRACTION | 34 |
| 그 밖 | OTHER | 0 |

**3. 접근성 등급 규칙** (DEC-015 그대로, 등급은 표시용)
- 정보 없음 → `UNKNOWN`, 휠체어·유모차 **모두 false** → `UNSUITABLE`, **둘 중 하나라도 true** → `VERIFIED`.
- **휠체어·유모차 중 하나가 false이고 나머지가 null인 경우: 문서에 없음** (DEC-015에 규칙 없음, PM 결정 필요).
- 무장애 1건 호출(`detailWithTour2`, contentId 988449 = 포털 Swagger 예시값)로 본 응답 구조: `wheelchair`, `exit`, `elevator`, `restroom`, `parking`, `route`, `stroller` 등 contentid 외 28개 필드가 **모두 자유 문장(빈 문자열 = 정보 없음)**입니다. 예: `wheelchair: "대여가능(수동휠체어 2대)"`(휠체어 **대여** 여부), `exit: "주출입구는 경사로가 있어 휠체어 접근 가능함"`. 따라서 DEC-015의 true/false/null로 바꾸려면 문장 판정 규칙이 필요하고, 휠체어 접근 판단은 `wheelchair` 하나가 아니라 `exit`·`route`·`elevator` 등을 함께 봐야 합니다. 무장애 연결과 등급 산출은 11/16 전후 별도 PR에서 합니다.
- 두 서비스가 같은 contentid를 쓰는지: **문서에 없음.** 이번 1건 호출로는 판단할 수 없습니다(예시 988449는 해운대 목록에 없음). 연결 PR에서 해운대 contentid로 `detailWithTour2`를 호출해 확인할 예정입니다.

### 출처·이용조건

| 항목 | 값 |
|---|---|
| `data_sources.code` | `tourapi-kor` (무장애 `tourapi-barrierfree`는 연결 PR에서 추가) |
| 제공기관·데이터 | 한국관광공사, 국문 관광정보 서비스_GW (KorService2) |
| URL | <https://www.data.go.kr/data/15101578/openapi.do> |
| 조회 시각 (`retrieved_at`) | 마지막 수집 호출 시각 (`data/raw/tourapi/fetch_log.jsonl`) |
| 기준일 (`base_date`) | 문서에 없음 → NULL |
| **이용허락범위 (공공누리 유형)** | **확인 필요** — 담당자가 직접 확인. 위치: 위 두 포털 페이지의 "이용허락범위" 항목, 그리고 장소별 응답 필드 `cpyrhtDivCd`(Swagger 설명 "저작권 유형"). 확인 전까지 `data_sources.license`는 NULL |
