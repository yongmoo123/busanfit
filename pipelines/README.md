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
| 무장애 (원본 수집, 판정 전) | `detailWithTour2` | `contentId` (아래 "무장애 원본 수집" 참고) |

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
| **운영시간 파싱 성공** | 172 / 274 (원문 있는 곳) | **62.8%** (이전 98곳 35.8%) — 나머지 102곳은 `open_hours` NULL, 원문만 보존 |
| 가격 원문 | 259 | 94.2% 누락 (가격 필드는 문화시설 `usefee`·레포츠 `usefeeleports`에만 있고, 레포츠는 소개정보가 있는 11곳 모두 빈 값) |
| 개요 | 0 | 0.0% |
| 카테고리 매핑 (OTHER 아님) | 275 | 100% |
| 관람소요시간 (`spendtime`) | 문화시설 19곳 모두 빈 값 → 기본 체류시간 사용 (DEC-018) |
| 실내 여부 | 원본에 필드 없음 → 전부 NULL(미확인) |

#### 운영시간 파싱 (확실한 것만, `mapping.analyze_open_hours`)

구조와 검증(`validate_open_hours`: 요일 키, `HH:mm`, close에만 `24:00`, 빈 객체 금지)은 그대로이고, 적재한 172곳 모두 검증을 통과합니다. 원문은 `open_hours_text`에 "이용시간: …\n쉬는날: …"로 항상 보존합니다. 보고서(`haeundae_report.json`)의 `open_hours_patterns`·`open_hours_null_reasons`·`open_hours_suspicious`에 아래 건수가 나옵니다.

**구조화하는 패턴** (파싱된 172곳 기준, 한 곳에 여러 패턴 가능)

| 패턴 | 처리 | 건수 |
|---|---|---|
| 마지막 주문·입장·발권 마감 | 그 시각을 그 구간의 close로 씀 — **제안(임시), 팀 확인 대기** | 46 |
| 준비시간(브레이크)·휴게시간 | 하루를 두 구간 이상으로 나눔 | 22 |
| 요일마다 다른 준비시간 (평일·주말 다름, "준비시간(평일)") | 요일별로 따로 나눔 | 6 |
| 평일·주말·요일 범위별 시간 (`[평일]`, `토요일`, `화요일~목요일`, `주말, 공휴일`) | 요일별 시간. 공휴일 시간은 구조 밖이라 무시 | 12 |
| "매일"·"월~일" 접두어 | 매일로 읽음 | 2 |
| ※ 안내 문구 ("자세한 사항은 홈페이지 참조/전화 문의"만) | 무시 | 3 |
| 상시 개방 | 00:00~24:00 | 27 |
| 연중무휴 | 휴무 요일 없음 | 91 |
| 명절·설·추석 휴무 (당일·연휴·전날·전일 및 당일) | 구조에 넣지 않고 원문 보존 | 50 |
| 매주 한 요일 / 여러 요일 휴무 (`매주 월요일, 화요일`, `매주 월요일~목요일`) | 그 요일 `[]` | 23 / 2 |
| 몇째 주·월 1회 + 요일 (`2,4주 월요일`, `월 1회 월요일`, `매달 첫째 월요일`) | **그 요일을 매주 `[]`로** (영업일을 부풀리지 않음) | 9 |

**NULL로 두고 원문만 보존** (102곳)

| 사유 | 건수 |
|---|---|
| 쉬는날 없음 (쇼핑 48곳) — 연중무휴로 채우지 않음 | 48 |
| 불규칙·외부 기준·공휴일 휴무 (부정기, 백화점 휴점일, 공휴일·1월 1일, "단, 공휴일이면 다음날", 휴관 공지, 기상) | 11 |
| 이용시간 상이·문의 (점포·시설·공연별 상이, 전화문의뿐) | 10 |
| 휴무 요일 불명 (`명절, 월 1회`, `월 1회 정기 휴점일`, `매월 1회 휴관`, `정기휴무일`, `연 2회`) | 10 |
| 시설·층별 시간 (`[종합자료실]`, `[1층]`, `[백화점]` 등) | 7 |
| 계절·월별 시간 (`매년 6월~9월`, `[12월~2월]`, 하절기·동절기, 성수기) | 6 |
| 예약제·조건부 시간 (예약제, 견학, 기상악화 운항 불가, 변동 가능) | 5 |
| 해석 불가 (샐러드바 마감, 문구로 바뀌는 준비시간 2곳) | 3 |
| 수상: 영업 요일과 휴무 요일 모순 | 1 |
| 이용시간 없음 | 1 |

