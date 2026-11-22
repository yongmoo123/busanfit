"""4개 권역 원 기준 DB 만들기 — FR-020, FR-007, FR-008, 이슈 #36 (PM 결정 11/21: 권역 = 중심 반경 안).

    python -m pipelines.circle_build --db data/share/busanfit_v3.sqlite3 [--report data/processed/v3_report.json]

- 네트워크 없음. 저장된 부산 시군구 원본 전체(``areas.sigungu_raw_dir``: list·common·intro·accessibility)를 합쳐 읽는다.
- 각 장소의 권역 = ``config/retrieval.json`` ``areaCenters`` 중심에서 반경(``BUSANFIT_WALK_RADIUS_M``, 기본 1500 m)
  안인 권역(``pipelines/circles.py``). 좌표는 DB에 들어가는 값(공통정보가 목록 값을 덮은 것)으로 판정한다.
- 어느 원에도 안 들어가는 대상 유형 장소는 건너뛰고 건수만 보고한다. 두 원에 동시에 들어가면 멈춘다.
- 장소 행은 ``mapping.build_rows``(카테고리·운영시간 파서·체류시간, 권역마다 한 번), 무장애 값·grade는
  ``accessibility_judge``(DEC-026 규칙, ``grade_of``), 두 출처의 license는 ``mapping.PORTAL_LICENSE``를 그대로 쓴다.
- 같은 경로에 파일이 있으면 거절한다(``db.create_database``). 같은 원본이면 같은 테이블 내용이 나온다.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
import json
from pathlib import Path
import time

from pipelines.haeundae_sample import RawStore, busan_sigungu, items_of, load_raw
from pipelines import accessibility_judge, areas, circles, duty_free_ids, mapping

GRADES = ("VERIFIED", "UNSUITABLE", "UNKNOWN")


@dataclass
class Merged:
    """Raw files of every stored 시군구, keyed by contentid (first 시군구 in code order wins)."""
    listed: dict[str, dict] = field(default_factory=dict)
    commons: dict[str, dict | None] = field(default_factory=dict)
    intros: dict[str, dict | None] = field(default_factory=dict)
    fetched_at: dict[str, str | None] = field(default_factory=dict)
    sigungu: dict[str, str] = field(default_factory=dict)
    retrieved_at: str | None = None
    duplicates: list[str] = field(default_factory=list)


def merge_raw(codes: list[str], lcls_root: Path = areas.RAW_ROOT) -> tuple[Merged, dict[str, str]]:
    merged = Merged()
    times = []
    for code in sorted(codes):
        sample = load_raw(RawStore(areas.sigungu_raw_dir(code)))
        if sample.retrieved_at:
            times.append(sample.retrieved_at)
        for cid, item in sample.listed.items():
            if cid in merged.listed:
                merged.duplicates.append(cid)
                continue
            merged.listed[cid] = item
            merged.commons[cid] = sample.commons.get(cid)
            merged.intros[cid] = sample.intros.get(cid)
            merged.fetched_at[cid] = sample.fetched_at.get(cid)
            merged.sigungu[cid] = code
    merged.retrieved_at = max(times) if times else None
    lcls = load_raw(RawStore(lcls_root)).lcls_names  # 분류체계 이름은 해운대 수집 때 받은 lcls/ 하나
    return merged, lcls


def point_of(item: dict, common: dict | None) -> tuple[float, float] | None:
    """The coordinate build_rows would store: common fields over the list item."""
    base = {**item, **{k: v for k, v in (common or {}).items() if mapping.text(v) is not None}}
    lat = mapping._coordinate(base.get("mapy"), -90, 90)
    lon = mapping._coordinate(base.get("mapx"), -180, 180)
    return None if lat is None or lon is None else (lat, lon)


@dataclass
class Assignment:
    by_area: dict[str, list[str]]
    outside: list[str]          # target-type places in no circle (skipped)
    no_point: list[str]         # target-type places without a usable coordinate (build_rows would skip)
    non_target: int             # listed places of other content types (not considered)


def assign_areas(merged: Merged, centers: circles.Centers, radius: float) -> Assignment:
    """Area of every target-type place. Raises circles.CircleOverlap if a place is in two circles."""
    by_area: dict[str, list[str]] = {area: [] for area in sorted(centers)}
    outside, no_point, non_target = [], [], 0
    for cid in sorted(merged.listed, key=lambda v: (len(v), v)):
        item = merged.listed[cid]
        if str(item.get("contenttypeid") or "") not in mapping.TARGET_CONTENT_TYPES:
            non_target += 1
            continue
        point = point_of(item, merged.commons.get(cid))
        if point is None:
            no_point.append(cid)
            continue
        area = circles.area_of(point[0], point[1], centers, radius, label=f"contentid {cid}")
        if area is None:
            outside.append(cid)
        else:
            by_area[area].append(cid)
    return Assignment(by_area, outside, no_point, non_target)


def build_area_rows(merged: Merged, lcls: dict[str, str], assignment: Assignment) -> dict[str, mapping.BuildResult]:
    results = {}
    for area, ids in assignment.by_area.items():
        sample = mapping.RawSample(
            listed={cid: merged.listed[cid] for cid in ids},
            commons={cid: merged.commons.get(cid) for cid in ids},
            intros={cid: merged.intros.get(cid) for cid in ids},
            lcls_names=lcls,
            fetched_at={cid: merged.fetched_at.get(cid) for cid in ids},
            retrieved_at=merged.retrieved_at)
        results[area] = mapping.build_rows(sample, area=area)
    return results


def combine(results: dict[str, mapping.BuildResult], retrieved_at: str | None) -> mapping.BuildResult:
    combined = mapping.BuildResult(retrieved_at=retrieved_at)
    for result in results.values():
        combined.rows.extend(result.rows)
    combined.rows.sort(key=lambda r: (len(r["source_place_id"]), r["source_place_id"]))
    return combined


def judge_places(merged: Merged, content_ids: list[str], rules: dict) -> tuple[list[dict], list[str]]:
    """accessibility_judge results for the loaded places, from each place's 시군구 folder."""
    out, missing = [], []
    for cid in content_ids:
        store = RawStore(areas.sigungu_raw_dir(merged.sigungu[cid]) / "accessibility")
        meta = merged.listed[cid]
        base = {"content_id": cid, "title": meta.get("title"), "contenttypeid": str(meta.get("contenttypeid"))}
        if not store.has(f"{cid}.json"):
            missing.append(cid)
            out.append({**base, "has_file": False, **accessibility_judge.judge(None, rules)})
            continue
        items = items_of(store.read_json(f"{cid}.json"))
        out.append({**base, "has_file": True, **accessibility_judge.judge(items[0] if items else None, rules)})
    return out, missing


