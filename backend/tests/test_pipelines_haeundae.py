"""pipelines (작업 C) — 키 처리, 수집 이어받기, 매핑, 재현성. 네트워크 없이 [가상] 원본만 쓴다."""
import io
import json
from pathlib import Path
import sqlite3
from urllib.error import HTTPError, URLError

import pytest

from app.data.sqlite_repository import SqlitePlaceRepository
from app.data import db
from app.domain.place import validate_open_hours
from pipelines import env, haeundae_sample, mapping, tourapi_client
from pipelines.tourapi_client import (CallBudgetExceeded, Response, TourApiClient, TourApiError,
                                      build_url, mask_url, normalize_key)

FAKE_KEY = "MOCK+key/with==chars"            # [가상] 키. 어떤 출력에도 나오면 안 된다
FAKE_KEY_ENCODED = "MOCK%2Bkey%2Fwith%3D%3Dchars"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("tests must not use the network")
    monkeypatch.setattr(tourapi_client, "urlopen", refuse)


# ---------------------------------------------------------------- env

def test_env_file_parsing(tmp_path):
    path = tmp_path / ".env"
    path.write_text("# comment\nexport TOURAPI_SERVICE_KEY=\"abc\"\nOTHER = x \n\nBROKEN\n", encoding="utf-8")
    assert env.read_env_file(path) == {"TOURAPI_SERVICE_KEY": "abc", "OTHER": "x"}
    assert env.read_env_file(tmp_path / "missing.env") == {}


def test_shared_key_used_for_both_and_specific_wins(tmp_path):
    keys = env.load_service_keys({"TOURAPI_SERVICE_KEY": "shared"}, env_file=None)
    assert (keys.kor, keys.with_, keys.kor_name, keys.with_name) == ("shared", "shared", env.SHARED, env.SHARED)
    keys = env.load_service_keys({"TOURAPI_SERVICE_KEY": "shared", "TOURAPI_WITH_SERVICE_KEY": "w"}, env_file=None)
    assert (keys.kor, keys.with_, keys.with_name) == ("shared", "w", env.WITH)
    path = tmp_path / ".env"
    path.write_text("TOURAPI_KOR_SERVICE_KEY=k\nTOURAPI_WITH_SERVICE_KEY=w\n", encoding="utf-8")
    keys = env.load_service_keys({}, env_file=path)
    assert (keys.kor, keys.with_) == ("k", "w")
    assert env.load_service_keys({"TOURAPI_KOR_SERVICE_KEY": "process"}, env_file=path).kor == "process"
    assert env.set_names({}, env_file=path) == [env.KOR, env.WITH]


def test_missing_key_names_only_and_repr_hides_values():
    with pytest.raises(env.MissingKeyError) as error:
        env.load_service_keys({"TOURAPI_KOR_SERVICE_KEY": FAKE_KEY}, env_file=None)
    assert "TOURAPI_SERVICE_KEY" in str(error.value) and FAKE_KEY not in str(error.value)
    keys = env.load_service_keys({"TOURAPI_SERVICE_KEY": FAKE_KEY}, env_file=None)
    assert FAKE_KEY not in repr(keys) and FAKE_KEY not in str(keys)


# ---------------------------------------------------------------- key encoding and masking

def test_encoding_and_decoding_key_give_same_single_encoded_url():
    assert normalize_key(FAKE_KEY_ENCODED) == FAKE_KEY
    plain = build_url("https://example.invalid/Svc", "op", {"a": 1}, FAKE_KEY)
    encoded = build_url("https://example.invalid/Svc", "op", {"a": 1}, FAKE_KEY_ENCODED)
    assert plain == encoded
    assert "serviceKey=" + FAKE_KEY_ENCODED in plain   # encoded exactly once
    assert "%25" not in plain                           # no double encoding


def test_mask_url_hides_key():
    url = build_url("https://example.invalid/Svc", "op", {"contentId": "1"}, FAKE_KEY)
    masked = mask_url(url)
    assert "serviceKey=***" in masked
    assert FAKE_KEY not in masked and FAKE_KEY_ENCODED not in masked
    assert mask_url("https://x/op?a=1&serviceKey=abc%2B&b=2") == "https://x/op?a=1&serviceKey=***&b=2"


class FakeHTTP:
    def __init__(self, status=200, body=b"{}"):
        self.status, self._body = status, body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def ok_body(items, total=None):
    return json.dumps({"response": {"header": {"resultCode": "0000", "resultMsg": "OK"},
                                    "body": {"items": {"item": items} if items else "",
                                             "totalCount": len(items) if total is None else total,
                                             "numOfRows": 1000, "pageNo": 1}}},
                      ensure_ascii=False).encode("utf-8")