**수상한 입력 4건** (NULL, 빌드 로그와 보고서에 건수만): 쉬는날이 비고 `01:00~24:00`인 쇼핑 3곳(위 "쉬는날 없음"에도 포함), 시간을 적은 요일(일요일)이 매주 휴무로도 적힌 1곳.

판단이 들어간 것 (팀 확인 필요): 마지막 주문·입장 마감을 close로 쓰는 것(제안, 임시). 공휴일·1월 1일 휴무는 명절과 달리 NULL로 둠(사용자 지침이 명절만 구조 밖으로 허용). "휴관 시 홈페이지 공지"는 불규칙 휴무로 봄.

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
- 두 서비스가 같은 contentid를 쓰는지: 포털 문서에는 없고, 2026-11-19 해운대 수집으로 **확인**했습니다(아래 "무장애 원본 수집").

## 무장애 원본 수집 (FR-008, 2026-11-19)

`accessibility_collect.py`는 해운대 대상 275곳에 `detailWithTour2`를 한 번씩 호출해 원본을 저장하고, 응답 문장을 **판정 없이** 정리합니다. DB의 `accessibility`(wheelchair·stroller·elevator·accessible_toilet)로 바꾸는 판정은 아래 "무장애 판정과 적재"(DEC-026 초안)를 봅니다.

```text
# 처음 5곳만 (contentid 짝 확인)
.venv/Scripts/python.exe -m pipelines.accessibility_collect fetch --limit 5 --max-calls 5
# 나머지 (이어받기: data/raw/tourapi/accessibility/<contentid>.json 이 있으면 호출하지 않음)
.venv/Scripts/python.exe -m pipelines.accessibility_collect fetch --max-calls 300
# 문장 원문·필드별 빈도표 (네트워크 없음) → data/processed/accessibility_phrases.json
.venv/Scripts/python.exe -m pipelines.accessibility_collect phrases
```

- 대상은 국문 fetch와 같은 규칙(`areaBasedList2` 원본 + 대상 유형 12·14·28·38·39)과 같은 순서입니다.
- 호출 간격 0.5초(`--interval`). 응답이 HTTP 200·`resultCode` 0000이 아니거나 전송 오류가 나면 **그 자리에서 멈추고 재시도하지 않습니다**(한도 초과·인증 오류 포함). 정상 응답은 항목이 비어 있어도 저장합니다(빈 응답 = 정보 없음, 다시 호출하지 않음).
- 호출 기록은 `data/raw/tourapi/accessibility/fetch_log.jsonl` (국문 `fetch_log.jsonl`과 분리해 국문 `retrieved_at`에 섞이지 않게 함).
- 일일 호출 한도: 포털 표 기준 상세기능별 1000회(사용자 확인). 기능 간 합산 여부는 **문서에 없음**.

### 결과

| 항목 | 값 |
|---|---|
| 호출 | **275번** (5 + 270), 성공 275, 실패 0, 약 181초 |
| 응답 항목 있음 | **53 / 275곳 (19.3%)** — 222곳은 정상 응답(0000)이지만 `items`가 빈 값 |
| 유형별 응답 있음 | 관광지 27/41, 문화시설 9/19, 레포츠 4/12, 쇼핑 4/117, 음식점 9/86 |
| contentid 짝 | 응답 `contentid` = 요청 `contentId` = DB `source_place_id` **53/53**. 응답 문장의 지명(죽도공원·동백공원·청사포·벡스코·좌동재래시장 등)도 국문 장소명과 맞음 → 두 서비스가 같은 contentid를 씀 |
| 처음 보는 필드 | 0 (28개 필드 모두 check 응답 988449와 같음) |

**빈 값 비율** (응답 있는 53곳 기준. 275곳 기준이면 모든 필드가 82.5% 이상 비어 있음)

| 필드 | 빈 값 | | 필드 | 빈 값 |
|---|---|---|---|---|
| `exit` | 9.4% | | `wheelchair` ⚠ | 79.2% |
| `route` | 11.3% | | `handicapetc` | 79.2% |
| `parking` | 28.3% | | `lactationroom` | 83.0% |
| `restroom` | 43.4% | | `publictransport` | 84.9% |
| `elevator` | 50.9% | | `stroller` ⚠ | 86.8% |
| 나머지 시각·청각·영유아 필드 | 81%~100% (`ticketoffice`·`promotion`·`room`·`bigprint`·`guidesystem`·`signguide`·`videoguide`·`hearingroom`·`hearinghandicapetc`는 53곳 모두 빈 값) | | | |

⚠ `wheelchair`·`stroller`: 값 18개가 모두 "대여가능(…)" 또는 "안내소에 N대" 같은 **대여 정보**입니다. 접근 가능 판정에 쓰지 않도록 `accessibility_phrases.json`에 `rental_field_not_for_judgement: true`로 표시만 했습니다.