def accessibility_retrieved_at(codes: set[str]) -> str | None:
    times = [t for t in (accessibility_judge.latest_retrieved_at(areas.sigungu_raw_dir(c)) for c in sorted(codes)) if t]
    return max(times) if times else None


def area_summary(conn, area: str) -> dict:
    places = conn.execute("SELECT COUNT(*) FROM places WHERE area = ?", (area,)).fetchone()[0]
    null_hours = conn.execute("SELECT COUNT(*) FROM places WHERE area = ? AND open_hours IS NULL",
                              (area,)).fetchone()[0]
    grades = dict(conn.execute(
        "SELECT a.grade, COUNT(*) FROM accessibility a JOIN places p ON p.id = a.place_id "
        "WHERE p.area = ? GROUP BY a.grade", (area,)).fetchall())
    rows = sum(grades.values())
    by_place = {g: grades.get(g, 0) for g in GRADES}
    by_place["UNKNOWN"] += places - rows  # 행 없음 = API에서 UNKNOWN
    wheel = conn.execute("SELECT COUNT(*) FROM accessibility a JOIN places p ON p.id = a.place_id "
                         "WHERE p.area = ? AND a.wheelchair = 1", (area,)).fetchone()[0]
    stroller = conn.execute("SELECT COUNT(*) FROM accessibility a JOIN places p ON p.id = a.place_id "
                            "WHERE p.area = ? AND a.stroller = 1", (area,)).fetchone()[0]
    return {"places": places, "open_hours_null": null_hours, "accessibility_rows": rows,
            "grade_by_place": by_place, "grade_unknown_with_row": grades.get("UNKNOWN", 0),
            "wheelchair_true": wheel, "stroller_true": stroller}


