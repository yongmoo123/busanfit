"""권역 원 판정·v3 build·사후면세점 예외 (FR-020, FR-007, 이슈 #36, PM 결정 11/21). 네트워크 없음, [가상] 데이터만."""
import json
import sqlite3

import pytest

from pipelines import areas, circle_build, circles, duty_free_ids, tourapi_client

CENTERS = {"SEOMYEON": (35.15, 129.05), "GWANGALLI": (35.15, 129.10)}  # [가상] 약 4.5 km 떨어진 두 중심
RADIUS = 1500.0
METERS_PER_DEGREE_LAT = 111_195.0


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("tests must not use the network")
    monkeypatch.setattr(tourapi_client, "urlopen", refuse)


def north(center, meters):
    return center[0] + meters / METERS_PER_DEGREE_LAT, center[1]


def body(items):
    return json.dumps({"response": {"header": {"resultCode": "0000", "resultMsg": "OK"},
                                    "body": {"items": {"item": items} if items else "",
                                             "totalCount": len(items), "numOfRows": 1000, "pageNo": 1}}},
                      ensure_ascii=False)


def listed_item(cid, type_id, point, lcls3="SH010100"):
    return {"contentid": cid, "contenttypeid": type_id, "title": f"[가상] 장소 {cid}",
            "mapy": str(point[0]), "mapx": str(point[1]), "lclsSystm3": lcls3}


# ---------------------------------------------------------------- circles

def test_area_of_inside_outside_and_overlap():
    assert circles.area_of(*north(CENTERS["SEOMYEON"], 1000), CENTERS, RADIUS) == "SEOMYEON"
    assert circles.area_of(*north(CENTERS["GWANGALLI"], 1499), CENTERS, RADIUS) == "GWANGALLI"
    assert circles.area_of(*CENTERS["GWANGALLI"], CENTERS, 0.0001) == "GWANGALLI"  # 거리 ≤ 반경이면 안
    assert circles.area_of(*north(CENTERS["SEOMYEON"], 1600), CENTERS, RADIUS) is None
    near = {"A": (35.15, 129.05), "B": north((35.15, 129.05), 1000)}
    with pytest.raises(circles.CircleOverlap, match="contentid 7"):
        circles.area_of(*north((35.15, 129.05), 500), near, RADIUS, label="contentid 7")


def test_centers_come_from_retrieval_config(tmp_path):
    shipped = circles.load_centers(required=areas.AREA_CODES)
    assert set(shipped) == set(areas.AREA_CODES)
    assert shipped["HAEUNDAE"] == (35.159084, 129.160279)  # DEC-023 ① 그대로
    config = tmp_path / "retrieval.json"
    config.write_text(json.dumps({"areaCenters": {"HAEUNDAE": {"latitude": 35.1, "longitude": 129.1}}}),
                      encoding="utf-8")
    with pytest.raises(ValueError, match="NAMPO"):
        circles.load_centers(config, required=areas.AREA_CODES)


def test_radius_follows_runtime_setting():
    assert circles.radius_m({}) == 1500
    assert circles.radius_m({"BUSANFIT_WALK_RADIUS_M": "800"}) == 800


# ---------------------------------------------------------------- v3 build

@pytest.fixture
def raw(tmp_path, monkeypatch):
    """[가상] 시군구 230(권역 폴더 SEOMYEON)과 170(sigungu/170, 옆 구)."""
    monkeypatch.setattr(areas, "RAW_ROOT", tmp_path)
    s, g = CENTERS["SEOMYEON"], CENTERS["GWANGALLI"]
    lists = {
        tmp_path / "SEOMYEON": [listed_item("1", "12", north(s, 200)),
                                listed_item("2", "38", north(s, 300), lcls3="SH040300"),
                                listed_item("3", "39", north(s, 5000)),           # 원 밖 → 건너뜀
                                listed_item("4", "32", north(s, 100))],           # 숙박: 대상 아님
        tmp_path / "sigungu" / "170": [listed_item("5", "14", north(g, -400))],   # 옆 구지만 광안리 원 안
    }
    for root, items in lists.items():
        (root / "list").mkdir(parents=True)
        (root / "list" / "areaBasedList2_p1.json").write_text(body(items), encoding="utf-8")
        log = []
        for it in items:
            cid = it["contentid"]
            for kind, detail in (("common", {"contentid": cid, "addr1": f"[가상] 주소 {cid}",
                                             "overview": "[가상] 개요"}),
                                 ("intro", {"contentid": cid, "usetime": "09:00~18:00", "restdate": "연중무휴",
                                            "opentime": "09:00~18:00", "restdateshopping": "연중무휴",
                                            "usetimeculture": "09:00~18:00", "restdateculture": "연중무휴",
                                            "opentimefood": "09:00~18:00", "restdatefood": "연중무휴"})):
                (root / kind).mkdir(exist_ok=True)
                (root / kind / f"{cid}.json").write_text(body([detail]), encoding="utf-8")
                log.append({"time": "2026-11-21T10:00:00+09:00", "file": f"{kind}/{cid}.json"})
        (root / "fetch_log.jsonl").write_text("\n".join(json.dumps(e) for e in log) + "\n", encoding="utf-8")
        acc = root / "accessibility"
        acc.mkdir()
        acc_log = []
        for it in items:
            cid = it["contentid"]
            found = [{"contentid": cid, "exit": "출입구까지 턱이 없어 휠체어 접근 가능함"}] if cid == "1" else []
            (acc / f"{cid}.json").write_text(body(found), encoding="utf-8")
            acc_log.append({"time": "2026-11-21T11:00:00+09:00", "status": 200, "resultCode": "0000",
                            "file": f"{cid}.json"})
        (acc / "fetch_log.jsonl").write_text("\n".join(json.dumps(e) for e in acc_log) + "\n", encoding="utf-8")
    exceptions = tmp_path / "exceptions.json"
    exceptions.write_text(json.dumps({"exceptions": []}), encoding="utf-8")
    exclusion = tmp_path / "exclusion.json"
    exclusion.write_text(json.dumps({"placeIds": ["tourapi-kor:2"]}), encoding="utf-8")
    return tmp_path