### `accessibility_phrases.json` 구성 (data/processed/, 커밋하지 않음)

- `places`: 장소별 contentid·장소명·유형·DB 존재·응답 유무·contentid 일치, 비어 있지 않은 필드의 **원문 그대로**.
- `type_frequency_by_field`: 필드별 **문장 유형** 빈도. 유형은 뜻을 판정하지 않는 텍스트 정규화로만 묶음 — `<br/>`→공백, 괄호 속 세부(대수·층·위치·문 종류) 제거, 꼬리말 `_무장애 편의시설`·`_시각장애인 편의시설` 제거, 앞 `*`·끝 `.` 제거, 공백 차이 무시. 유형마다 원문 예 3개까지.
- `frequency_by_field`: 필드별 원문(공백만 정리) 빈도. `top_types`: 전체 상위 30개 유형.
- 관찰: "없음"으로 적힌 부정 문장은 거의 없습니다(`handicapetc`의 "전동휠체어 탑승 불가"·"화장실은 공간이 좁아 사용이 어려움" 1곳, `publictransport`의 "저상버스 없음" 1곳). 빈 값은 "없음"이 아니라 **정보 없음**으로 다뤄야 합니다.

### 출처·이용조건

| 항목 | 값 |
|---|---|
| `data_sources.code` | `tourapi-kor` (무장애 `tourapi-barrierfree`는 `accessibility_judge load`가 없을 때만 추가 — 아래 "무장애 판정과 적재") |
| 제공기관·데이터 | 한국관광공사, 국문 관광정보 서비스_GW (KorService2) |
| URL | <https://www.data.go.kr/data/15101578/openapi.do> |
| 조회 시각 (`retrieved_at`) | 마지막 수집 호출 시각 (`data/raw/tourapi/fetch_log.jsonl`) |
| 기준일 (`base_date`) | 문서에 없음 → NULL |
| **이용허락범위 (공공누리 유형)** | **확인 필요** — 담당자가 직접 확인. 위치: 위 두 포털 페이지의 "이용허락범위" 항목, 그리고 장소별 응답 필드 `cpyrhtDivCd`(Swagger 설명 "저작권 유형"). 확인 전까지 `data_sources.license`는 NULL |

## 무장애 판정과 적재 (FR-008, DEC-026 초안)

> **상태: 제안, 세민 확인 대기.** 표현 목록은 DEC-026 확정 전 초안입니다. 확정되면 `accessibility_rules.json`만 고치고 `load`를 다시 실행합니다.
>
> **grade는 #58 정리 전까지 UNKNOWN, 이동제약 판정은 항목값으로만 함(DEC-015).**

```text
# 판정 결과를 data/haeundae_sample.sqlite3의 accessibility에 적재 (멱등)
.venv/Scripts/python.exe -m pipelines.accessibility_judge load
# 집계 보고서 (네트워크 없음) → data/processed/accessibility_judgement.json
.venv/Scripts/python.exe -m pipelines.accessibility_judge report
```

