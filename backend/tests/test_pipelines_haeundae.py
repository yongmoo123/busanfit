"""pipelines (작업 C) — 키 처리, 수집 이어받기, 매핑, 재현성. 네트워크 없이 [가상] 원본만 쓴다."""
import io
import json
from pathlib import Path
import sqlite3
from urllib.error import HTTPError, URLError

import pytest

from app.data.sqlite_repository import SqlitePlaceRepository
from app.data import db
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


@pytest.mark.parametrize("usetime, restdate, expected", [
    ("10:00~18:00", "연중무휴", every_day("10:00", "18:00")),
    ("10:30-20:00", "명절", every_day("10:30", "20:00")),
    ("09:00~18:00", "매주 월요일", {**every_day("09:00", "18:00"), "mon": []}),
    ("11:30~05:00", "연중무휴", every_day("11:30", "05:00")),      # 자정 넘김: close < open
    ("08:00~24:00", "연중무휴", every_day("08:00", "24:00")),      # 24:00은 close에만
    ("상시 개방", "연중무휴", every_day("00:00", "24:00")),
])
def test_open_hours_parsed_only_when_certain(usetime, restdate, expected):
    assert mapping.parse_open_hours(usetime, restdate) == expected


@pytest.mark.parametrize("usetime, restdate", [
    ("10:00~18:00", None),            # 쉬는날 모름 → 매일 영업으로 채우지 않음
    ("10:00~18:00", ""),
    (None, "연중무휴"),                 # 이용시간 누락 → 상시 영업으로 채우지 않음
    ("상시 개방", None),
    ("10:00~18:00 (입장 마감 17:30)", "연중무휴"),
    ("- 평일 10:00~19:00- 주말 10:00~20:00", "연중무휴"),
    ("10:00~18:00", "매주 월요일 / 1월 1일"),
    ("10:00~18:00", "매주 토요일, 일요일"),
    ("24:00~10:00", "연중무휴"), ("10:00~10:00", "연중무휴"), ("10:00~25:00", "연중무휴"),
    ("※ 매장마다 상이함", "연중무휴"),
])
def test_open_hours_not_filled(usetime, restdate):
    assert mapping.parse_open_hours(usetime, restdate) is None


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
    "101": {"contentid": "101", "contenttypeid": "39", "opentimefood": "- 11:00~21:00<br>- 마지막 주문 20:30",
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
