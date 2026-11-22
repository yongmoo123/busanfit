"""무장애 문장 → accessibility 항목 판정과 적재 — FR-008, DEC-026 확정 (11/19 PM 확인, #58).

    python -m pipelines.accessibility_judge load   [--db data/haeundae_sample.sqlite3]
    python -m pipelines.accessibility_judge report [--db ...] [--out data/processed/accessibility_judgement.json]
    python -m pipelines.accessibility_judge --area SEOMYEON load   # 권역 (기본 HAEUNDAE, pipelines/areas.py)

- 판정 규칙은 pipelines/accessibility_rules.json에만 있다. 이 모듈은 그 파일을 읽어 적용할 뿐이다.
- 네트워크를 쓰지 않는다. 원본은 data/raw/tourapi/accessibility/<contentid>.json만 읽는다.
- load: 처음 실행 때 DB를 <db>.pre_access.sqlite3로 복사해 두고(이미 있으면 덮어쓰지 않음),
  data_sources에 tourapi-barrierfree가 없으면 추가(있으면 그대로), 이 출처의 accessibility 행을
  지우고 다시 넣는다(한 트랜잭션). 같은 원본·규칙이면 몇 번 실행해도 같은 결과.
- grade는 DEC-026 ③ 규칙으로 계산한다(``grade_of``): 휠체어·유모차 두 항목만 보고, 하나라도 true면
  VERIFIED, true 없이 false가 있으면 UNSUITABLE, 둘 다 null이면 UNKNOWN. 엘리베이터·장애인 화장실은
  등급에 넣지 않는다. 등급은 표시용이고 이동제약 판정은 항목값으로만 한다(DEC-015).
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import shutil
import sqlite3

from pipelines.haeundae_sample import REPO_ROOT, RawStore, add_area_args, items_of, parse_area_args
from pipelines.accessibility_collect import listed_from_raw, normalize, targets_from_raw
from pipelines import areas, mapping
from app.data import db as appdb  # noqa: E402  (backend/ 경로는 haeundae_sample이 넣음)
from app.data.geo import haversine_m  # noqa: E402

RULES_PATH = Path(__file__).with_name("accessibility_rules.json")
DEFAULT_DB = areas.get(areas.DEFAULT_AREA).default_db  # 권역별 기본값: areas.Area.default_db
DEFAULT_OUT = REPO_ROOT / "data" / "processed" / "accessibility_judgement.json"
ITEMS = ("wheelchair", "stroller", "elevator", "accessible_toilet")

SOURCE = {
    "code": "tourapi-barrierfree",
    "provider": "한국관광공사",
    "dataset_name": "무장애 여행 정보_GW (KorWithService2)",
    "license": mapping.PORTAL_LICENSE,  # 값은 mapping.PORTAL_LICENSE 한 곳에만 둔다
    "url": "https://www.data.go.kr/data/15101897/openapi.do",
    "base_date": None,    # 문서에 없음
}
TYPE_NAMES = {"12": "관광지", "14": "문화시설", "28": "레포츠", "38": "쇼핑", "39": "음식점"}
# 보고용 반경 기준점은 권역 표(areas.Area.report_center)에 둔다. 해운대: 해운대해수욕장(11/20 보고)
CENTER = areas.get(areas.DEFAULT_AREA).report_center
RADIUS_M = 1500


def load_rules(path: Path = RULES_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- judge (pure)

def clauses(text: str, rules: dict) -> list[str]:
    parts = re.split(rules["clause_split"], text)
    return [c for c in (normalize(p) for p in parts) if c]


def match_positive(rule: dict, clause: str) -> list[str]:
    """Phrases of ``rule`` found in ``clause``: every ``all`` phrase and at least one ``any``."""
    required = rule.get("all", [])
    if not all(p in clause for p in required):
        return []
    options = rule.get("any")
    if options is None:
        return list(required)
    found = [p for p in options if p in clause]
    return [*required, *found] if found else []


def is_door_only(field: str, clause: str, rules: dict) -> bool:
    door = rules["door_only"]
    if field not in door["fields"]:
        return False
    text = clause
    for prefix in door["prefixes"]:
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text.strip(" .") in door["values"]


def apply_overrides(content_id: str | None, fields: dict, values: dict, rules: dict) -> tuple:
    """Place-specific overrides from the rules file. Applied only if the evidence is in the original."""
    applied, missing = [], []
    for ov in rules.get("overrides", []):
        if content_id is None or ov["content_id"] != content_id:
            continue
        if ov["evidence"] not in fields.get(ov["field"], ""):
            missing.append({"content_id": ov["content_id"], "name": ov["name"], "field": ov["field"],
                            "evidence": ov["evidence"]})
            continue
        for it, value in ov["set"].items():
            applied.append({"item": it, "from": values[it], "to": value, "field": ov["field"],
                            "evidence": ov["evidence"]})
            values[it] = value
    return applied, missing


def judge(item: dict | None, rules: dict) -> dict:
    """One detailWithTour2 item (or None for an empty response) → item values and evidence.

    Values are True / False / None. None = no information or conflict (never filled with False).
    Place overrides (rules["overrides"]) are matched by the item's ``contentid``.
    """
    ignored = set(rules["ignored_fields"]["fields"])
    neg = rules["negative"]
    manual = rules["manual_review"]
    pos_hits: dict[str, list] = {k: [] for k in ITEMS}
    neg_hits: dict[str, list] = {k: [] for k in ITEMS}
    negated_positive, manual_review, unmatched, door_only = [], [], [], []
    fields: dict[str, str] = {}

    for field, value in (item or {}).items():
        if field == "contentid" or not isinstance(value, str) or not normalize(value):
            continue
        fields[field] = value
        if field in ignored:
            continue
        field_hit = False
        judged_clause = False
        for clause in clauses(value, rules):
            if is_door_only(field, clause, rules):
                door_only.append({"field": field, "clause": clause})
                continue
            judged_clause = True
            cleaned = clause
            for phrase in neg["barrier_absence_phrases"]:
                cleaned = cleaned.replace(phrase, "")
            negated = [w for w in neg["words"] if w in cleaned]
            for rule in rules["positive"]:
                if field not in rule["fields"]:
                    continue
                found = match_positive(rule, clause)
                if not found:
                    continue
                field_hit = True
                if negated:
                    negated_positive.append({"rule": rule["id"], "field": field, "clause": clause,
                                             "phrases": found, "negation": negated})
                    continue
                for it in rule["items"]:
                    pos_hits[it].append({"rule": rule["id"], "field": field, "phrases": found,
                                         "clause": clause})
            if not negated:
                continue
            if field in manual["fields"] and manual["keyword"] in clause:
                manual_review.append({"rule": manual["id"], "field": field, "clause": clause,
                                      "original": value})
                field_hit = True
                continue
            for it, keywords in neg["item_keywords"].items():
                if any(k in clause for k in keywords):
                    neg_hits[it].append({"rule": neg["id"], "field": field, "clause": clause,
                                         "negation": negated})
                    field_hit = True
        if not field_hit and judged_clause:
            unmatched.append({"field": field, "original": value})

    values, conflicts = {}, []
    for it in ITEMS:
        if pos_hits[it] and neg_hits[it]:
            values[it] = None
            conflicts.append({"item": it, "positive": pos_hits[it], "negative": neg_hits[it]})
        elif pos_hits[it]:
            values[it] = True
        elif neg_hits[it]:
            values[it] = False
        else:
            values[it] = None
    content_id = None if item is None or item.get("contentid") is None else str(item["contentid"])
    overrides, override_missing = apply_overrides(content_id, fields, values, rules)
    return {"has_response": item is not None, "values": values, "conflicts": conflicts,
            "positive": pos_hits, "negative": neg_hits, "negated_positive": negated_positive,
            "manual_review": manual_review, "unmatched": unmatched, "door_only": door_only,
            "overrides": overrides, "override_missing": override_missing, "fields": fields}


def grade_of(values: dict, rules: dict) -> str:
    """DEC-026 ③: only the items in rules["grade"]["items"] (wheelchair, stroller) decide the grade.

    any True → VERIFIED; no True and any False → UNSUITABLE; all None → UNKNOWN.
    """
    judged = [values[it] for it in rules["grade"]["items"]]
    if any(v is True for v in judged):
        return "VERIFIED"
    if any(v is False for v in judged):
        return "UNSUITABLE"
    return "UNKNOWN"


def raw_json(result: dict, rules: dict) -> str:
    """accessibility.raw: original fields + evidence. No timestamps, so reloading gives the same text."""
    payload = {
        "rules_status": rules["status"],
        "rules_decision": rules["decision"],
        "grade_note": rules["grade"]["note"],
        "fields": result["fields"],
        "evidence": {it: [h["rule"] + ":" + h["clause"] for h in result["positive"][it]]
                     for it in ITEMS if result["positive"][it]},
        "negative": {it: [h["rule"] + ":" + h["clause"] for h in result["negative"][it]]
                     for it in ITEMS if result["negative"][it]},
        "conflicts": [c["item"] for c in result["conflicts"]],
        "negated_positive": [n["clause"] for n in result["negated_positive"]],
        "manual_review": [m["clause"] for m in result["manual_review"]],
        "door_only": [d["clause"] for d in result["door_only"]],
        "overrides": result["overrides"],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def judge_all(raw_root: Path, rules: dict) -> list[dict]:
    """All Haeundae targets in fetch order; places without a stored file are has_file=False."""
    listed = listed_from_raw(raw_root)
    store = RawStore(raw_root / "accessibility")
    out = []
    for cid in targets_from_raw(raw_root):
        meta = listed.get(cid, {})
        base = {"content_id": cid, "title": meta.get("title"),
                "contenttypeid": str(meta.get("contenttypeid"))}
        if not store.has(f"{cid}.json"):
            out.append({**base, "has_file": False, **judge(None, rules)})
            continue
        items = items_of(store.read_json(f"{cid}.json"))
        out.append({**base, "has_file": True, **judge(items[0] if items else None, rules)})
    return out


def latest_retrieved_at(raw_root: Path) -> str | None:
    """Latest time among OK fetch_log entries whose file is still present."""
    acc = raw_root / "accessibility"
    log = acc / "fetch_log.jsonl"
    if not log.is_file():
        return None
    times = []
    for line in log.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        if e.get("status") == 200 and e.get("resultCode") == "0000" and e.get("file") \
                and (acc / e["file"]).is_file():
            times.append(e["time"])
    return max(times) if times else None


# ---------------------------------------------------------------- load

def ensure_source(conn: sqlite3.Connection, retrieved_at: str) -> int:
    """Insert the tourapi-barrierfree row if missing; leave an existing row unchanged."""
    row = conn.execute("SELECT id FROM data_sources WHERE code = ?", (SOURCE["code"],)).fetchone()
    if row is not None:
        return row[0]
    return conn.execute(
        "INSERT INTO data_sources (code, provider, dataset_name, license, url, base_date, retrieved_at) "
        "VALUES (:code, :provider, :dataset_name, :license, :url, :base_date, :retrieved_at)",
        {**SOURCE, "retrieved_at": retrieved_at}).lastrowid


def load(conn: sqlite3.Connection, results: list[dict], rules: dict, retrieved_at: str) -> dict:
    stats = Counter()
    with conn:
        source_id = ensure_source(conn, retrieved_at)
        base_id = conn.execute("SELECT id FROM data_sources WHERE code = ?",
                               (mapping.SOURCE["code"],)).fetchone()
        if base_id is None:
            raise RuntimeError(f"data_sources has no {mapping.SOURCE['code']!r} row")
        place_ids = dict(conn.execute("SELECT source_place_id, id FROM places WHERE source_id = ?",
                                      (base_id[0],)).fetchall())
        stats["deleted"] = conn.execute("DELETE FROM accessibility WHERE source_id = ?",
                                        (source_id,)).rowcount
        for r in results:
            if not r["has_response"]:
                stats["no_response_no_row"] += 1
                continue
            pid = place_ids.get(r["content_id"])
            if pid is None:
                stats["not_in_db"] += 1
                continue
            v = r["values"]
            conn.execute(
                "INSERT INTO accessibility (place_id, grade, wheelchair, stroller, elevator, "
                "accessible_toilet, raw, source_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (pid, grade_of(v, rules), *(None if v[k] is None else int(v[k]) for k in ITEMS),
                 raw_json(r, rules), source_id))
            stats["inserted"] += 1
    return dict(stats)


def backup_once(db_path: Path, backup_path: Path) -> bool:
    if backup_path.exists():
        return False
    shutil.copy2(db_path, backup_path)
    return True


def cmd_load(args) -> int:
    rules = load_rules()
    raw_root = Path(args.raw)
    db_path = Path(args.db)
    backup = Path(args.backup) if args.backup else db_path.with_name(
        db_path.name.replace(".sqlite3", "") + ".pre_access.sqlite3")
    retrieved_at = latest_retrieved_at(raw_root)
    if retrieved_at is None:
        print("no OK entries in accessibility/fetch_log.jsonl; stop")
        return 1
    made = backup_once(db_path, backup)
    print(f"backup {'written' if made else 'kept (already exists)'}: {backup}")
    results = judge_all(raw_root, rules)
    conn = appdb.connect(db_path)
    try:
        stats = load(conn, results, rules, retrieved_at)
    finally:
        conn.close()
    print(f"load done: {stats}")
    return 0


# ---------------------------------------------------------------- report

def build_report(results: list[dict], rules: dict, db_path: Path | None,
                 center: tuple[float, float] | None = CENTER) -> dict:
    """center=None (기준점이 정해지지 않은 권역)이면 candidates_in_radius는 None."""
    counts = {it: Counter() for it in ITEMS}
    for r in results:
        conflicted = {c["item"] for c in r["conflicts"]}
        for it in ITEMS:
            key = "conflict" if it in conflicted else {True: "true", False: "false",
                                                        None: "null"}[r["values"][it]]
            counts[it][key] += 1

    rule_places = Counter()
    r1_phrase_places = Counter()
    for r in results:
        hit_rules = set()
        for it in ITEMS:
            for h in r["positive"][it]:
                hit_rules.add(h["rule"])
            for h in r["negative"][it]:
                hit_rules.add(h["rule"])
        if r["manual_review"]:
            hit_rules.add(rules["manual_review"]["id"])
        for rid in hit_rules:
            rule_places[rid] += 1
        phrases = {p for h in r["positive"]["wheelchair"] if h["rule"] == "R1" for p in h["phrases"]}
        for p in phrases:
            r1_phrase_places[p] += 1

    unmatched = [{"content_id": r["content_id"], "title": r["title"], **u}
                 for r in results for u in r["unmatched"]]
    rule_fields = {f for rule in rules["positive"] for f in rule["fields"]}
    by_type = Counter()
    for r in results:
        if r["values"]["wheelchair"] is True:
            by_type[TYPE_NAMES.get(r["contenttypeid"], r["contenttypeid"])] += 1

    candidates = None
    if center is not None and db_path is not None and db_path.is_file():
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT p.source_place_id, p.latitude, p.longitude, a.wheelchair, a.stroller "
                "FROM places p JOIN data_sources s ON s.id = p.source_id AND s.code = ? "
                "LEFT JOIN accessibility a ON a.place_id = p.id "
                "WHERE p.open_hours IS NOT NULL", (mapping.SOURCE["code"],)).fetchall()
        finally:
            conn.close()
        inside = [r for r in rows if haversine_m(center[0], center[1], r[1], r[2]) <= RADIUS_M]
        candidates = {"center": center, "radius_m": RADIUS_M,
                      "open_hours_not_null_in_radius": len(inside),
                      "wheelchair_true": sum(1 for r in inside if r[3] == 1),
                      "stroller_true": sum(1 for r in inside if r[4] == 1)}

    return {
        "rules_status": rules["status"],
        "places": len(results),
        "with_response": sum(1 for r in results if r["has_response"]),
        "item_counts": {it: {k: counts[it][k] for k in ("true", "false", "null", "conflict")}
                        for it in ITEMS},
        "rule_places": dict(sorted(rule_places.items())),
        "r1_phrase_places": {p: r1_phrase_places[p] for p in rules["positive"][0]["any"]},
        "responses_without_any_match": [r["content_id"] for r in results if r["has_response"]
                                        and not any(r["values"][it] is not None for it in ITEMS)
                                        and not r["conflicts"] and not r["manual_review"]],
        "unmatched_in_positive_rule_fields": [u for u in unmatched if u["field"] in rule_fields],
        "unmatched_other_fields_count": Counter(u["field"] for u in unmatched
                                                if u["field"] not in rule_fields),
        "negated_positive": [{"content_id": r["content_id"], "title": r["title"], **n}
                             for r in results for n in r["negated_positive"]],
        "wheelchair_true_by_type": {name: by_type[name] for name in TYPE_NAMES.values()},
        "candidates_in_radius": candidates,
        "manual_review": [{"content_id": r["content_id"], "title": r["title"], **m}
                          for r in results for m in r["manual_review"]],
        "conflicts": [{"content_id": r["content_id"], "title": r["title"], **c}
                      for r in results for c in r["conflicts"]],
        "door_only": [{"content_id": r["content_id"], "title": r["title"], **d}
                      for r in results for d in r["door_only"]],
        "overrides": [{"content_id": r["content_id"], "title": r["title"], **o}
                      for r in results for o in r["overrides"]],
        "override_missing": [m for r in results for m in r["override_missing"]],
    }


def cmd_report(args) -> int:
    rules = load_rules()
    report = build_report(judge_all(Path(args.raw), rules), rules,
                          Path(args.db) if args.db else None,
                          center=areas.get(args.area).report_center)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipelines.accessibility_judge")
    add_area_args(parser)
    sub = parser.add_subparsers(dest="cmd", required=True)
    load_p = sub.add_parser("load", help="판정 결과를 accessibility 테이블에 적재 (멱등)")
    load_p.add_argument("--db", default=None, help="기본 data/<권역>_sample.sqlite3")
    load_p.add_argument("--backup", default=None,
                        help="적재 전 복사본 (기본 <db 이름>.pre_access.sqlite3, 있으면 덮어쓰지 않음)")
    report_p = sub.add_parser("report", help="판정 집계 보고서 (네트워크 없음)")
    report_p.add_argument("--db", default=None, help="기본 data/<권역>_sample.sqlite3")
    report_p.add_argument("--out", default=str(DEFAULT_OUT))
    args = parse_area_args(parser, argv)
    if args.db is None:
        args.db = str(areas.get(args.area).default_db)
    return {"load": cmd_load, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