def test_client_budget_and_errors_never_show_key():
    seen = []

    def opener(request, timeout):
        seen.append(request.full_url)
        return FakeHTTP(200, ok_body([]))

    client = TourApiClient(FAKE_KEY, "https://example.invalid/Svc", max_calls=1, opener=opener)
    resp = client.get("op", {"x": 1})
    assert resp.status == 200 and resp.result() == ("0000", "OK")
    assert FAKE_KEY not in resp.url_masked and FAKE_KEY not in repr(client)
    with pytest.raises(CallBudgetExceeded):
        client.get("op", {})
    assert client.calls == 1 and len(seen) == 1

    def http_error(request, timeout):
        raise HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(
            b"<OpenAPI_ServiceResponse><cmmMsgHeader><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR"
            b"</returnAuthMsg><returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>"))

    resp = TourApiClient(FAKE_KEY, "https://example.invalid/Svc", max_calls=1, opener=http_error).get("op", {})
    assert resp.status == 401 and resp.result() == ("30", "SERVICE_KEY_IS_NOT_REGISTERED_ERROR")

    def down(request, timeout):
        raise URLError("no route")

    with pytest.raises(TourApiError) as error:
        TourApiClient(FAKE_KEY, "https://example.invalid/Svc", max_calls=1, opener=down).get("op", {})
    assert FAKE_KEY not in str(error.value) and FAKE_KEY_ENCODED not in str(error.value)
    assert error.value.__cause__ is None and error.value.__suppress_context__


def test_response_result_reads_xml_header():
    xml = b"<response><header><resultCode>22</resultCode><resultMsg>LIMITED</resultMsg></header></response>"
    assert Response(200, xml, "u").result() == ("22", "LIMITED")


# ---------------------------------------------------------------- mapping rules

@pytest.mark.parametrize("type_id, lcls3, expected", [
    ("39", "FD050100", "CAFE"), ("39", "FD010100", "FOOD"), ("38", "SH040300", "SHOPPING"),
    ("12", "SH010100", "SHOPPING"), ("14", "VE070600", "EXHIBITION"), ("12", "NA020900", "PARK"),
    ("12", "VE030100", "PARK"), ("12", "VE010200", "ATTRACTION"), ("28", "LS020300", "ATTRACTION"),
    ("12", None, "ATTRACTION"), ("99", "XX", "OTHER"),
])
def test_category_rules(type_id, lcls3, expected):
    assert mapping.category_of(type_id, lcls3)[0] == expected
    assert expected in {"CAFE", "FOOD", "EXHIBITION", "ATTRACTION", "PARK", "SHOPPING", "OTHER"}


def every_day(open_, close):
    return {day: [{"open": open_, "close": close}] for day in mapping.DAYS}


def days(spec):
    """{"mon": [("10:00", "18:00"), ...]} shorthand → open_hours dict."""
    return {day: [{"open": o, "close": c} for o, c in spec[day]] for day in mapping.DAYS}


def week(intervals, closed=(), **override):
    return days({day: ([] if day in closed else override.get(day, intervals)) for day in mapping.DAYS})


WEEKDAYS, WEEKEND = mapping.DAYS[:5], mapping.DAYS[5:]