def duty_free_check(merged: Merged, loaded: list[str], exclusion_path: Path, exceptions: list[dict]) -> dict:
    """SH040300 places in the DB must be in the exclusion list or the exception list."""
    listed_ids = set(json.loads(exclusion_path.read_text(encoding="utf-8"))["placeIds"])
    excepted = {e["placeId"] for e in exceptions}
    sh = [cid for cid in loaded if merged.listed[cid].get("lclsSystm3") in duty_free_ids.DUTY_FREE_CODES]
    uncovered = [cid for cid in sh if duty_free_ids.place_id(cid) not in listed_ids | excepted]
    return {"sh040300_in_db": len(sh), "excepted_in_db": sorted(c for c in sh if duty_free_ids.place_id(c) in excepted),
            "not_in_exclusion_or_exceptions": uncovered}


def run(db_path: Path, centers: circles.Centers, radius: float, codes: list[str] | None = None,
        lcls_root: Path = areas.RAW_ROOT, exclusion_path: Path = duty_free_ids.OUTPUT,
        exceptions_path: Path = duty_free_ids.EXCEPTIONS) -> dict:
    from app.data import db  # backend/ is on sys.path (pipelines.circles)

    started = time.monotonic()
    codes = sorted(busan_sigungu()) if codes is None else codes
    merged, lcls = merge_raw(codes, lcls_root)
    assignment = assign_areas(merged, centers, radius)
    results = build_area_rows(merged, lcls, assignment)
    combined = combine(results, merged.retrieved_at)
    loaded = [r["source_place_id"] for r in combined.rows]
    rules = accessibility_judge.load_rules()
    judged, acc_missing = judge_places(merged, loaded, rules)
    acc_time = accessibility_retrieved_at({merged.sigungu[cid] for cid in loaded})
    if acc_time is None:
        raise RuntimeError("no OK entries in any accessibility/fetch_log.jsonl")

    path = db.create_database(db_path)  # refuses to overwrite an existing file
    conn = db.connect(path)
    try:
        mapping.insert_rows(conn, combined)
        conn.commit()
        acc_stats = accessibility_judge.load(conn, judged, rules, acc_time)
        summary = {area: area_summary(conn, area) for area in sorted(centers)}
    finally:
        conn.close()
    exceptions = duty_free_ids.load_exceptions(exceptions_path)
    return {
        "db": str(path),
        "centers": {a: list(c) for a, c in sorted(centers.items())},
        "radius_m": radius,
        "sigungu_codes": codes,
        "listed_total": len(merged.listed),
        "listed_duplicates_across_sigungu": sorted(merged.duplicates),
        "non_target_type": assignment.non_target,
        "target_outside_circles_skipped": len(assignment.outside),
        "target_outside_by_sigungu": dict(sorted(Counter(merged.sigungu[c] for c in assignment.outside).items())),
        "target_no_coordinate": assignment.no_point,
        "assigned_by_area": {a: len(v) for a, v in assignment.by_area.items()},
        "build_skipped_by_area": {a: dict(sorted(r.skipped.items())) for a, r in results.items()},
        "loaded": len(loaded),
        "areas": summary,
        "accessibility_load": acc_stats,
        "accessibility_file_missing": acc_missing,
        "tourapi_kor_retrieved_at": merged.retrieved_at,
        "barrierfree_retrieved_at": acc_time,
        "duty_free": duty_free_check(merged, loaded, exclusion_path, exceptions),
        "build_reports": {a: r.report() for a, r in results.items()},
        "elapsed_s": round(time.monotonic() - started, 2),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipelines.circle_build")
    parser.add_argument("--db", required=True, help="새 DB 파일 (있으면 거절)")
    parser.add_argument("--report", default=None, help="보고서 JSON 경로")
    args = parser.parse_args(argv)
    centers = circles.load_centers(required=areas.AREA_CODES)
    try:
        report = run(Path(args.db), centers, circles.radius_m())
    except circles.CircleOverlap as error:
        print(f"stop: {error}")
        return 1
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(text + "\n", encoding="utf-8")
    brief = {k: report[k] for k in ("loaded", "assigned_by_area", "target_outside_circles_skipped",
                                    "accessibility_load", "accessibility_file_missing", "duty_free")}
    print(f"built {report['db']}")
    print(json.dumps({**brief, "areas": report["areas"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
