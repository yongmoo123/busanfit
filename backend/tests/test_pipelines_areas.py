"""pipelines 권역 인자 (FR-020, 이슈 #36) — 권역 표, 원본 경로, 목록만 수집, area 칸. 네트워크 없음, [가상] 데이터만."""
import json
from pathlib import Path

import pytest

from pipelines import accessibility_collect, accessibility_judge, areas, duty_free_ids, haeundae_sample, mapping
from pipelines import tourapi_client
from pipelines.tourapi_client import TourApiClient

REPO_ROOT = Path(__file__).resolve().parents[2]
FAKE_KEY = "MOCK-area-key"  # [가상]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("tests must not use the network")
    monkeypatch.setattr(tourapi_client, "urlopen", refuse)


def ok_body(items):
    return json.dumps({"response": {"header": {"resultCode": "0000", "resultMsg": "OK"},
                                    "body": {"items": {"item": items} if items else "",
                                             "totalCount": len(items), "numOfRows": 1000, "pageNo": 1}}},
                      ensure_ascii=False).encode("utf-8")


class FakeHTTP:
    def __init__(self, body):
        self.status, self._body = 200, body

    def read(self):
        return self._body

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def openapi_area_enums() -> list[list[str]]:
    found = []

    def walk(node):
        if isinstance(node, dict):
            enum = node.get("enum")
            if isinstance(enum, list) and "HAEUNDAE" in enum:
                found.append(enum)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(json.loads((REPO_ROOT / "contracts" / "openapi.json").read_text(encoding="utf-8")))
    return found


# ---------------------------------------------------------------- area table

def test_area_codes_match_openapi_enum():
    enums = openapi_area_enums()
    assert enums, "openapi.json has no area enum"
    for enum in enums:
        assert sorted(enum) == sorted(areas.AREA_CODES)


def test_area_table_values():
    table = {a.code: (a.sigungu_name, a.ldong_regn_cd, a.ldong_signgu_cd) for a in areas.AREAS.values()}
    assert table == {"HAEUNDAE": ("해운대구", "26", "350"), "SEOMYEON": ("부산진구", "26", "230"),
                     "GWANGALLI": ("수영구", "26", "500"), "NAMPO": ("중구", "26", "110")}
    assert areas.DEFAULT_AREA == "HAEUNDAE"


def test_raw_dir_keeps_haeundae_path_and_splits_others():
    assert areas.get("HAEUNDAE").raw_dir == areas.RAW_ROOT == haeundae_sample.RAW_DIR
    assert areas.RAW_ROOT == REPO_ROOT / "data" / "raw" / "tourapi"
    for code in ("SEOMYEON", "GWANGALLI", "NAMPO"):
        assert areas.get(code).raw_dir == areas.RAW_ROOT / code
    assert areas.get("HAEUNDAE").default_db == REPO_ROOT / "data" / "haeundae_sample.sqlite3"
    assert areas.get("NAMPO").default_db == REPO_ROOT / "data" / "nampo_sample.sqlite3"


def test_only_haeundae_has_report_center():
    assert areas.get("HAEUNDAE").report_center == (35.159084, 129.160279)
    assert accessibility_judge.CENTER == areas.get("HAEUNDAE").report_center
    assert all(areas.get(c).report_center is None for c in ("SEOMYEON", "GWANGALLI", "NAMPO"))


def test_unknown_area_is_refused():
    with pytest.raises(ValueError):
        areas.get("BUSAN")
    with pytest.raises(SystemExit):
        haeundae_sample.main(["--area", "haeundae", "build", "--db", "x.sqlite3"])  # 소문자는 enum 아님


# ---------------------------------------------------------------- CLI defaults