# [가상] 문장 픽스처: 해운대 원본에서 본 패턴을 본떠 시각을 바꿔 쓴 것 (실제 장소 데이터 아님)
PARSED = [
    # 기존 규칙
    ("단일 범위", "10:00~18:00", "연중무휴", every_day("10:00", "18:00")),
    ("하이픈", "10:30-20:00", "명절", every_day("10:30", "20:00")),
    ("매주 한 요일", "09:00~18:00", "매주 월요일", {**every_day("09:00", "18:00"), "mon": []}),
    ("자정 넘김", "11:30~05:00", "연중무휴", every_day("11:30", "05:00")),
    ("24:00은 close에만", "08:00~24:00", "연중무휴", every_day("08:00", "24:00")),
    ("상시 개방", "상시 개방", "연중무휴", every_day("00:00", "24:00")),
    # 마지막 주문·입장 마감 → close (제안, 팀 확인 대기)
    ("마지막 주문 괄호", "09:00~21:00 (마지막 주문 20:15)", "연중무휴", every_day("09:00", "20:15")),
    ("라스트오더", "10:00~20:00 (라스트오더 19:10)", "연중무휴", every_day("10:00", "19:10")),
    ("입장 마감", "09:30~17:30 (입장 마감 16:40)", "매주 화요일",
     week([("09:30", "16:40")], closed=("tue",))),
    ("발권 마감", "09:00~20:00 (발권 마감 19:20)", "연중무휴", every_day("09:00", "19:20")),
    ("마지막 주문 줄 바꿈", "- 10:00~20:00<br>- 마지막 주문 19:25", "연중무휴", every_day("10:00", "19:25")),
    ("자정 넘김 마지막 주문", "- 13:30~03:30<br>- 마지막 주문 02:45", "연중무휴", every_day("13:30", "02:45")),
    ("마지막 주문 자정 → 24:00", "09:00~02:00 (마지막 주문 00:00)", "연중무휴", every_day("09:00", "24:00")),
    # 준비시간(브레이크) → 하루 두 구간 이상
    ("준비시간 괄호", "10:00~20:30 (준비시간 14:10~16:20)", "매주 목요일",
     week([("10:00", "14:10"), ("16:20", "20:30")], closed=("thu",))),
    ("휴게시간", "09:00~18:30 (휴게시간 13:00~14:00)", "연중무휴",
     week([("09:00", "13:00"), ("14:00", "18:30")])),
    ("준비시간 + 점심·저녁 마지막 주문",
     "- 10:30~21:00- 점심 마지막 주문 13:40- 준비시간 14:30~16:30- 저녁 마지막 주문 20:10", "연중무휴",
     week([("10:30", "13:40"), ("16:30", "20:10")])),
    ("브레이크타임 + 라스트오더 두 개", "11:00 - 20:30 (브레이크타임 14:30~16:30<br>라스트오더 13:50, 19:40",
     "매주 월요일", week([("11:00", "13:50"), ("16:30", "19:40")], closed=("mon",))),
    ("마지막 주문 슬래시", "- 11:00~21:00- 준비시간 14:00~16:30- 마지막 주문 13:20 / 20:05", "연중무휴",
     week([("11:00", "13:20"), ("16:30", "20:05")])),
    # 평일·주말·요일별 시간
    ("평일·주말", "- 평일 09:30~20:30 (마지막 주문 20:00)- 주말 09:30~21:00 (마지막 주문 20:40)", "연중무휴",
     week([("09:30", "20:00")], **{d: [("09:30", "20:40")] for d in WEEKEND})),
    ("[평일][주말·공휴일]", "[평일]- 09:00~18:00 (입장 마감 17:10)[주말·공휴일]- 09:00~19:00 (입장 마감 18:10)",
     "연중무휴", week([("09:00", "17:10")], **{d: [("09:00", "18:10")] for d in WEEKEND})),
    ("평일·토·일 따로", "- 평일 09:00~17:00 (마지막 주문 16:40)- 토요일 09:00~16:00- 일요일 09:00~19:00",
     "연중무휴", week([("09:00", "16:40")], sat=[("09:00", "16:00")], sun=[("09:00", "19:00")])),
    ("요일 범위(넘어감)", "화요일~목요일 10:00-20:00  금요일~월요일 10:00~21:00", "연중무휴",
     week([("10:00", "21:00")], **{d: [("10:00", "20:00")] for d in ("tue", "wed", "thu")})),
    ("주말, 공휴일", "평일 08:00~22:00 / 주말, 공휴일 08:00~21:00", "연중무휴",
     week([("08:00", "22:00")], **{d: [("08:00", "21:00")] for d in WEEKEND})),
    # 요일마다 다른 준비시간
    ("평일·주말 준비시간 다름", "[평일]- 10:00~19:00- 준비시간 14:30~16:00[주말]- 10:00~19:00- 준비시간 15:00~16:00",
     "연중무휴", week([("10:00", "14:30"), ("16:00", "19:00")],
                     **{d: [("10:00", "15:00"), ("16:00", "19:00")] for d in WEEKEND})),
    ("평일만 준비시간", "- 07:00~20:30<br>- 준비시간(평일) 14:00~15:00<br>- 마지막 주문 20:00", "연중무휴",
     week([("07:00", "14:00"), ("15:00", "20:00")], **{d: [("07:00", "20:00")] for d in WEEKEND})),
    ("주말 준비시간 여러 개", "- 평일 11:00~20:00 (준비 시간 14:00~17:00)<br>"
     "- 주말 11:00~20:00 (준비 시간 12:30~13:00, 15:00~16:00, 18:00~18:30)", "매주 목요일",
     week([("11:00", "14:00"), ("17:00", "20:00")], closed=("thu",),
          **{d: [("11:00", "12:30"), ("13:00", "15:00"), ("16:00", "18:00"), ("18:30", "20:00")]
             for d in WEEKEND})),
    # 접두어·참고 문구
    ("매일 접두어", "매일 08:00~20:00", "연중무휴", every_day("08:00", "20:00")),
    ("월~일 접두어 + 휴무", "월~일 10:00 - 20:00", "매주 수요일 정기휴무",
     week([("10:00", "20:00")], closed=("wed",))),
    ("※ 안내 문구(이용시간)", "07:00~23:00※ 자세한 사항은 전화 문의 바람", "연중무휴", every_day("07:00", "23:00")),
    ("※ 안내 문구(쉬는날)", "09:00~21:00", "매주 수요일※ 자세한 사항은 전화문의 요망",
     week([("09:00", "21:00")], closed=("wed",))),
    # 명절 휴무 (구조에 넣지 않음, 원문 보존)
    ("명절 전날", "10:30~22:00", "명절 전날", every_day("10:30", "22:00")),
    ("설·추석 전일 및 당일", "09:00~19:40", "설·추석 전일 및 당일", every_day("09:00", "19:40")),
    ("설날·추석 당일", "09:00~19:00", "설날·추석 당일", every_day("09:00", "19:00")),
    ("매주 + 설·추석 연휴", "09:00~19:00", "매주 월요일 / 설·추석 연휴", week([("09:00", "19:00")], closed=("mon",))),
    # 매주 여러 요일
    ("매주 두 요일", "11:00~17:00", "매주 월요일, 화요일", week([("11:00", "17:00")], closed=("mon", "tue"))),
    ("매주 요일 범위", "11:00~17:00", "매주 월요일~목요일",
     week([("11:00", "17:00")], closed=("mon", "tue", "wed", "thu"))),
    ("매주 토요일, 일요일", "10:00~18:00", "매주 토요일, 일요일", week([("10:00", "18:00")], closed=WEEKEND)),
    # 몇째 주·월 1회 + 요일: 그 요일을 비움 (영업일을 부풀리지 않음)
    ("월 1회 월요일", "10:00-21:00", "월 1회 월요일", week([("10:00", "21:00")], closed=("mon",))),
    ("월1회 월요일", "10:00~21:00", "월1회 월요일", week([("10:00", "21:00")], closed=("mon",))),
    ("2,4주 일요일", "09:00-21:00", "2,4주 일요일", week([("09:00", "21:00")], closed=("sun",))),
    ("매달 첫째 월요일", "08:00~17:00 (입장 마감 16:00)", "매달 첫째 월요일",
     week([("08:00", "16:00")], closed=("mon",))),
    ("명절, 월1회 월요일", "10:00~21:00", "명절, 월1회 월요일", week([("10:00", "21:00")], closed=("mon",))),
]


