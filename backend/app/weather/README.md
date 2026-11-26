# 날씨 — 이찬용

FR-016 (Should), 이슈 #33 **A단계(날씨 데이터·판정)**. 관련: UC-003 2단계·2a, SDD COMP-12, DEC-010, DEC-028.

**아직 아무 곳에도 연결하지 않았다.** `capabilities.supportsWeather`는 `false` 그대로다. 판정 기준은 **DEC-034**(PM 11/24,
PR #87 승인 리뷰, 기록 PR #90)로 확정됐고 `config/weather.json`은 `status: APPROVED`, `pmApproved: true`다.
실외 장소 목록은 `config/outdoor-places.json`(DEC-034 4)이다.

## 파일

| 파일 | 내용 |
|---|---|
| `grid.py` | 위경도 → 기상청 격자(nx, ny). 활용가이드 LCC 변환, 서울시청 → (60, 127) 확인 |
| `settings.py` | `config/weather.json` 읽기·검사, 권역 격자 계산(`config/retrieval.json` `areaCenters`), `KMA_SERVICE_KEY` 읽기 |
| `kma_client.py` | 기상청 API 호출(urllib). 키 마스킹, 결과 코드·형식 검사 |
| `judge.py` | 결과 형식(`AreaWeather`, `HourlyJudgement`, `ActiveWarning`)과 순수 판정 함수 |
| `provider.py` | `WeatherProvider.area_weather(권역, 방문일, 시각들)` — 범위·키 확인 → 조회 → 판정 |
| `outdoor.py` | `outdoor_status(place)` → `OUTDOOR` / `UNKNOWN`, `place_weather(place, 시각 판정)` → 장소에 적용한 판정 |
| `pipelines/outdoor_ids.py` | 분류 코드 규칙으로 실외 장소 ID 목록 파일 생성(사후면세점 목록과 같은 방식) |

## 실제 응답으로 확인한 것 (2026-11-24, 서비스별 1회 호출)

응답 원본은 저장소에 넣지 않았다. 테스트 고정 응답(`backend/tests/fixtures/kma/*_virtual.json`)은 같은 구조에 `[가상]` 값이다.

- **단기예보** `VilageFcstInfoService_2.0/getVilageFcst` (base 20261124 0200, 해운대 격자 99·75)
  - `response.header.resultCode "00"`, `response.body.items.item[]`: `baseDate, baseTime, category, fcstDate, fcstTime, fcstValue, nx, ny`
  - category 14종: TMP UUU VVV VEC **WSD SKY** PTY **POP** WAV PCP REH SNO (시각별) + TMN TMX (하루 1개). PCP·SNO는 "강수없음" 같은 글자
  - 제공 기간: 오늘 03시 ~ 모레 23시 **1시간 간격**, 글피는 **3시간 간격**(00·03·…·21시), 글피 다음날 00시 1개. 944행(numOfRows 1000이면 한 번에)
  - SKY 값: 1·3·4 (맑음·구름많음·흐림)
  - base_time: 0200·0500·…·2300(3시간 간격), 발표 10분 뒤부터 받는다고 보고(`availableAfterMin`, 활용가이드 기준) 가장 최근 발표를 쓴다. 02:10 전이면 전날 2300
- **기상특보** `WthrWrnInfoService/getPwnCd` (특보코드조회, fromTmFc 20261117 ~ toTmFc 20261124, 구역 지정 없음)
  - 같은 머리부, item: `areaCode, areaName, warnVar, warnStress, command, cancel, startTime, endTime, allEndTime, tmFc, tmSeq, stnId`
  - 7일 전국 528건, 모두 stnId 108. warnVar 관측 값 1·2·3·4·6·8, command 관측 값 1·2·3·7, cancel은 모두 "0"
  - command 1(발표)은 `startTime`만 있고 281건 중 137건은 발표 시각보다 늦다(**발효 예정**). command 2(해제)는 `endTime`만 있고
    191건 중 59건은 발표 시각보다 늦다(**해제 예정**). 3(연장)·7(변경발표)은 `startTime` = 발표 시각
  - command 7은 같은 구역·종류의 주의보 → 경보, 경보 → 주의보 변경이고, 바뀌기 전 강도의 해제 기록은 따로 오지 않는다
  - 부산 구역: **S1311100 부산앞바다**(해상)만 확인. **부산 육상 특보구역 코드는 이 기간 기록이 없어 확인하지 못했다.** 그래서 코드 대신 이름이 "부산"으로 시작하고 "바다"가 없는 구역의 특보를 4개 권역 모두에 적용한다(보수적, PM 확인 항목)
  - 같은 서비스의 다른 오퍼레이션(특보목록·통보문·현황 등)은 호출하지 않았다(서비스당 1회). 판정에는 getPwnCd만 쓴다

## 결과 형식

```python
AreaWeather(
    area="HAEUNDAE", visit_date=date(2026, 11, 25),
    status="APPLIED" | "NOT_APPLIED",
    not_applied_reason=None | "NO_KEY" | "OUT_OF_RANGE" | "FETCH_FAILED" | "INVALID_RESPONSE" | "INCOMPLETE_FORECAST",
    verdict=None | "OK" | "PENALIZE_OUTDOOR" | "EXCLUDE_OUTDOOR",   # 시각별 중 가장 심한 것
    reasons=("POP_HIGH", "SKY_OVERCAST", "WIND_STRONG", "WARNING_HEAVY_RAIN", "WARNING_COLD_WAVE", "WARNING_TYPHOON",
             "WARNING_HEAVY_SNOW", "WARNING_HEAT_WAVE", "WARNING_STRONG_WIND", "WARNING_UNCHECKED"),
    hours=(HourlyJudgement(hour=13, verdict=..., reasons=..., pop=20, sky="1", wind_mps=2.0, pty="0", temperature_c=12.0), ...),
    grid=(99, 75), base_date="20261124", base_time="0200",
    warning_check="CHECKED" | "NOT_CHECKED_FUTURE" | "FAILED" | "INCOMPLETE" | "NOT_CHECKED",
    active_warnings=(ActiveWarning(..., effect="EXCLUDE" | "PENALIZE", starts_at=..., ends_at=None | ...), ...),
    settings_status="APPROVED", detail=None | "실패 내용(키·URL 없음)",
)
```

판정 (`config/weather.json`, DEC-034):

| 조건 | 판정 |
|---|---|
| 강수확률(POP) ≥ 60 | `EXCLUDE_OUTDOOR` (HARD) |
| 폭염(12)·한파(3)·호우(2)·대설(8)·태풍(7) 특보가 그 시각에 발효 중 — **방문일이 오늘일 때만 확인** | `EXCLUDE_OUTDOOR` (HARD) |
| 하늘상태(SKY) 4 흐림 | `PENALIZE_OUTDOOR` (SOFT) |
| 풍속(WSD) ≥ 9 m/s, 강풍(1) 특보가 그 시각에 발효 중 | `PENALIZE_OUTDOOR` (SOFT) |

강수형태(PTY)는 판정에 쓰지 않는다(표시용으로만 보관).

### 특보 시각 판정 (`judge.busan_warning_tracks`)

필드 의미는 공공데이터포털 [기상청_기상특보 조회서비스 명세](https://www.data.go.kr/data/15000415/openapi.do) 특보코드조회:
command `1-발표, 2-해제, 3-연장, 6-정정, 7-변경발표, 8-변경해제`, cancel `0-정상, 1-취소된 특보`,
startTime `발표발효시각(특보발표시에만 제공)`, endTime `해제발효시각(특보해제시에만 제공)`.

- 구역·특보 종류별로 발표 순서(tmFc, tmSeq)대로 적용한다. 주의보·경보는 나누지 않는다(7 변경발표 뒤에 이전 강도의 해제가 오지 않음).
- 발표(1·3·7)는 **startTime부터**, 해제(2·8)는 **endTime부터** 효력. 뒤 발표가 앞의 예정을 덮어쓴다.
- `cancel` 1(취소된 특보)은 효력 없는 기록이라 무시한다.
- 방문 시각마다 `[HH:00, HH+1:00)`에 효력이 있으면 그 시각에만 제외·감점한다.
  예: 21시 발효 예정 한파 특보는 13~18시 방문에 적용하지 않는다. 21시 해제 예정 특보는 13시에 아직 유효하다.
- 필요한 시각이 없는 기록, 6(정정)이나 명세에 없는 command는 상태를 정하지 않는다. 그 발표 시각부터 다음 기록까지 해당 시각에
  `WARNING_UNCHECKED`를 붙이고 `warning_check="INCOMPLETE"`로 둔다(제외도 무시도 하지 않음).

- 범위 밖(오늘 전, 오늘 + 2일 뒤)은 **호출 없이** `NOT_APPLIED(OUT_OF_RANGE)`. 키가 없으면 **호출 없이** `NOT_APPLIED(NO_KEY)`.
- 요청한 시각 중 하나라도 POP·SKY·WSD가 없거나 숫자가 아니거나 결측(±900)이면 `NOT_APPLIED`. 맑음·0으로 채우지 않는다.
- 한 페이지가 numOfRows만큼 꽉 차면 잘렸을 수 있으므로 `INVALID_RESPONSE`.

## 사용 예시

```python
from datetime import date
from app.weather.provider import WeatherProvider
from app.weather.outdoor import outdoor_status, OUTDOOR

provider = WeatherProvider()            # config/weather.json + KMA_SERVICE_KEY(환경변수 → .env)
weather = provider.area_weather("HAEUNDAE", date(2026, 11, 25), range(13, 19))
if not weather.applied:
    print("날씨 미반영:", weather.not_applied_reason)
else:
    for hour in weather.hours:
        print(hour.hour, hour.verdict, hour.reasons)

outdoor_status(place)                   # PlaceRecord 또는 "tourapi-kor:126078" → "OUTDOOR" / "UNKNOWN"
```

실외 장소 목록 다시 만들기(원본 목록 `data/raw/tourapi`가 있어야 함, API 호출 없음):

```text
.venv/Scripts/python.exe pipelines/outdoor_ids.py
.venv/Scripts/python.exe pipelines/outdoor_ids.py --check
```

## 실외 판정 (DEC-034 4·5)

`places.indoor`는 630곳 모두 NULL이고 바꾸지 않는다. TourAPI 분류 코드(`lclsSystm3`) 접두어로 **확실한 실외만** `OUTDOOR`:
`NA`(자연관광: 섬·항구·해수욕장·생태관광지), `VE03`(도시공원), `VE0401`(골목길·문화거리), `VE0103`(다리·대교).

- **먹자골목 3곳**(부평족발골목·부산 자갈치 양곱창 골목·서면먹자골목)은 활동이 식당 안이라 규칙에 맞아도 뺀다.
  규칙은 그대로 두고 `outdoorBy.excludePlaceIds`에 이유와 함께 적는다(목록 파일 `excludedPlaces`).
- 실외 29곳: 해운대 6, 서면 7, 광안리 6, 남포 10. 이 중 코스 후보(193곳)에 드는 곳은 23곳(해운대 5, 서면 4, 광안리 6, 남포 8).
- 애매한 코드(`outdoorBy.needsDecision`, 44곳)와 나머지는 `UNKNOWN`(실내라는 뜻이 아님).
- **`UNKNOWN` 장소는 날씨로 제외도 감점도 하지 않는다.** `place_weather()`는 `verdict="OK"`, `reasons=("OUTDOOR_UNKNOWN",)`를
  돌려준다. B단계는 이 이유로 "실내·실외 정보가 없는 장소는 날씨를 반영하지 않았어요" 경고를 붙인다.

## B단계 연결 방법 (김영무, 11/25 판단 후)

1. 코스 요청 처리에서 방문일·시간대·권역이 정해진 뒤 `WeatherProvider.area_weather(area, visit_date, 방문 시각들)`을 한 번 부른다.
   provider는 요청 범위(또는 짧은 TTL)로 만든다. 같은 발표·격자 예보와 같은 날 특보는 provider 안에서 한 번만 호출한다.
2. `status == "NOT_APPLIED"`이면 날씨 없이 코스를 만들고 경고("날씨 미반영", 이유 코드)를 응답에 넣는다(UC-003 2a).
3. `APPLIED`이면 후보마다 그 장소 방문 시각의 `HourlyJudgement`로 `place_weather(place, judgement)`를 부른다:
   - `verdict == EXCLUDE_OUTDOOR` → 후보 제외(HARD). 제외 건수·이유를 남긴다
   - `PENALIZE_OUTDOOR` → 순위 감점(SOFT, 감점 크기는 코스 엔진 설정)
   - `reasons`에 `WARNING_UNCHECKED` → "특보 미확인" 경고
   - `reasons`에 `OUTDOOR_UNKNOWN` → 제외·감점 없음, "실내·실외 정보가 없는 장소는 날씨를 반영하지 않았어요" 경고 (DEC-034 5)
4. 연결할 때 계약(`capabilities.supportsWeather`, 경고 코드)·SDD COMP-12·테스트를 같은 PR에서 고친다.
   비 예보는 고정 응답 테스트로 확인한다(PM, 실제 날씨는 11/24 확인 때 모두 맑음).

## C단계 (배진호)

응답 경고로 "날씨 미반영(이유)" 안내, 적용 시 시간대별 날씨 요약(강수확률·하늘·풍속)과 제외·감점된 실외 장소 표시, 조정 칩 ③.

## 결정 (DEC-034, 2026-11-24)

1. 판정 기준: 위 표. 강수형태(PTY)는 쓰지 않는다
2. 예보 범위: 모레까지(1시간 간격). 그 뒤는 "날씨 미반영"
3. 부산 육상 특보구역 코드 미확인 → 이름 매칭·4개 권역 공통 적용
4. 실외 판정은 분류 코드로 확실한 실외만, 먹자골목 3곳 제외
5. 판단 필요·`UNKNOWN`은 제외·감점 없이 경고
