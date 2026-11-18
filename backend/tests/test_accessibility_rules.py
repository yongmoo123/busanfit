"""무장애 표현 규칙 판정·적재 — FR-008, DEC-026 초안 (제안, 세민 확인 대기). 장소·문장은 가상."""
import copy
import json
import sqlite3

import pytest

from app.data import db
from pipelines import accessibility_judge as aj

RULES = aj.load_rules()
NONE4 = {"wheelchair": None, "stroller": None, "elevator": None, "accessible_toilet": None}


def values(item):
    return aj.judge(item, RULES)["values"]


def test_rules_file_is_marked_as_proposal():
    assert RULES["status"] == "제안, 세민 확인 대기"
    assert RULES["grade"] == {"value": "UNKNOWN", "note": "미산정(#58 등급 규칙 정리 전)"}


# ---------------------------------------------------------------- 규칙 1

@pytest.mark.parametrize("phrase", ["턱이 없", "단차가 없", "경사로", "휠체어 접근 가능",
                                    "휠체어가 통과 가능"])
@pytest.mark.parametrize("field", ["exit", "route"])
def test_rule1_each_phrase_sets_wheelchair_and_stroller(phrase, field):
    result = aj.judge({field: f"[가상] 주출입구는 {phrase}함"}, RULES)
    assert result["values"] == {**NONE4, "wheelchair": True, "stroller": True}
    assert result["positive"]["wheelchair"][0]["rule"] == "R1"


def test_rule1_only_in_exit_and_route():
    assert values({"parking": "경사로 있음", "elevator": "휠체어 접근 가능"}) == NONE4


# ---------------------------------------------------------------- 규칙 2·3

@pytest.mark.parametrize("text", ["엘리베이터 있음", "장애인용 엘리베이터가 있음(2층)"])
def test_rule2_elevator(text):
    assert values({"elevator": text}) == {**NONE4, "elevator": True}


def test_rule2_only_in_elevator_field():
    assert values({"route": "엘리베이터 있음"}) == NONE4


def test_rule3_needs_both_words_in_restroom():
    assert values({"restroom": "장애인 전용 화장실 있음(1층)"}) == {**NONE4, "accessible_toilet": True}
    assert values({"restroom": "장애인화장실 있음"}) == {**NONE4, "accessible_toilet": True}
    assert values({"restroom": "화장실 있음"}) == NONE4
    assert values({"handicapetc": "장애인 화장실 있음"}) == NONE4


# ---------------------------------------------------------------- 규칙 4 (부정·충돌·수동 확인)

def test_rule4_negation_gives_false_for_that_item_only():
    result = aj.judge({"elevator": "엘리베이터 없음", "handicapetc": "유모차 진입 불가"}, RULES)
    assert result["values"] == {**NONE4, "elevator": False, "stroller": False}
    assert result["negative"]["elevator"][0]["rule"] == "R4"


def test_rule4_barrier_absence_is_not_negation():
    # "턱 없음"은 장벽이 없다는 뜻이라 부정어로 보지 않는다
    assert values({"route": "휠체어 이용 가능<br/>내부 턱 없음."}) == NONE4
    assert values({"exit": "턱이 없어 휠체어 접근 가능. 내부 턱 없음"})["wheelchair"] is True


def test_rule4_negation_without_item_keyword_is_ignored():
    assert values({"publictransport": "저상버스 없음", "parking": "주차료 없음"}) == NONE4


def test_conflict_gives_null_and_is_recorded():
    item = {"exit": "주출입구는 턱이 없어 휠체어 접근 가능함", "handicapetc": "휠체어 이용 어려움"}
    result = aj.judge(item, RULES)
    assert result["values"]["wheelchair"] is None
    assert result["values"]["stroller"] is True  # 부정 근거는 휠체어에만 있음
    assert [c["item"] for c in result["conflicts"]] == ["wheelchair"]
    assert json.loads(aj.raw_json(result, RULES))["conflicts"] == ["wheelchair"]


def test_positive_phrase_in_negated_clause_is_not_true():
    result = aj.judge({"route": "경사로 없음"}, RULES)
    assert result["values"] == NONE4
    assert result["negated_positive"][0]["clause"] == "경사로 없음"


def test_power_wheelchair_is_reported_not_judged():
    text = "* 전동휠체어 탑승 불가* 수동휠체어는 접어서 탑승가능"
    result = aj.judge({"handicapetc": text}, RULES)
    assert result["values"] == NONE4
    assert [m["clause"] for m in result["manual_review"]] == ["전동휠체어 탑승 불가"]
    assert result["manual_review"][0]["original"] == text
    assert json.loads(aj.raw_json(result, RULES))["manual_review"] == ["전동휠체어 탑승 불가"]


# ---------------------------------------------------------------- 규칙 5·6

def test_rule5_rental_fields_are_ignored():
    item = {"wheelchair": "대여가능(수동휠체어 2대) 휠체어 접근 가능",
            "stroller": "유모차 대여 불가"}
    result = aj.judge(item, RULES)
    assert result["values"] == NONE4
    assert result["unmatched"] == []
    assert result["fields"] == item  # 원문은 raw에 남김