@pytest.mark.parametrize("label, usetime, restdate, expected", PARSED, ids=[p[0] for p in PARSED])
def test_open_hours_parsed_when_certain(label, usetime, restdate, expected):
    parsed = mapping.parse_open_hours(usetime, restdate)
    assert parsed == expected
    validate_open_hours(parsed)   # 구조·검증 규칙은 그대로


REJECTED = [
    # 누락을 채우지 않음
    ("쉬는날 없음", "10:00~18:00", None, mapping.R_NO_REST),
    ("쉬는날 빈 문자열", "10:00~18:00", "", mapping.R_NO_REST),
    ("이용시간 없음", None, "연중무휴", mapping.R_NO_USE),
    ("이용시간 빈 문자열", "", "매주 월요일 정기휴무", mapping.R_NO_USE),
    ("상시 개방 + 쉬는날 없음", "상시 개방", None, mapping.R_NO_REST),
    # 상이·문의뿐
    ("상이", "※ 매장마다 상이함", "※ 매장마다 상이함", mapping.R_VARIES),
    ("문의", "※ 자세한 사항은 전화문의 요망", "※ 자세한 사항은 전화문의 요망", mapping.R_VARIES),
    ("시간 + 상이 문구", "09:00~21:00※ 점포 별로 상이함", "연중무휴", mapping.R_VARIES),
    # 시설·층별 시간
    ("시설별", "[열람실] 08:00~21:00[매점] 10:00~18:00", "연중무휴", mapping.R_FACILITY),
    ("층별", "[1층]- 11:00~22:00[2층]- 11:00~21:00", "연중무휴", mapping.R_FACILITY),
    # 예약제·조건부
    ("예약제", "- 평일 13:00~17:00- 토요일 11:00~16:30※ 방문은 예약제로 운영됨", "매주 일요일",
     mapping.R_CONDITIONAL),
    ("변동", "09:00~21:00※ 운영시간은 상황에 따라 변동될 수 있음", "연중무휴", mapping.R_CONDITIONAL),
    ("기상", "09:00~21:00※ 기상악화 시 운항 불가", "연중무휴", mapping.R_CONDITIONAL),
    # 불규칙·외부 기준·공휴일 휴무
    ("부정기", "10:00~22:00", "부정기 휴무", mapping.R_REST_IRREGULAR),
    ("외부 기준", "10:00~20:00", "[가상] 백화점 휴점일 (백화점 공지 기준)", mapping.R_REST_IRREGULAR),
    ("공휴일 휴무", "10:00~18:00", "매주 월요일 / 법정공휴일", mapping.R_REST_IRREGULAR),
    ("1월 1일", "10:00~18:00", "매주 월요일 / 1월 1일", mapping.R_REST_IRREGULAR),
    ("단서 조항", "10:00~18:00", "매주 월요일 (단, 월요일이 공휴일인 경우 다음날 휴관)", mapping.R_REST_IRREGULAR),
    ("휴관 공지", "10:00~19:00", "연중무휴 ※ 휴관 시 공식 홈페이지를 통해 공지", mapping.R_REST_IRREGULAR),
    ("쉬는날 기상", "09:00~22:00", "※ 기상여건에 따라 다르므로 홈페이지 참고", mapping.R_REST_IRREGULAR),
    # 요일 모르는 정기휴무
    ("정기휴무일", "10:30-20:00", "정기휴무일", mapping.R_REST_UNKNOWN_DAY),
    # 해석 못 하는 문장
    ("샐러드바 마감", "11:00~21:00 (샐러드바 마감 20:00)", "연중무휴", mapping.R_OTHER),
    ("문구로 준비시간 바뀜", "- 11:00~21:00- 준비시간 15:00~16:00※ 주말에는 준비시간 없이 영업", "연중무휴",
     mapping.R_OTHER),
    ("요일 빠짐", "- 평일 10:00~18:00", "연중무휴", mapping.R_OTHER),
    ("준비시간이 영업시간 밖", "11:00~15:00 (준비시간 16:00~17:00)", "연중무휴", mapping.R_OTHER),
    ("마지막 주문이 영업시간 밖", "11:00~15:00 (마지막 주문 16:00)", "연중무휴", mapping.R_OTHER),
    ("open 24:00", "24:00~10:00", "연중무휴", mapping.R_OTHER),
    ("open == close", "10:00~10:00", "연중무휴", mapping.R_OTHER),
    ("25시", "10:00~25:00", "연중무휴", mapping.R_OTHER),
]

