"""FR-016 #33 A단계: 날씨 격자·설정·판정·기상청 클라이언트·실외 판정. 네트워크를 쓰지 않는다.

기상청 응답은 ``fixtures/kma``의 [가상] 고정 응답(실제 응답 구조, 만든 값)만 쓴다. 키도 [가상] 문자열이다.
"""
from __future__ import annotations

import copy
from datetime import date, datetime
import io
import json
from pathlib import Path
import shutil
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import pytest

from app.weather import judge, kma_client, outdoor
from app.weather.grid import to_grid
from app.weather.judge import (APPLIED, EXCLUDE_OUTDOOR, NOT_APPLIED, OK, PENALIZE_OUTDOOR, POP_HIGH,
                               SKY_OVERCAST, WARNING_UNCHECKED, WIND_STRONG)
from app.weather.provider import KST, WeatherProvider, latest_base
from app.weather.settings import (CONFIG_DIR, ENV_KEY, WeatherSettingsError, load_service_key,
                                  load_weather_settings)
from pipelines import outdoor_ids

FIXTURES = Path(__file__).parent / "fixtures" / "kma"
FAKE_KEY = "VIRTUAL-KMA-KEY-0000/+=="   # [가상] 키. '/', '+', '='는 인코딩 확인용
NOW = datetime(2026, 11, 24, 4, 9, tzinfo=KST)   # 02시 발표를 받을 수 있는 시각
TODAY, TOMORROW = date(2026, 11, 24), date(2026, 11, 25)
AFTERNOON = range(13, 19)   # 13~18시


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("tests must not use the network")
    monkeypatch.setattr(kma_client, "urlopen", refuse)


@pytest.fixture(scope="module")
def settings():
    return load_weather_settings()


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200):
        super().__init__(body)
        self.status = status


class FakeKma:
    """URL의 오퍼레이션 이름으로 응답을 고른다. 받은 URL을 기록한다."""

    def __init__(self, forecast=None, warnings=None):
        self.forecast = fixture("vilage_fcst_virtual.json") if forecast is None else forecast
        self.warnings = fixture("pwn_cd_virtual.json") if warnings is None else warnings
        self.urls: list[str] = []

    def __call__(self, request, timeout):
        self.urls.append(request.full_url)
        answer = self.forecast if "getVilageFcst" in request.full_url else self.warnings
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, bytes):
            return FakeResponse(answer)
        return FakeResponse(json.dumps(answer, ensure_ascii=False).encode("utf-8"))

    def operations(self) -> list[str]:
        return [urlsplit(u).path.rsplit("/", 1)[-1] for u in self.urls]


def provider(settings, fake=None, key=FAKE_KEY, now=NOW):
    return WeatherProvider(settings, key, read_key=False, opener=fake, clock=lambda: now)


# --- 격자·설정 ---------------------------------------------------------------

def test_grid_matches_guide_reference_point():
    assert to_grid(37.5665, 126.9780) == (60, 127)   # 활용가이드 예시와 같은 서울시청 격자


def test_area_grids_come_from_area_centers(settings):
    assert settings.area_grids == {"HAEUNDAE": (99, 75), "GWANGALLI": (99, 75),
                                   "SEOMYEON": (98, 75), "NAMPO": (97, 74)}
    assert len(set(settings.area_grids.values())) == 3


@pytest.mark.parametrize("bad", [float("nan"), True, "35.1"])
def test_grid_rejects_non_numbers(bad):
    with pytest.raises(ValueError):
        to_grid(bad, 129.0)


def test_shipped_settings_are_an_unapproved_proposal(settings):
    assert settings.status == "PROPOSAL" and settings.pm_approved is False
    assert settings.pop_exclude_gte == 60
    assert settings.sky_penalize == frozenset({"4"})
    assert settings.wind_penalize_gte == 9.0
    assert settings.max_days_ahead == 2
    assert settings.warning_exclude == {"3": "WARNING_COLD_WAVE", "12": "WARNING_HEAT_WAVE"}


def copy_config(tmp_path: Path) -> Path:
    for name in ("weather.json", "retrieval.json"):
        shutil.copy(CONFIG_DIR / name, tmp_path / name)
    return tmp_path


