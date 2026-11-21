"""pipelines.circle_details — 원 안 대상 선택, 시군구 폴더 저장, 이어받기, 오류 시 멈춤. 네트워크 없음, [가상] 데이터만."""
import json

import pytest

from pipelines import areas, circle_details, haeundae_sample, tourapi_client
from pipelines.tourapi_client import CallBudgetExceeded, TourApiClient

FAKE_KEY = "MOCK-circle-key"  # [가상]


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

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def item(cid, type_id, lat, lon):
    return {"contentid": cid, "contenttypeid": type_id, "title": f"[가상] {cid}",
            "mapy": str(lat), "mapx": str(lon)}


@pytest.fixture
def raw(tmp_path, monkeypatch):
    """[가상] two 시군구 lists: 230 (area folder SEOMYEON) and 170 (sigungu/170)."""
    monkeypatch.setattr(areas, "RAW_ROOT", tmp_path)

    def put(path, items):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(ok_body(items))

    put(tmp_path / "SEOMYEON" / "list" / "areaBasedList2_p1.json", [
        item("1", "12", 35.15, 129.05),            # center
        item("2", "39", 35.155, 129.05),           # ~556 m → in
        item("3", "32", 35.15, 129.05),            # 숙박 → not a target type
        item("4", "38", 35.20, 129.05),            # ~5.6 km → out
    ])
    put(tmp_path / "sigungu" / "170" / "list" / "areaBasedList2_p1.json", [
        item("5", "14", 35.145, 129.05),           # other 구, ~556 m → in
        item("10.5", "12", 35.15, 129.05),         # invalid ID → never requested
    ])
    return tmp_path


KNOWN = {"230": "부산진구", "170": "동구"}


def test_targets_are_union_of_circles_across_sigungu(raw):
    listed = circle_details.load_listed(KNOWN)
    targets = circle_details.targets_in_circles(listed, ["1"], 1500)
    assert [(t.content_id, t.sigungu) for t in targets] == [("5", "170"), ("1", "230"), ("2", "230")]
    assert [t.content_id for t in circle_details.targets_in_circles(listed, ["1", "4"], 1500)] \
        == ["5", "1", "2", "4"]
    with pytest.raises(ValueError):
        circle_details.targets_in_circles(listed, ["999"], 1500)


class Opener:
    def __init__(self, fail_on=None):
        self.ops, self.fail_on = [], fail_on

    def __call__(self, request, timeout):
        op = request.full_url.split("?")[0].rsplit("/", 1)[1]
        self.ops.append(op)
        if op == self.fail_on:
            return FakeHTTP(json.dumps({"response": {"header": {"resultCode": "22",
                                                                 "resultMsg": "LIMITED"}}}).encode())
        return FakeHTTP(ok_body([{"contentid": "x"}]))


def client(opener, max_calls=20):
    return TourApiClient(FAKE_KEY, "https://example.invalid/Svc", max_calls=max_calls, opener=opener)


def test_fetch_saves_into_sigungu_folders_and_resumes(raw):
    targets = circle_details.targets_in_circles(circle_details.load_listed(KNOWN), ["1"], 1500)
    todo = circle_details.pending(targets)
    assert {op: len(v) for op, v in todo.items()} == {op: 3 for op in circle_details.OPERATIONS}

    opener = Opener()
    assert circle_details.fetch_kor(client(opener), todo["detailCommon2"], "detailCommon2") == 3
    assert circle_details.fetch_kor(client(opener), todo["detailIntro2"], "detailIntro2") == 3
    stats = circle_details.fetch_with(client(opener), todo["detailWithTour2"], interval_s=0)
    assert stats["ok"] == 3
    assert (raw / "sigungu" / "170" / "common" / "5.json").is_file()
    assert (raw / "SEOMYEON" / "intro" / "2.json").is_file()
    assert (raw / "SEOMYEON" / "accessibility" / "1.json").is_file()
    log = (raw / "SEOMYEON" / "fetch_log.jsonl").read_text(encoding="utf-8")
    assert FAKE_KEY not in log and "serviceKey" not in log

    assert all(not v for v in circle_details.pending(targets).values())
    again = Opener()
    circle_details.fetch_kor(client(again), targets, "detailCommon2")
    assert again.ops == []  # 이미 받은 파일은 다시 호출하지 않음


def test_fetch_stops_on_error_and_budget(raw):
    targets = circle_details.targets_in_circles(circle_details.load_listed(KNOWN), ["1"], 1500)
    opener = Opener(fail_on="detailIntro2")
    with pytest.raises(haeundae_sample.FetchStopped):
        circle_details.fetch_kor(client(opener), targets, "detailIntro2")
    assert opener.ops == ["detailIntro2"]  # 첫 오류에서 멈춤, 재시도 없음
    assert not (raw / "sigungu" / "170" / "intro").exists()

    with pytest.raises(CallBudgetExceeded):
        circle_details.fetch_kor(client(Opener(), max_calls=2), targets, "detailCommon2")


def test_main_dry_run_makes_no_calls(raw, monkeypatch, capsys):
    monkeypatch.setattr(circle_details, "busan_sigungu", lambda: KNOWN)
    monkeypatch.setattr(circle_details, "load_service_keys",
                        lambda: (_ for _ in ()).throw(AssertionError("dry run must not load keys")))
    assert circle_details.main(["--center", "1", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "targets=3" in out and "detailCommon2=3" in out


def test_main_refuses_when_over_budget(raw, monkeypatch, capsys):
    monkeypatch.setattr(circle_details, "busan_sigungu", lambda: KNOWN)
    monkeypatch.setattr(circle_details, "load_service_keys",
                        lambda: (_ for _ in ()).throw(AssertionError("must stop before loading keys")))
    assert circle_details.main(["--center", "1", "--max-calls", "2"]) == 1
    assert "more than --max-calls 2" in capsys.readouterr().out