# 시험 파서가 잘못 받아들였던 10건의 패턴 (계절 한정 5, 명절·월 1회 5): 반드시 거절
WRONGLY_ACCEPTED_BEFORE = [
    ("계절: 매년 몇 월", "매년 7월~8월 09:30~18:30  ※ 자세한 사항은 홈페이지 참조", "연중무휴", mapping.R_SEASONAL),
    ("계절: 월 구간 괄호", "[12월~2월]06:00~19:00[3월~5월, 9월~11월]06:00~20:00[6~8월]06:00~21:00", "연중무휴",
     mapping.R_SEASONAL),
    ("계절: 하절기·동절기", "- 하절기 09:00~19:00 (입장마감 18:30) - 동절기 09:00~18:00 (입장마감 17:30)",
     "매주 화요일", mapping.R_SEASONAL),
    ("계절: 동절기(월 목록)", "- 동절기(11, 12, 1, 2월) 10:00~18:00 - 성수기(5, 6, 9월) 10:00~20:00", "연중무휴",
     mapping.R_SEASONAL),
    ("계절: 성수기", "- 평일 09:00~17:00- 주말/공휴일/성수기 09:00~18:30", "연중무휴", mapping.R_SEASONAL),
    ("명절, 월 1회", "10:30-20:00", "명절, 월 1회", mapping.R_REST_UNKNOWN_DAY),
    ("명절, 월1회", "10:30~20:00", "명절, 월1회", mapping.R_REST_UNKNOWN_DAY),
    ("월 1회 정기 휴점일", "10:30~20:00", "월 1회 정기 휴점일", mapping.R_REST_UNKNOWN_DAY),
    ("매월 1회 휴관", "10:00~19:00", "매월 1회 휴관※ 자세한 사항은 전화문의 요망", mapping.R_REST_UNKNOWN_DAY),
    ("연 2회", "10:00-21:00", "연 2회", mapping.R_REST_UNKNOWN_DAY),
]