def run(raw, db, centers=CENTERS):
    return circle_build.run(db, centers, RADIUS, codes=["230", "170"], lcls_root=raw,
                            exclusion_path=raw / "exclusion.json", exceptions_path=raw / "exceptions.json")


def test_build_assigns_area_by_circle_and_skips_outside(raw):
    report = run(raw, raw / "v3.sqlite3")
    conn = sqlite3.connect(raw / "v3.sqlite3")
    try:
        rows = dict(conn.execute("SELECT source_place_id, area FROM places").fetchall())
        acc = conn.execute("SELECT p.source_place_id, a.grade, a.wheelchair FROM accessibility a "
                           "JOIN places p ON p.id = a.place_id").fetchall()
    finally:
        conn.close()
    assert rows == {"1": "SEOMYEON", "2": "SEOMYEON", "5": "GWANGALLI"}  # 옆 구 장소도 원 기준 권역
    assert report["target_outside_circles_skipped"] == 1 and report["target_outside_by_sigungu"] == {"230": 1}
    assert report["non_target_type"] == 1
    assert report["assigned_by_area"] == {"GWANGALLI": 1, "SEOMYEON": 2}
    assert acc == [("1", "VERIFIED", 1)]  # DEC-026 규칙·grade 그대로, 빈 응답은 행 없음
    assert report["areas"]["SEOMYEON"]["grade_by_place"] == {"VERIFIED": 1, "UNSUITABLE": 0, "UNKNOWN": 1}
    assert report["duty_free"]["not_in_exclusion_or_exceptions"] == []


def test_build_twice_gives_same_tables(raw):
    run(raw, raw / "a.sqlite3")
    run(raw, raw / "b.sqlite3")

    def dump(path):
        conn = sqlite3.connect(path)
        try:
            return list(conn.iterdump())
        finally:
            conn.close()
    assert dump(raw / "a.sqlite3") == dump(raw / "b.sqlite3")


def test_build_stops_on_overlapping_circles_without_db(raw):
    near = {"SEOMYEON": CENTERS["SEOMYEON"], "NAMPO": north(CENTERS["SEOMYEON"], 600)}
    with pytest.raises(circles.CircleOverlap):
        run(raw, raw / "overlap.sqlite3", near)
    assert not (raw / "overlap.sqlite3").exists()


def test_build_reports_duty_free_not_covered(raw):
    (raw / "exclusion.json").write_text(json.dumps({"placeIds": []}), encoding="utf-8")
    report = run(raw, raw / "uncovered.sqlite3")
    assert report["duty_free"]["not_in_exclusion_or_exceptions"] == ["2"]


# ---------------------------------------------------------------- 사후면세점 예외

def duty_free_listed():
    s, g = CENTERS["SEOMYEON"], CENTERS["GWANGALLI"]
    items = [listed_item("10", "38", north(s, 100), "SH040300"),
             listed_item("11", "38", north(s, 200), "SH040300"),
             listed_item("12", "38", north(g, 100), "SH040300"),
             listed_item("13", "38", north(s, 9000), "SH040300"),   # 원 밖 → 목록에 없음
             listed_item("14", "38", north(s, 100), "SH010100"),    # 면세점 아님
             listed_item("15", "39", north(s, 100), "SH040300")]    # 쇼핑 아님
    return {it["contentid"]: it for it in items}


def test_duty_free_list_covers_circles_and_drops_exceptions():
    exceptions = [{"placeId": "tourapi-kor:11", "name": "[가상] 장소 11", "reason": "백화점은 놀거리 후보, PM 11/21"}]
    result = duty_free_ids.build(duty_free_listed(), CENTERS, RADIUS, exceptions)
    assert result["placeIds"] == ["tourapi-kor:10", "tourapi-kor:12"]
    assert result["exceptedPlaceIds"] == ["tourapi-kor:11"]
    assert result["dutyFreeInCircles"] == 3 and result["shoppingInCircles"] == 4
    assert result["countByArea"] == {"GWANGALLI": 1, "SEOMYEON": 1}
    assert duty_free_ids.build(duty_free_listed(), CENTERS, RADIUS, [])["count"] == 3


@pytest.mark.parametrize("entry", [
    {"placeId": "tourapi-kor:13", "name": "[가상] 장소 13"},   # 원 밖
    {"placeId": "tourapi-kor:14", "name": "[가상] 장소 14"},   # SH040300 아님
    {"placeId": "tourapi-kor:10", "name": "[가상] 다른 이름"},  # 이름이 원본과 다름
])
def test_stale_exception_is_an_error(entry):
    with pytest.raises(duty_free_ids.ExceptionMismatch):
        duty_free_ids.build(duty_free_listed(), CENTERS, RADIUS, [entry])


def test_shipped_exceptions_are_not_in_shipped_exclusion_list():
    exceptions = duty_free_ids.load_exceptions()
    listed = json.loads(duty_free_ids.OUTPUT.read_text(encoding="utf-8"))
    assert [e["placeId"] for e in exceptions] == listed["exceptedPlaceIds"] == ["tourapi-kor:2908259"]
    assert not {e["placeId"] for e in exceptions} & set(listed["placeIds"])
    assert all(e["reason"] == "백화점은 놀거리 후보, PM 11/21" for e in exceptions)