@pytest.mark.parametrize("edit", [
    lambda c: c["thresholds"]["excludeOutdoor"].update(popGte=150),
    lambda c: c["thresholds"]["penalizeOutdoor"].update(windSpeedGteMps="9"),
    lambda c: c["forecast"].update(baseTimes=["2am"]),
    lambda c: c.update(pmApproved="no"),
    lambda c: c.pop("warnings"),
])
def test_broken_settings_are_an_error_not_a_default(tmp_path, edit):
    config_dir = copy_config(tmp_path)
    config = json.loads((config_dir / "weather.json").read_text(encoding="utf-8"))
    edit(config)
    (config_dir / "weather.json").write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(WeatherSettingsError):
        load_weather_settings(config_dir)


def test_missing_settings_file_is_an_error(tmp_path):
    with pytest.raises(WeatherSettingsError):
        load_weather_settings(tmp_path)


# --- 서비스키 ------------------------------------------------------------------

def test_key_from_environment_wins_over_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(f"{ENV_KEY}=FROM-FILE-[가상]\n", encoding="utf-8")
    assert load_service_key({ENV_KEY: "FROM-ENV-[가상]"}, env_file) == "FROM-ENV-[가상]"
    assert load_service_key({}, env_file) == "FROM-FILE-[가상]"
    assert load_service_key({ENV_KEY: "  "}, env_file) == "FROM-FILE-[가상]"


def test_missing_key_is_none(tmp_path):
    assert load_service_key({}, tmp_path / "absent.env") is None
    assert load_service_key({}, None) is None


def test_no_key_returns_not_applied_without_calling(settings):
    fake = FakeKma()
    result = provider(settings, fake, key=None).area_weather("HAEUNDAE", TOMORROW, AFTERNOON)
    assert (result.status, result.not_applied_reason) == (NOT_APPLIED, judge.NO_KEY)
    assert result.verdict is None and result.hours == ()
    assert fake.urls == []


# --- 발표시각·범위 ------------------------------------------------------------

@pytest.mark.parametrize("now, expected", [
    (datetime(2026, 11, 24, 4, 9, tzinfo=KST), ("20261124", "0200")),
    (datetime(2026, 11, 24, 2, 10, tzinfo=KST), ("20261124", "0200")),
    (datetime(2026, 11, 24, 2, 9, tzinfo=KST), ("20261123", "2300")),
    (datetime(2026, 11, 24, 23, 59, tzinfo=KST), ("20261124", "2300")),
    (datetime(2026, 11, 24, 5, 0, 0, tzinfo=KST).astimezone(), ("20261124", "0200")),
])
def test_latest_base(settings, now, expected):
    assert latest_base(now, settings) == expected


@pytest.mark.parametrize("visit", [date(2026, 11, 23), date(2026, 11, 27), date(2026, 12, 31)])
def test_out_of_range_returns_not_applied_without_calling(settings, visit):
    fake = FakeKma()
    result = provider(settings, fake).area_weather("HAEUNDAE", visit, AFTERNOON)
    assert (result.status, result.not_applied_reason) == (NOT_APPLIED, judge.OUT_OF_RANGE)
    assert fake.urls == []


@pytest.mark.parametrize("hours", [[], [24], [-1], ["13"], [13.0]])
def test_bad_hours_are_a_caller_error(settings, hours):
    with pytest.raises(ValueError):
        provider(settings, FakeKma()).area_weather("HAEUNDAE", TOMORROW, hours)


def test_unknown_area_is_a_caller_error(settings):
    with pytest.raises(ValueError):
        provider(settings, FakeKma()).area_weather("GIJANG", TOMORROW, AFTERNOON)


# --- 판정 ----------------------------------------------------------------------

def test_tomorrow_hourly_judgement(settings):
    fake = FakeKma()
    result = provider(settings, fake).area_weather("HAEUNDAE", TOMORROW, AFTERNOON)
    assert result.status == APPLIED and result.applied
    by_hour = {h.hour: (h.verdict, h.reasons) for h in result.hours}
    assert by_hour == {
        13: (OK, ()),
        14: (PENALIZE_OUTDOOR, (SKY_OVERCAST,)),
        15: (PENALIZE_OUTDOOR, (WIND_STRONG,)),
        16: (EXCLUDE_OUTDOOR, (POP_HIGH, SKY_OVERCAST)),
        17: (OK, ()),                                    # 59%, 구름많음, 8.9 m/s: 모두 경계 아래
        18: (EXCLUDE_OUTDOOR, (POP_HIGH, SKY_OVERCAST, WIND_STRONG)),
    }
    assert result.verdict == EXCLUDE_OUTDOOR
    assert (result.base_date, result.base_time, result.grid) == ("20261124", "0200", (99, 75))
    assert result.settings_status == "PROPOSAL"