@pytest.mark.parametrize("label, usetime, restdate, reason", REJECTED + WRONGLY_ACCEPTED_BEFORE,
                         ids=[r[0] for r in REJECTED + WRONGLY_ACCEPTED_BEFORE])
def test_open_hours_not_filled(label, usetime, restdate, reason):
    result = mapping.analyze_open_hours(usetime, restdate)
    assert (result.parsed, result.reason) == (None, reason)
    assert mapping.parse_open_hours(usetime, restdate) is None


def test_wrongly_accepted_before_count():
    assert len(WRONGLY_ACCEPTED_BEFORE) == 10


@pytest.mark.parametrize("usetime, restdate, kind", [
    ("01:00~24:00", "", mapping.S_NO_REST_ALL_DAY),            # 쉬는날 빈 값 + 01:00~24:00
    ("01:00~24:00", None, mapping.S_NO_REST_ALL_DAY),
    ("일~목 15:00~24:00금~토 15:00~02:00", "매주 일요일 (전화문의)", mapping.S_CONFLICT),  # 일요일 영업 + 휴무
])
def test_open_hours_suspicious_stay_null(usetime, restdate, kind):
    result = mapping.analyze_open_hours(usetime, restdate)
    assert result.parsed is None and result.suspicious == kind


def test_generic_prefix_with_closed_day_is_not_conflict():
    # "월~일"·"평일"은 일반 표기 → 휴무 요일이 우선 (모순 아님)
    assert mapping.parse_open_hours("[평일]- 10:00~20:00[주말]- 10:00~21:00", "매주 수요일")["wed"] == []
    assert mapping.analyze_open_hours("월~일 10:00~20:00", "매주 수요일").suspicious is None


def test_pattern_features_are_reported():
    result = mapping.analyze_open_hours(
        "[평일]- 10:00~20:00- 준비시간 14:00~15:00- 마지막 주문 19:30[주말]- 10:00~20:00", "명절, 월1회 월요일")
    assert result.features == {mapping.F_DAY_GROUPS, mapping.F_BREAK, mapping.F_BREAK_BY_DAY, mapping.F_LAST,
                               mapping.F_HOLIDAY, mapping.F_MONTHLY_DAY}


def test_hours_text_keeps_original_values():
    assert mapping.hours_text(" 10:00~18:00 (입장 마감 17:30) ", "매주 월요일") \
        == "이용시간: 10:00~18:00 (입장 마감 17:30)\n쉬는날: 매주 월요일"
    assert mapping.hours_text("", None) is None


@pytest.mark.parametrize("spend, expected", [(None, (60, False)), ("", (60, False)), ("1시간", (60, True)),
                                             ("90분", (90, True)), ("1시간 30분", (90, True)),
                                             ("약 1시간", (60, False))])
def test_stay_minutes_exhibition(spend, expected):
    assert mapping.stay_minutes("EXHIBITION", spend) == expected
    assert mapping.stay_minutes("FOOD", None) == (70, False)


# ---------------------------------------------------------------- end-to-end on [가상] raw files

def mock_item(cid, type_id, lcls3, **extra):
    base = {"contentid": cid, "contenttypeid": type_id, "title": f"[가상] 장소 {cid}",
            "addr1": "[가상] 부산광역시 해운대구", "addr2": "", "mapx": "129.16", "mapy": "35.16",
            "lclsSystm3": lcls3, "lDongRegnCd": "26", "lDongSignguCd": "350"}
    base.update(extra)
    return base


MOCK_LIST = [
    mock_item("100", "14", "VE070600"),                                   # 전시: 요금 원문, 운영시간 파싱
    mock_item("101", "39", "FD050100", addr1=""),                         # 카페: 주소 누락
    mock_item("102", "12", "NA020900"),                                   # 해변: 소개정보 없음
    mock_item("103", "38", "SH040300", mapx="0", mapy="0"),               # 좌표 없음 → 건너뜀
    mock_item("104", "32", "AC010100"),                                   # 숙박: 대상 아님
    mock_item("10.5", "12", "VE010200"),                                  # 허용 문자 밖 ID → 건너뜀
    mock_item("105", "28", "LS020300"),                                   # 레포츠: 요금 필드 비어 있음
]
MOCK_COMMON = {cid: {"contentid": cid, "overview": f"[가상] 개요 {cid}" if cid != "105" else ""}
               for cid in ("100", "101", "102", "103", "105")}