def test_rule6_empty_response_is_null_not_false():
    assert values(None) == NONE4
    assert values({"contentid": "1", "exit": "", "route": "  "}) == NONE4


def test_rule6_unmatched_sentence_is_null_and_listed():
    result = aj.judge({"exit": "여닫이문"}, RULES)
    assert result["values"] == NONE4
    assert result["unmatched"] == [{"field": "exit", "original": "여닫이문"}]


def test_judge_reads_rules_from_data():
    rules = copy.deepcopy(RULES)
    rules["positive"][0]["any"] = ["[가상]표현"]
    assert aj.judge({"exit": "턱이 없어"}, rules)["values"] == NONE4
    assert aj.judge({"exit": "[가상]표현"}, rules)["values"]["wheelchair"] is True


# ---------------------------------------------------------------- 적재

def make_db(tmp_path):
    path = tmp_path / "t.sqlite3"
    db.create_database(path)
    conn = db.connect(path)
    with conn:
        conn.execute("INSERT INTO data_sources (code, provider, dataset_name, url, retrieved_at) "
                     "VALUES ('tourapi-kor', 'p', 'd', 'u', '2026-11-12T00:00:00+09:00')")
        for sid in ("900001", "900002", "900003"):
            conn.execute(
                "INSERT INTO places (source_place_id, name, category, area, latitude, longitude, "
                "default_stay_min, source_id, updated_at) "
                "VALUES (?, '[가상] 장소', 'OTHER', 'HAEUNDAE', 35.16, 129.16, 60, 1, 't')", (sid,))
    return conn


def fake_results():
    base = {"title": "[가상]", "contenttypeid": "12", "has_file": True}
    return [
        {**base, "content_id": "900001", **aj.judge({"exit": "턱이 없어 휠체어 접근 가능"}, RULES)},
        {**base, "content_id": "900002", **aj.judge(None, RULES)},
        {**base, "content_id": "900003", **aj.judge({"exit": "여닫이문"}, RULES)},
        {**base, "content_id": "999999", **aj.judge({"exit": "경사로"}, RULES)},
    ]


def dump(conn):
    return (conn.execute("SELECT * FROM data_sources ORDER BY id").fetchall(),
            [tuple(r) for r in conn.execute("SELECT * FROM accessibility ORDER BY place_id")])


def test_load_is_idempotent_and_keeps_grade_unknown(tmp_path):
    conn = make_db(tmp_path)
    try:
        stats = aj.load(conn, fake_results(), RULES, "2026-11-19T00:44:04+09:00")
        assert stats == {"deleted": 0, "inserted": 2, "no_response_no_row": 1, "not_in_db": 1}
        first = [tuple(r) for r in dump(conn)[0]], dump(conn)[1]
        aj.load(conn, fake_results(), RULES, "2026-11-20T00:00:00+09:00")
        assert ([tuple(r) for r in dump(conn)[0]], dump(conn)[1]) == first
        source = conn.execute("SELECT * FROM data_sources WHERE code = 'tourapi-barrierfree'").fetchone()
        assert source["retrieved_at"] == "2026-11-19T00:44:04+09:00"  # 있으면 그대로
        assert source["license"] is None and source["base_date"] is None
        rows = conn.execute("SELECT * FROM accessibility ORDER BY place_id").fetchall()
        assert [r["grade"] for r in rows] == ["UNKNOWN", "UNKNOWN"]
        assert (rows[0]["wheelchair"], rows[0]["stroller"], rows[0]["elevator"]) == (1, 1, None)
        assert (rows[1]["wheelchair"], rows[1]["accessible_toilet"]) == (None, None)
        assert json.loads(rows[0]["raw"])["grade_note"] == "미산정(#58 등급 규칙 정리 전)"
    finally:
        conn.close()


def test_latest_retrieved_at_uses_ok_entries_with_files(tmp_path):
    acc = tmp_path / "accessibility"
    acc.mkdir()
    (acc / "1.json").write_text("{}", encoding="utf-8")
    entries = [
        {"time": "2026-11-19T00:40:00+09:00", "status": 200, "resultCode": "0000", "file": "1.json"},
        {"time": "2026-11-19T00:50:00+09:00", "status": 500, "resultCode": None, "file": None},
        {"time": "2026-11-19T00:55:00+09:00", "status": 200, "resultCode": "0000", "file": "2.json"},
    ]
    (acc / "fetch_log.jsonl").write_text("\n".join(json.dumps(e) for e in entries) + "\n",
                                         encoding="utf-8")
    assert aj.latest_retrieved_at(tmp_path) == "2026-11-19T00:40:00+09:00"
    assert aj.latest_retrieved_at(tmp_path / "none") is None


def test_backup_is_written_once(tmp_path):
    src, dst = tmp_path / "a.sqlite3", tmp_path / "a.pre_access.sqlite3"
    sqlite3.connect(src).close()
    assert aj.backup_once(src, dst) is True
    assert aj.backup_once(src, dst) is False