def test_future_date_skips_warnings_and_says_so(settings):
    fake = FakeKma()
    result = provider(settings, fake).area_weather("HAEUNDAE", TOMORROW, [13])
    assert fake.operations() == ["getVilageFcst"]
    assert result.warning_check == judge.WARNING_NOT_CHECKED_FUTURE
    assert WARNING_UNCHECKED in result.reasons and result.verdict == OK


def test_forecast_request_parameters_and_key_encoding(settings):
    fake = FakeKma()
    provider(settings, fake).area_weather("NAMPO", TOMORROW, AFTERNOON)
    query = parse_qs(urlsplit(fake.urls[0]).query)
    assert {k: v[0] for k, v in query.items() if k != "serviceKey"} == {
        "pageNo": "1", "numOfRows": "1000", "dataType": "JSON", "base_date": "20261124",
        "base_time": "0200", "nx": "97", "ny": "74"}
    assert query["serviceKey"] == [FAKE_KEY]
    assert "%2F" in fake.urls[0] and "%2B" in fake.urls[0]   # 한 번만 인코딩
    encoded = provider(settings, FakeKma(), key="VIRTUAL-KMA-KEY-0000%2F%2B%3D%3D")
    encoded._client._open = fake
    encoded.area_weather("NAMPO", TOMORROW, AFTERNOON)
    assert fake.urls[0] == fake.urls[1]


def test_same_grid_is_called_once(settings):
    fake = FakeKma()
    p = provider(settings, fake)
    results = p.areas_weather(["HAEUNDAE", "GWANGALLI"], TOMORROW, AFTERNOON)
    assert fake.operations() == ["getVilageFcst"] and p.calls == 1
    assert results["HAEUNDAE"].hours == results["GWANGALLI"].hours


def test_today_checks_busan_land_warnings(settings):
    fake = FakeKma()
    result = provider(settings, fake).area_weather("HAEUNDAE", TODAY, [13, 14])
    assert fake.operations() == ["getVilageFcst", "getPwnCd"]
    query = parse_qs(urlsplit(fake.urls[1]).query)
    assert (query["fromTmFc"], query["toTmFc"]) == (["20261117"], ["20261124"])
    assert result.warning_check == judge.WARNING_CHECKED
    assert WARNING_UNCHECKED not in result.reasons
    # 한파는 해제됨, 앞바다·다른 지역은 무시, 강풍은 정보만(판정 영향 없음)
    assert [(w.area_name, w.warn_name) for w in result.active_warnings] == [("부산서부[가상]", "강풍")]
    assert result.verdict == OK


def test_active_cold_wave_warning_excludes_outdoor(settings):
    warnings = fixture("pwn_cd_virtual.json")
    items = warnings["response"]["body"]["items"]["item"]
    items[:] = [i for i in items if i["command"] != "2"]   # 해제 기록을 빼면 한파주의보가 발효 중
    forecast = fixture("vilage_fcst_virtual.json")
    for item in forecast["response"]["body"]["items"]["item"]:
        item["nx"] = 98                                     # 서면 격자로 옮김
    result = provider(settings, FakeKma(forecast, warnings)).area_weather("SEOMYEON", TODAY, [13])
    assert result.grid == (98, 75)
    # 격자가 달라도 부산 육상 특보는 모든 권역에 적용(구역 코드 미확인, 보수적)
    assert result.hours[0].reasons == ("WARNING_COLD_WAVE",)
    assert result.verdict == EXCLUDE_OUTDOOR


def test_warning_no_data_means_checked_and_none(settings):
    no_data = {"response": {"header": {"resultCode": "03", "resultMsg": "NO_DATA"}}}
    result = provider(settings, FakeKma(warnings=no_data)).area_weather("HAEUNDAE", TODAY, [13])
    assert result.warning_check == judge.WARNING_CHECKED and result.active_warnings == ()