MOCK_INTRO = {
    "100": {"contentid": "100", "contenttypeid": "14", "usetimeculture": "10:00~18:00",
            "restdateculture": "매주 월요일", "usefee": "[가상] 성인 1,000원", "spendtime": ""},
    "101": {"contentid": "101", "contenttypeid": "39", "opentimefood": "- 11:00~21:00<br>- 샐러드바 마감 20:30",
            "restdatefood": "연중무휴"},
    "103": {"contentid": "103", "contenttypeid": "38", "opentime": "10:00-20:00", "restdateshopping": ""},
    "105": {"contentid": "105", "contenttypeid": "28", "usetimeleports": "상시 개방",
            "restdateleports": "연중무휴", "usefeeleports": ""},
}


def write_raw(root: Path) -> None:
    def put(rel, items):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(ok_body(items))
    put("list/areaBasedList2_p1.json", MOCK_LIST)
    put("lcls/list_p1.json", [{"lclsSystm1Cd": "VE", "lclsSystm1Nm": "[가상] 문화관광",
                               "lclsSystm2Cd": "VE07", "lclsSystm2Nm": "[가상] 전시시설",
                               "lclsSystm3Cd": "VE070600", "lclsSystm3Nm": "[가상] 미술관"}])
    log = []
    for cid, item in MOCK_COMMON.items():
        put(f"common/{cid}.json", [item])
        log.append({"file": f"common/{cid}.json", "time": f"2026-11-12T00:00:{int(cid) % 60:02d}+09:00"})
    put("intro/102.json", [])
    for cid, item in MOCK_INTRO.items():
        put(f"intro/{cid}.json", [item])
    (root / "fetch_log.jsonl").write_text("\n".join(json.dumps(e) for e in log) + "\n", encoding="utf-8")


def build(raw: Path, db_path: Path) -> dict:
    assert haeundae_sample.main(["--raw", str(raw), "build", "--db", str(db_path),
                                 "--report", str(db_path.with_suffix(".json"))]) == 0
    return json.loads(db_path.with_suffix(".json").read_text(encoding="utf-8"))


def test_build_maps_without_filling_missing(tmp_path):
    raw = tmp_path / "raw"
    write_raw(raw)
    report = build(raw, tmp_path / "a.sqlite3")
    conn = sqlite3.connect(tmp_path / "a.sqlite3")
    conn.row_factory = sqlite3.Row
    rows = {r["source_place_id"]: r for r in conn.execute("SELECT * FROM places")}
    source = conn.execute("SELECT * FROM data_sources").fetchone()
    conn.close()

    assert sorted(rows) == ["100", "101", "102", "105"]
    assert report["skipped"] == {"contentid 허용 문자 규칙 위반": 1, "대상 아닌 유형 32 숙박": 1,
                                 "좌표 없음·범위 밖": 1}
    assert report["skipped_ids"]["contentid 허용 문자 규칙 위반"] == ["10.5"]  # 값을 바꾸지 않고 보고
    assert source["code"] == "tourapi-kor" and source["license"] is None and source["base_date"] is None

    exhibition = rows["100"]
    assert (exhibition["category"], exhibition["price_text"], exhibition["price_amount"],
            exhibition["price_basis"]) == ("EXHIBITION", "[가상] 성인 1,000원", None, None)
    assert json.loads(exhibition["open_hours"])["mon"] == []
    assert exhibition["open_hours_text"] == "이용시간: 10:00~18:00\n쉬는날: 매주 월요일"

    cafe = rows["101"]
    assert cafe["category"] == "CAFE" and cafe["address"] is None          # 주소 누락은 NULL
    assert cafe["open_hours"] is None and "<br>" in cafe["open_hours_text"]  # 파싱 실패 → 원문만
    assert cafe["price_text"] is None                                      # 가격 누락 ≠ 무료

    beach = rows["102"]
    assert beach["category"] == "PARK"
    assert (beach["open_hours"], beach["open_hours_text"], beach["price_text"]) == (None, None, None)

    leisure = rows["105"]
    assert leisure["overview"] is None and leisure["price_text"] is None
    assert json.loads(leisure["open_hours"])["sun"] == [{"open": "00:00", "close": "24:00"}]

    for row in rows.values():
        assert row["indoor"] is None          # 실내 여부는 원본에 없음 → 미확인
        assert row["area"] == "HAEUNDAE"
    assert report["missing"]["address"]["count"] == 1
    assert report["missing"]["intro_item_missing"] == 1
    assert report["open_hours_parsed"] == {"count": 2, "rate": 0.6667, "total": 3}
    assert report["open_hours_null_reasons"] == {mapping.R_OTHER: 1}
    assert report["open_hours_patterns"] == {mapping.F_ALWAYS: 1, mapping.F_NO_CLOSE: 1, mapping.F_WEEKLY_ONE: 1}
    assert report["open_hours_suspicious"] == {"count": 0, "by_kind": {}}