def test_cli_raw_default_follows_area(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(haeundae_sample, "cmd_build",
                        lambda args: seen.update(area=args.area, raw=args.raw) or 0)
    assert haeundae_sample.main(["build", "--db", "x"]) == 0
    assert seen == {"area": "HAEUNDAE", "raw": str(areas.RAW_ROOT)}
    assert haeundae_sample.main(["--area", "GWANGALLI", "build", "--db", "x"]) == 0
    assert seen == {"area": "GWANGALLI", "raw": str(areas.RAW_ROOT / "GWANGALLI")}
    assert haeundae_sample.main(["--area", "NAMPO", "--raw", str(tmp_path), "build", "--db", "x"]) == 0
    assert seen == {"area": "NAMPO", "raw": str(tmp_path)}


def test_accessibility_cli_db_default_follows_area(monkeypatch):
    seen = {}
    monkeypatch.setattr(accessibility_judge, "cmd_report", lambda args: seen.update(vars(args)) or 0)
    monkeypatch.setattr(accessibility_collect, "cmd_phrases", lambda args: seen.update(vars(args)) or 0)
    assert accessibility_judge.main(["--area", "SEOMYEON", "report"]) == 0
    assert seen["db"] == str(areas.get("SEOMYEON").default_db)
    assert seen["raw"] == str(areas.RAW_ROOT / "SEOMYEON")
    seen.clear()
    assert accessibility_collect.main(["phrases"]) == 0
    assert seen["db"] == str(areas.get("HAEUNDAE").default_db) and seen["raw"] == str(areas.RAW_ROOT)


def test_duty_free_paths_by_area():
    assert duty_free_ids.raw_list_of("HAEUNDAE") == duty_free_ids.RAW_LIST
    assert duty_free_ids.RAW_LIST == REPO_ROOT / "data/raw/tourapi/list/areaBasedList2_p1.json"
    assert duty_free_ids.output_of("HAEUNDAE") == duty_free_ids.OUTPUT
    assert duty_free_ids.raw_list_of("NAMPO") == REPO_ROOT / "data/raw/tourapi/NAMPO/list/areaBasedList2_p1.json"
    assert duty_free_ids.output_of("NAMPO") == REPO_ROOT / "data/processed/duty-free-exclusion.NAMPO.json"
    assert duty_free_ids.relative(duty_free_ids.RAW_LIST) == "data/raw/tourapi/list/areaBasedList2_p1.json"


def test_duty_free_build_records_source_path():
    raw = {"response": {"body": {"items": {"item": [
        {"contentid": "9", "contenttypeid": "38", "lclsSystm3": "SH040300"},
        {"contentid": "10", "contenttypeid": "38", "lclsSystm3": "SH010100"},
        {"contentid": "11", "contenttypeid": "39", "lclsSystm3": "SH040300"}]}}}}
    default = duty_free_ids.build(raw)
    assert default["generatedFrom"] == "data/raw/tourapi/list/areaBasedList2_p1.json (pipelines/duty_free_ids.py)"
    assert default["placeIds"] == ["tourapi-kor:9"] and default["shoppingTotal"] == 2
    other = duty_free_ids.build(raw, "data/raw/tourapi/NAMPO/list/areaBasedList2_p1.json")
    assert other["generatedFrom"].startswith("data/raw/tourapi/NAMPO/")


# ---------------------------------------------------------------- fetch

class AreaOpener:
    """[가상] TourAPI: records (operation, url) and answers per operation."""

    def __init__(self, sigungu=None):
        self.calls = []
        self.sigungu = sigungu or [{"code": "230", "name": "부산진구"}]

    def __call__(self, request, timeout):
        url = request.full_url
        op = url.split("?")[0].rsplit("/", 1)[1]
        self.calls.append((op, url))
        if op == "ldongCode2" and "lDongRegnCd=26" in url:
            return FakeHTTP(ok_body(self.sigungu))
        if op == "ldongCode2":
            return FakeHTTP(ok_body([{"code": "26", "name": "부산광역시"}]))
        if op == "areaBasedList2":
            return FakeHTTP(ok_body([
                {"contentid": "200", "contenttypeid": "12", "title": "[가상] A", "mapx": "129.05", "mapy": "35.15"},
                {"contentid": "201", "contenttypeid": "32", "title": "[가상] B", "mapx": "129.05", "mapy": "35.15"}]))
        return FakeHTTP(ok_body([]))


def fetcher(opener, raw):
    client = TourApiClient(FAKE_KEY, "https://example.invalid/KorService2", max_calls=20, opener=opener)
    return haeundae_sample.Fetcher(client, haeundae_sample.RawStore(raw), out=lambda *a: None)


def test_list_only_calls_area_based_list_with_table_codes(tmp_path):
    raw = tmp_path / "SEOMYEON"
    opener = AreaOpener()
    info = haeundae_sample.run_fetch(fetcher(opener, raw), "SEOMYEON", list_only=True)
    assert [op for op, _ in opener.calls] == ["areaBasedList2"]
    url = opener.calls[0][1]
    assert "lDongRegnCd=26" in url and "lDongSignguCd=230" in url
    assert info == {"area": "SEOMYEON", "busan": "26", "sigungu": "230", "listed": 2, "targets": 1}
    assert (raw / "list" / "areaBasedList2_p1.json").is_file()
    assert not (raw / "common").exists() and not (raw / "intro").exists() and not (raw / "ldong").exists()
    log = (raw / "fetch_log.jsonl").read_text(encoding="utf-8")
    assert FAKE_KEY not in log and "serviceKey" not in log

    again = AreaOpener()
    assert haeundae_sample.run_fetch(fetcher(again, raw), "SEOMYEON", list_only=True)["listed"] == 2
    assert again.calls == []  # 이미 받은 파일은 다시 호출하지 않음


def test_full_fetch_uses_area_name_and_checks_table(tmp_path):
    opener = AreaOpener()
    info = haeundae_sample.run_fetch(fetcher(opener, tmp_path / "ok"), "SEOMYEON")
    assert info["sigungu"] == "230"
    assert [op for op, _ in opener.calls] == ["ldongCode2", "ldongCode2", "lclsSystmCode2", "areaBasedList2",
                                              "detailCommon2", "detailIntro2"]

    wrong = AreaOpener(sigungu=[{"code": "999", "name": "부산진구"}])
    with pytest.raises(haeundae_sample.FetchStopped) as error:
        haeundae_sample.run_fetch(fetcher(wrong, tmp_path / "bad"), "SEOMYEON")
    assert "999" in str(error.value)
    assert "areaBasedList2" not in [op for op, _ in wrong.calls]


def test_sigungu_raw_dir_reuses_area_folders():
    assert areas.sigungu_raw_dir("350") == areas.RAW_ROOT
    assert areas.sigungu_raw_dir("230") == areas.RAW_ROOT / "SEOMYEON"
    assert areas.sigungu_raw_dir("500") == areas.RAW_ROOT / "GWANGALLI"
    assert areas.sigungu_raw_dir("110") == areas.RAW_ROOT / "NAMPO"
    assert areas.sigungu_raw_dir("290") == areas.RAW_ROOT / "sigungu" / "290"


def test_busan_sigungu_reads_stored_ldong_file(tmp_path):
    path = tmp_path / "26.json"
    path.write_bytes(ok_body([{"code": "110", "name": "중구"}, {"code": "290", "name": "남구"}]))
    assert haeundae_sample.busan_sigungu(path) == {"110": "중구", "290": "남구"}


def test_sigungu_lists_skip_stored_and_stop_on_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(areas, "RAW_ROOT", tmp_path)
    stored = tmp_path / "list" / "areaBasedList2_p1.json"     # [가상] 해운대구(350) 목록이 이미 있음
    stored.parent.mkdir(parents=True)
    stored.write_bytes(ok_body([{"contentid": "1", "contenttypeid": "12"}]))
    opener = AreaOpener()
    client = TourApiClient(FAKE_KEY, "https://example.invalid/KorService2", max_calls=5, opener=opener)
    known = {"350": "해운대구", "290": "남구"}
    done = haeundae_sample.run_sigungu_lists(client, ["350", "290"], known, out=lambda *a: None)
    assert [(d["sigungu"], d["calls"], d["listed"]) for d in done] == [("350", 0, 1), ("290", 1, 2)]
    assert [op for op, _ in opener.calls] == ["areaBasedList2"]
    assert "lDongSignguCd=290" in opener.calls[0][1]
    assert (tmp_path / "sigungu" / "290" / "list" / "areaBasedList2_p1.json").is_file()
    assert not (tmp_path / "sigungu" / "290" / "common").exists()

    with pytest.raises(haeundae_sample.FetchStopped):
        haeundae_sample.run_sigungu_lists(client, ["999"], known, out=lambda *a: None)
    assert len(opener.calls) == 1


# ---------------------------------------------------------------- build: area column

def sample():
    item = {"contentid": "300", "contenttypeid": "12", "title": "[가상] 장소", "addr1": "[가상] 주소",
            "mapx": "129.03", "mapy": "35.10", "lclsSystm3": "VE040100"}
    return mapping.RawSample(listed={"300": item}, commons={"300": {"contentid": "300"}},
                             intros={"300": {}}, lcls_names={}, fetched_at={"300": None},
                             retrieved_at="2026-11-21T00:00:00+09:00")


def test_build_rows_writes_area_code():
    assert [r["area"] for r in mapping.build_rows(sample()).rows] == ["HAEUNDAE"]
    assert [r["area"] for r in mapping.build_rows(sample(), area="NAMPO").rows] == ["NAMPO"]
    with pytest.raises(ValueError):
        mapping.build_rows(sample(), area="Nampo")


def test_accessibility_report_without_center_has_no_radius_counts(tmp_path):
    rules = accessibility_judge.load_rules()
    report = accessibility_judge.build_report([], rules, tmp_path / "missing.sqlite3", center=None)
    assert report["candidates_in_radius"] is None