def test_today_warning_failure_is_reported_not_ignored(settings):
    fake = FakeKma(warnings=URLError("[가상] down"))
    result = provider(settings, fake).area_weather("HAEUNDAE", TODAY, [13])
    assert result.status == APPLIED
    assert result.warning_check == judge.WARNING_CHECK_FAILED
    assert WARNING_UNCHECKED in result.reasons


# --- 실패·형식 오류 → NOT_APPLIED ----------------------------------------------

GATEWAY_XML = (b"<OpenAPI_ServiceResponse><cmmMsgHeader><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR"
               b"</returnAuthMsg><returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>")


@pytest.mark.parametrize("answer, reason", [
    (URLError("[가상] timeout"), judge.FETCH_FAILED),
    (TimeoutError(), judge.FETCH_FAILED),
    (HTTPError("http://x", 500, "err", {}, io.BytesIO(b"")), judge.FETCH_FAILED),
    (GATEWAY_XML, judge.FETCH_FAILED),
    ({"response": {"header": {"resultCode": "10", "resultMsg": "INVALID_REQUEST_PARAMETER_ERROR"}}},
     judge.FETCH_FAILED),
    ({"response": {"body": {}}}, judge.INVALID_RESPONSE),
    ({"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": "x"}}}}, judge.INVALID_RESPONSE),
])
def test_fetch_failures_are_not_applied(settings, answer, reason):
    result = provider(settings, FakeKma(forecast=answer)).area_weather("HAEUNDAE", TOMORROW, AFTERNOON)
    assert (result.status, result.not_applied_reason) == (NOT_APPLIED, reason)
    assert result.verdict is None and result.hours == ()
    assert FAKE_KEY not in (result.detail or "") and "serviceKey" not in (result.detail or "")


def test_failure_is_not_cached(settings):
    fake = FakeKma(forecast=URLError("[가상]"))
    p = provider(settings, fake)
    assert p.area_weather("HAEUNDAE", TOMORROW, [13]).not_applied_reason == judge.FETCH_FAILED
    fake.forecast = fixture("vilage_fcst_virtual.json")
    assert p.area_weather("HAEUNDAE", TOMORROW, [13]).status == APPLIED
    assert p.calls == 2


def test_full_page_is_treated_as_truncated(settings):
    forecast = fixture("vilage_fcst_virtual.json")
    items = forecast["response"]["body"]["items"]["item"]
    items.extend(copy.deepcopy(items[0]) for _ in range(1000 - len(items)))
    result = provider(settings, FakeKma(forecast=forecast)).area_weather("HAEUNDAE", TOMORROW, [13])
    assert result.not_applied_reason == judge.INVALID_RESPONSE


def test_missing_hour_is_incomplete_not_filled(settings):
    result = provider(settings, FakeKma()).area_weather("HAEUNDAE", TOMORROW, [18, 19])
    assert (result.status, result.not_applied_reason) == (NOT_APPLIED, judge.INCOMPLETE_FORECAST)


def test_other_grid_items_are_not_used(settings):
    # 고정 응답은 (99, 75) 격자뿐이다. 서면(98, 75)으로 받으면 쓸 값이 없다.
    result = provider(settings, FakeKma()).area_weather("SEOMYEON", TOMORROW, [13])
    assert result.not_applied_reason == judge.INCOMPLETE_FORECAST


@pytest.mark.parametrize("value", ["강수없음", "", "900", "-999"])
def test_unusable_values_are_invalid_not_zero(settings, value):
    forecast = fixture("vilage_fcst_virtual.json")
    for item in forecast["response"]["body"]["items"]["item"]:
        if item["category"] == "POP" and item["fcstDate"] == "20261125" and item["fcstTime"] == "1300":
            item["fcstValue"] = value
    result = provider(settings, FakeKma(forecast=forecast)).area_weather("HAEUNDAE", TOMORROW, [13])
    assert (result.status, result.not_applied_reason) == (NOT_APPLIED, judge.INVALID_RESPONSE)


def test_key_never_in_repr(settings):
    p = provider(settings, FakeKma())
    assert FAKE_KEY not in repr(p) and FAKE_KEY not in repr(p._client)
    assert kma_client.mask_url(f"https://x/y?a=1&serviceKey={FAKE_KEY}&b=2") == "https://x/y?a=1&serviceKey=***&b=2"


# --- 실외 판정 -------------------------------------------------------------------