def test_rebuild_from_same_raw_is_identical_and_readable(tmp_path):
    raw = tmp_path / "raw"
    write_raw(raw)
    build(raw, tmp_path / "a.sqlite3")
    build(raw, tmp_path / "b.sqlite3")

    def dump(path):
        conn = sqlite3.connect(path)
        try:
            return list(conn.iterdump())
        finally:
            conn.close()

    assert dump(tmp_path / "a.sqlite3") == dump(tmp_path / "b.sqlite3")
    conn = db.connect(tmp_path / "a.sqlite3")
    try:
        repo = SqlitePlaceRepository(conn)
        assert repo.get_place("tourapi-kor:100").name == "[가상] 장소 100"
        assert repo.get_place("tourapi-kor:10.5") is None
        assert len(repo.find_within_radius(35.16, 129.16, 100)) == 4
    finally:
        conn.close()


def test_build_refuses_existing_db(tmp_path):
    raw = tmp_path / "raw"
    write_raw(raw)
    build(raw, tmp_path / "a.sqlite3")
    with pytest.raises(FileExistsError):
        build(raw, tmp_path / "a.sqlite3")


# ---------------------------------------------------------------- fetch: resume, budget, stop on error

class ScriptedOpener:
    """Answers TourAPI operations from [가상] data and records the operations requested."""

    def __init__(self, fail_on=None):
        self.ops, self.fail_on = [], fail_on

    def __call__(self, request, timeout):
        url = request.full_url
        op = url.split("?")[0].rsplit("/", 1)[1]
        self.ops.append(op)
        if op == self.fail_on:
            return FakeHTTP(200, json.dumps({"response": {"header": {"resultCode": "22",
                                                                      "resultMsg": "LIMITED"}}}).encode())
        if op == "ldongCode2" and "lDongRegnCd=26" in url:
            return FakeHTTP(200, ok_body([{"code": "350", "name": "해운대구"}, {"code": "110", "name": "중구"}]))
        if op == "ldongCode2":
            return FakeHTTP(200, ok_body([{"code": "26", "name": "부산광역시"}]))
        if op == "lclsSystmCode2":
            return FakeHTTP(200, ok_body([]))
        if op == "areaBasedList2":
            return FakeHTTP(200, ok_body([mock_item("100", "14", "VE070600"), mock_item("101", "39", "FD050100"),
                                          mock_item("104", "32", "AC010100")]))
        return FakeHTTP(200, ok_body([{"contentid": "x"}]))


def fetcher_with(opener, raw, max_calls):
    client = TourApiClient(FAKE_KEY, "https://example.invalid/KorService2", max_calls=max_calls, opener=opener)
    return haeundae_sample.Fetcher(client, haeundae_sample.RawStore(raw), out=lambda *a: None)


def test_fetch_resumes_without_refetching(tmp_path):
    raw = tmp_path / "raw"
    first = ScriptedOpener()
    with pytest.raises(CallBudgetExceeded):
        haeundae_sample.run_fetch(fetcher_with(first, raw, max_calls=5))
    assert len(first.ops) == 5
    second = ScriptedOpener()
    info = haeundae_sample.run_fetch(fetcher_with(second, raw, max_calls=100))
    assert second.ops == ["detailIntro2", "detailCommon2", "detailIntro2"]  # 받은 것은 다시 받지 않음
    assert info == {"busan": "26", "haeundae": "350", "listed": 3, "targets": 2}
    assert not (raw / "common" / "104.json").exists()   # 숙박(대상 아님)은 상세를 받지 않음
    third = ScriptedOpener()
    haeundae_sample.run_fetch(fetcher_with(third, raw, max_calls=100))
    assert third.ops == []
    log = (raw / "fetch_log.jsonl").read_text(encoding="utf-8")
    assert FAKE_KEY not in log and "serviceKey" not in log


def test_fetch_stops_on_error_without_saving(tmp_path):
    raw = tmp_path / "raw"
    opener = ScriptedOpener(fail_on="lclsSystmCode2")
    with pytest.raises(haeundae_sample.FetchStopped) as error:
        haeundae_sample.run_fetch(fetcher_with(opener, raw, max_calls=100))
    assert "resultCode=22" in str(error.value) and "serviceKey=***" in str(error.value)
    assert FAKE_KEY not in str(error.value) and FAKE_KEY_ENCODED not in str(error.value)
    assert not (raw / "lcls").exists()
    assert opener.ops == ["ldongCode2", "ldongCode2", "lclsSystmCode2"]