- 규칙은 `pipelines/accessibility_rules.json`에만 있고 `accessibility_judge.py`는 그 파일을 읽어 적용만 합니다. 원본은 `data/raw/tourapi/accessibility/`만 읽고 API를 호출하지 않습니다.
- 규칙 (원문 부분 문자열 일치. 필드 값은 `<br/>`·`.`·`*`·줄바꿈으로 문장 조각을 나눠 봄. 쉼표로는 나누지 않음 — "휠체어, 전동 스쿠터 진입 쉬움"이 한 조각이어야 R1b가 맞음)
  1. **R1** `exit`·`route`에 "턱이 없", "단차가 없", "경사로", "휠체어 접근 가능", "휠체어가 통과 가능", "턱 없", "문턱없", "문턱 없", "휠체어 통과 가능", "휠체어 접근 및 이동 가능" 중 하나 → wheelchair=true, stroller=true. 근거: 무장애 여행 정보의 경사로·턱 없음은 휠체어 접근용 편의시설로 보고, 휠체어가 지나갈 수 있으면 유모차도 지나갈 수 있다고 봄.
     - **R1b** `exit`·`route`의 같은 조각에 "휠체어"와 "진입 쉬움" 또는 "이용 가능"이 함께 → wheelchair=true, stroller=true (부정어가 같은 조각에 있으면 제외).
     - 문 종류만 있는 조각("자동문", "여닫이문", "문의 형태 : 여닫이문", "출입통로 형태 : 상시 개방형" 등)은 판정하지 않고 보고서 `door_only`에 남김.
  2. **R2** `elevator`에 "엘리베이터 있" 또는 "엘리베이터가 있" → elevator=true.
  3. **R3** `restroom`에 "장애인"과 "화장실"이 함께 → accessible_toilet=true.
  4. **R4** 어느 필드든(대여 필드 제외) 한 조각에 부정어("없음"·"불가"·"어려움")와 항목 키워드(휠체어 / 유모차 / 엘리베이터·승강기 / 화장실)가 함께 → 그 항목 false 후보. 같은 항목에 true 근거도 있으면 **null + 충돌**로 raw에 기록. "턱 없음"·"단차 없음" 같은 장벽 없음 표현은 부정어로 보지 않음. 긍정 표현이 부정어와 같은 조각에 있으면(예: "경사로 없음") true로 세지 않고 `negated_positive`로 기록만 함.
     - **R4-manual** `handicapetc`의 "전동휠체어 … 불가" 조각은 자동 판정하지 않고 원문·장소명을 raw와 보고서에 남김.
  5. TourAPI `wheelchair`·`stroller` 필드(대여 정보)는 판정에 쓰지 않음(원문은 raw에 남김).
  6. 응답이 비었거나 어떤 규칙에도 안 맞으면 **null(정보 없음)**. false로 채우지 않음.
  7. grade는 계산하지 않음: 모든 행 `UNKNOWN`, raw에 `"grade_note": "미산정(#58 등급 규칙 정리 전)"`.
  8. **장소별 예외 `overrides`**: 규칙 파일에 장소·항목·값·근거 원문(`evidence`)을 적음. 근거 원문이 해당 필드에 그대로 있을 때만 적용하고, 없으면 적용하지 않고 보고서 `override_missing`에 남김. 적용 내역은 raw `overrides`에 기록.
     - 해운대 블루라인파크(2672393): wheelchair=false. 근거 `handicapetc` "* 전동휠체어 탑승 불가* 수동휠체어는 도움을 받아 휠체어를 접어서 탑승가능". stroller·accessible_toilet은 자동 판정 그대로.
- `load`
  - 처음 실행 때 DB를 `data/haeundae_sample.pre_access.sqlite3`로 복사(이미 있으면 덮어쓰지 않음).
  - `data_sources`에 `tourapi-barrierfree`가 없으면 추가, 있으면 그대로. provider·dataset_name·url은 `accessibility_collect.py`와 같고, `license`(공공누리 유형 확인 전)·`base_date`(문서에 없음)는 NULL, `retrieved_at`은 `accessibility/fetch_log.jsonl`의 정상 응답 중 파일이 있는 것의 가장 늦은 시각.
  - 이 출처의 accessibility 행을 지우고 다시 넣음(한 트랜잭션). 응답이 있는 장소만 행을 만들고, 빈 응답 장소는 행 없음(= API에서 UNKNOWN). raw는 원문 필드·근거 조각·충돌·수동 확인 조각·문 종류 조각·override 내역이며 시각을 넣지 않아 두 번 실행해도 같은 DB.

### 결과 (2026-11-19, 해운대 275곳, 응답 있음 53곳)

| 항목 | true | false | null | 충돌 |
|---|---|---|---|---|
| wheelchair | 47 | 1 | 227 | 0 |
| stroller | 48 | 0 | 227 | 0 |
| elevator | 26 | 0 | 249 | 0 |
| accessible_toilet | 30 | 1 | 244 | 0 |

- 규칙별 장소 수: R1 47, R1b 4, R2 26, R3 30, R4 1, R4-manual 1, override 1. R1 표현별: "턱이 없" 29, "단차가 없" 6, "경사로" 17, "휠체어 접근 가능" 40, "휠체어가 통과 가능" 2, "턱 없" 2, "문턱없" 1, "문턱 없" 0, "휠체어 통과 가능" 1, "휠체어 접근 및 이동 가능" 1 (한 장소가 여러 표현에 맞을 수 있음).
- 유형별 wheelchair true: 관광지 24, 문화시설 8, 레포츠 3, 쇼핑 4, 음식점 8.
- 해운대해수욕장(35.159084, 129.160279) 반경 1500m 안이고 `open_hours`가 NULL이 아닌 77곳 중 wheelchair true 11, stroller true 11.
- wheelchair false 1곳은 블루라인파크 override. accessible_toilet false 1곳은 같은 장소 `handicapetc`의 "화장실은 공간이 좁아 사용이 어려움"(R4).
- 여전히 규칙에 안 맞는 exit·route 문장: 누리마루 APEC하우스 `exit` "동백공원 장애인 전용주차장에서 출발해 산책로 아래쪽 도로를 따라온 탐방객은 1층 엘리베이터를 이용해 3층 전시 공간으로 진입" 1건. 문 종류만 있는 조각 5건은 `door_only`.