def test_outdoor_status_of_shipped_list():
    shipped = outdoor.load_outdoor_list()
    assert outdoor.outdoor_status("tourapi-kor:126078", shipped) == outdoor.OUTDOOR    # 광안리해수욕장(NA020900)
    assert outdoor.outdoor_status("tourapi-kor:999999999", shipped) == outdoor.UNKNOWN

    class Place:
        id = "tourapi-kor:126078"
    assert outdoor.outdoor_status(Place(), shipped) == outdoor.OUTDOOR
    assert outdoor.outdoor_status("tourapi-kor:126078") == outdoor.OUTDOOR             # 기본 목록


def test_outdoor_status_rejects_non_ids():
    with pytest.raises(TypeError):
        outdoor.outdoor_status(126078, outdoor.OutdoorList(frozenset(), "x"))


def test_missing_outdoor_list_is_an_error(tmp_path):
    shutil.copy(CONFIG_DIR / "weather.json", tmp_path / "weather.json")
    with pytest.raises(WeatherSettingsError):
        outdoor.load_outdoor_list(tmp_path)


def test_shipped_outdoor_list_follows_rules():
    prefixes, undecided, path = outdoor_ids.load_rules()
    listed = json.loads(path.read_text(encoding="utf-8"))
    assert listed["criterion"]["codePrefixes"] == prefixes
    assert listed["status"].startswith("PROPOSAL")
    assert listed["count"] == len(listed["places"]) == sum(listed["countByArea"].values())
    assert all(any(p["code"].startswith(x) for x in prefixes) for p in listed["places"])
    assert all(p["code"] in undecided for p in listed["needsDecisionPlaces"])
    assert not {p["placeId"] for p in listed["places"]} & {p["placeId"] for p in listed["needsDecisionPlaces"]}


CENTERS = {"SEOMYEON": (35.15, 129.05), "GWANGALLI": (35.15, 129.10)}  # [가상] 중심
RADIUS = 1500.0


def listed_item(cid, type_id, lat, code, title=None):
    return {"contentid": cid, "contenttypeid": type_id, "mapy": str(lat), "mapx": "129.05",
            "lclsSystm3": code, "title": title or f"[가상] 장소 {cid}"}


def test_outdoor_ids_build():
    prefixes = {"NA": "자연", "VE03": "도시공원", "VE0401": "거리", "VE0103": "다리"}
    undecided = {"VE010200": "전망대"}
    items = [listed_item("1", "12", 35.151, "NA020900"),   # 해수욕장 → 실외
             listed_item("2", "12", 35.152, "VE030100"),   # 공원 → 실외
             listed_item("3", "12", 35.153, "VE040100"),   # 거리 → 실외
             listed_item("4", "12", 35.154, "VE010300"),   # 다리 → 실외
             listed_item("5", "12", 35.155, "VE010200"),   # 전망대 → 판단 필요
             listed_item("6", "39", 35.156, "FD010100"),   # 식당 → 목록 없음
             listed_item("7", "12", 35.30, "NA020900"),    # 원 밖
             listed_item("8", "15", 35.151, "NA020900")]   # 대상 유형 아님(축제)
    result = outdoor_ids.build({i["contentid"]: i for i in items}, CENTERS, RADIUS, prefixes, undecided)
    assert [p["placeId"] for p in result["places"]] == [f"tourapi-kor:{n}" for n in "1234"]
    assert result["countByArea"] == {"SEOMYEON": 4}
    assert [p["placeId"] for p in result["needsDecisionPlaces"]] == ["tourapi-kor:5"]
    assert result["targetsInCircles"] == 6


def test_needs_decision_code_cannot_also_be_outdoor(tmp_path):
    config = json.loads((CONFIG_DIR / "weather.json").read_text(encoding="utf-8"))
    config["outdoorBy"]["needsDecision"]["NA020900"] = "[가상] 겹침"
    path = tmp_path / "weather.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError):
        outdoor_ids.load_rules(path)


# --- 연결하지 않음(A단계) -----------------------------------------------------------

def test_weather_module_is_not_connected_yet():
    app_dir = Path(__file__).resolve().parents[1] / "app"
    users = [p for p in app_dir.rglob("*.py")
             if "weather" not in p.parts and "app.weather" in p.read_text(encoding="utf-8")]
    assert users == []
