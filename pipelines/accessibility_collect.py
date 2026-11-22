"""해운대 무장애 원본 수집과 문장 정리 — FR-008 (DEC-026 표현 목록 확정 전 준비 작업).

    python -m pipelines.accessibility_collect fetch --limit 5        # 처음 5곳만 (contentid 짝 확인용)
    python -m pipelines.accessibility_collect fetch --max-calls 300  # 나머지 (이어받기)
    python -m pipelines.accessibility_collect phrases [--out data/processed/accessibility_phrases.json]

- 대상: 국문 수집과 같은 해운대 대상 장소 (data/raw/tourapi/list + mapping.TARGET_CONTENT_TYPES).
- 원본: data/raw/tourapi/accessibility/<contentid>.json 한 장소에 한 파일. 파일이 있으면 다시 호출하지 않는다.
- 응답이 정상(HTTP 200, resultCode 0000)이 아니거나 전송 오류가 나면 그 자리에서 멈춘다. 재시도하지 않는다.
- phrases는 네트워크를 쓰지 않는다. 문장 원문과 필드 이름, 필드별 빈도표만 만들고
  DB의 accessibility 항목(wheelchair/stroller/elevator/accessible_toilet)으로 판정하지 않는다.
  TourAPI의 wheelchair·stroller 필드는 대여 여부일 수 있어 판정에 쓰지 않도록 표시만 한다.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sqlite3
import time

# haeundae_sample을 먼저 import해야 backend/가 sys.path에 들어가 mapping을 import할 수 있다
from pipelines.haeundae_sample import (OK, RAW_DIR, REPO_ROOT, RawStore, items_of, now_kst)
from pipelines import mapping  # noqa: E402
from pipelines.env import load_service_keys
from pipelines.tourapi_client import WITH_BASE, CallBudgetExceeded, TourApiClient, TourApiError

ACCESS_DIR = RAW_DIR / "accessibility"
OPERATION = "detailWithTour2"
DEFAULT_INTERVAL_S = 0.5
DEFAULT_OUT = REPO_ROOT / "data" / "processed" / "accessibility_phrases.json"
DEFAULT_DB = REPO_ROOT / "data" / "haeundae_sample.sqlite3"

# 응답 필드 (포털 Swagger, check 응답 988449와 같은 28개). 묶음 이름은 Swagger 항목 분류를 따름
FIELD_GROUPS = {
    "physical": ["parking", "publictransport", "route", "ticketoffice", "promotion", "wheelchair",
                 "exit", "elevator", "restroom", "auditorium", "room", "handicapetc"],
    "visual": ["braileblock", "helpdog", "guidehuman", "audioguide", "bigprint", "brailepromotion",
               "guidesystem", "blindhandicapetc"],
    "hearing": ["signguide", "videoguide", "hearingroom", "hearinghandicapetc"],
    "infant_family": ["stroller", "lactationroom", "babysparechair", "infantsfamilyetc"],
}
FIELDS = [f for group in FIELD_GROUPS.values() for f in group]
# 대여 여부일 수 있는 필드: 접근 가능 판정에 쓰지 않는다 (표시만)
RENTAL_FIELDS = {"wheelchair", "stroller"}
TOP_N = 30


class FetchStopped(RuntimeError):
    """A response was not OK. Fetch stops at that point (no retry)."""


def targets_from_raw(raw_root: Path = RAW_DIR) -> list[str]:
    """해운대 대상 contentid (국문 fetch와 같은 규칙, 같은 순서)."""
    store = RawStore(raw_root)
    pairs = set()
    for path in sorted(store.path("list").glob("areaBasedList2_p*.json")):
        for it in items_of(json.loads(path.read_text(encoding="utf-8"))):
            if str(it.get("contenttypeid")) in mapping.TARGET_CONTENT_TYPES:
                pairs.add(str(it["contentid"]))
    ids = sorted(pairs, key=lambda cid: (len(cid), cid))
    return [cid for cid in ids if mapping.valid_source_place_id(cid)]


# ---------------------------------------------------------------- fetch

def fetch(client: TourApiClient, store: RawStore, ids: list[str], *, interval_s: float,
          out=print) -> dict:
    stats = {"skipped_existing": 0, "ok": 0, "ok_empty": 0, "failed": 0}
    first = True
    for cid in ids:
        name = f"{cid}.json"
        if store.has(name):
            stats["skipped_existing"] += 1
            continue
        if not first and interval_s > 0:
            time.sleep(interval_s)
        first = False
        params = {"contentId": cid}
        entry = {"time": now_kst(), "operation": OPERATION, "params": params}
        try:
            resp = client.get(OPERATION, params)
        except TourApiError as error:
            stats["failed"] += 1
            store.log({**entry, "status": None, "resultCode": None, "file": None,
                       "error": type(error).__name__})
            raise FetchStopped(str(error)) from None
        code, msg = resp.result()
        entry.update(status=resp.status, resultCode=code)
        if resp.status != 200 or code != OK:
            stats["failed"] += 1
            store.log({**entry, "file": None, "resultMsg": msg})
            raise FetchStopped(f"{OPERATION} contentId={cid}: HTTP {resp.status}, "
                               f"resultCode={code}, resultMsg={msg} ({resp.url_masked})")
        store.save(resp.body, name)
        items = items_of(json.loads(resp.body.decode("utf-8")))
        store.log({**entry, "file": name, "items": len(items)})
        stats["ok"] += 1
        if not items:
            stats["ok_empty"] += 1
    return stats


def cmd_fetch(args) -> int:
    ids = targets_from_raw(Path(args.raw))
    if args.limit is not None:
        ids = ids[:args.limit]
    keys = load_service_keys()
    client = TourApiClient(keys.with_, WITH_BASE, max_calls=args.max_calls)
    store = RawStore(Path(args.raw) / "accessibility")
    started = time.monotonic()
    status, stats = "complete", {}
    try:
        stats = fetch(client, store, ids, interval_s=args.interval, out=print)
    except CallBudgetExceeded:
        status = f"stopped: --max-calls {args.max_calls} reached (run again to continue)"
    except FetchStopped as error:
        status = f"stopped on error: {error}"
    have = sum(1 for cid in ids if store.has(f"{cid}.json"))
    print(f"fetch {status}")
    print(f"targets={len(ids)}, files present={have}, calls this run={client.calls}, "
          f"stats={stats}, elapsed {time.monotonic() - started:.1f}s, key name: {keys.with_name}")
    return 0 if status == "complete" or status.startswith("stopped: --max-calls") else 1


# ---------------------------------------------------------------- phrases (offline)

_SPACE = re.compile(r"\s+")
_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_PAREN = re.compile(r"\s*\([^()]*\)")
_SUFFIX = re.compile(r"_(무장애|시각장애인|청각장애인|영유아가족)\s*편의시설$")


def normalize(text: str) -> str:
    """빈도 집계용: 앞뒤 공백 제거, 연속 공백 하나로. 원문은 places에 그대로 둔다."""
    return _SPACE.sub(" ", text).strip()


def phrase_type(text: str) -> str:
    """문장 유형 묶음용 텍스트 정규화 (뜻 판정 없음).

    `<br/>`→공백, 괄호 속 세부(대수·층·위치) 제거, 꼬리말 `_무장애 편의시설` 등 제거,
    앞의 `*`·끝의 `.` 제거. 묶음 키는 공백을 모두 지운 문자열이다(`주 출입구`=`주출입구`).
    """
    text = normalize(_BR.sub(" ", text))
    text = _SUFFIX.sub("", text)
    while _PAREN.search(text):
        text = _PAREN.sub("", text)
    text = _SUFFIX.sub("", text.strip()).strip().lstrip("*").strip().rstrip(".").strip()
    return text


def type_key(text: str) -> str:
    return _SPACE.sub("", text)


def listed_from_raw(raw_root: Path) -> dict[str, dict]:
    store = RawStore(raw_root)
    listed: dict[str, dict] = {}
    for path in sorted(store.path("list").glob("areaBasedList2_p*.json")):
        for it in items_of(json.loads(path.read_text(encoding="utf-8"))):
            listed.setdefault(str(it["contentid"]), it)
    return listed


def db_source_ids(db_path: Path) -> set[str] | None:
    if not db_path.is_file():
        return None
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        return {row[0] for row in conn.execute("SELECT source_place_id FROM places")}
    finally:
        conn.close()


def build_phrases(raw_root: Path, db_path: Path | None) -> dict:
    ids = targets_from_raw(raw_root)
    listed = listed_from_raw(raw_root)
    store = RawStore(raw_root / "accessibility")
    db_ids = db_source_ids(db_path) if db_path else None

    places, missing_file, unknown_fields = [], [], Counter()
    counts = {f: Counter() for f in FIELDS}
    type_counts = {f: Counter() for f in FIELDS}          # type_key -> 건수
    type_labels = {f: {} for f in FIELDS}                 # type_key -> Counter(표시 문자열)
    type_examples = {f: {} for f in FIELDS}               # type_key -> 원문 예 (최대 3)
    nonempty = Counter()
    response_by_type, targets_by_type = Counter(), Counter()
    with_response = matched = 0
    for cid in ids:
        type_id = str(listed.get(cid, {}).get("contenttypeid"))
        targets_by_type[type_id] += 1
        if not store.has(f"{cid}.json"):
            missing_file.append(cid)
            continue
        items = items_of(store.read_json(f"{cid}.json"))
        record = {"content_id": cid, "title": listed.get(cid, {}).get("title"),
                  "contenttypeid": type_id,
                  "in_db": None if db_ids is None else cid in db_ids,
                  "has_response": bool(items), "contentid_match": None, "fields": {}}
        if items:
            with_response += 1
            response_by_type[type_id] += 1
            item = items[0]
            record["contentid_match"] = str(item.get("contentid")) == cid
            matched += record["contentid_match"]
            for key in item:
                if key != "contentid" and key not in FIELDS:
                    unknown_fields[key] += 1
            for field in FIELDS:
                value = item.get(field)
                text = normalize(value) if isinstance(value, str) else ""
                if text:
                    record["fields"][field] = value  # 원문 그대로
                    nonempty[field] += 1
                    counts[field][text] += 1
                    label = phrase_type(value)
                    key = type_key(label)
                    type_counts[field][key] += 1
                    type_labels[field].setdefault(key, Counter())[label] += 1
                    examples = type_examples[field].setdefault(key, [])
                    if text not in examples and len(examples) < 3:
                        examples.append(text)
        places.append(record)

    field_stats = {}
    for group, fields in FIELD_GROUPS.items():
        for field in fields:
            field_stats[field] = {
                "group": group,
                "nonempty": nonempty[field],
                "empty": with_response - nonempty[field],
                "empty_rate": round((with_response - nonempty[field]) / with_response, 4)
                if with_response else None,
                "distinct_phrases": len(counts[field]),
                "distinct_types": len(type_counts[field]),
                "rental_field_not_for_judgement": field in RENTAL_FIELDS,
            }

    def by_count(counter: Counter) -> list:
        return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))

    frequency = {field: [{"phrase": p, "count": n} for p, n in by_count(counts[field])]
                 for field in FIELDS if counts[field]}
    type_frequency = {
        field: [{"type": type_labels[field][k].most_common(1)[0][0], "count": n,
                 "examples": type_examples[field][k]} for k, n in by_count(type_counts[field])]
        for field in FIELDS if type_counts[field]}
    top = []
    for field, rows in type_frequency.items():
        top.extend({"field": field, "type": r["type"], "count": r["count"],
                    "rental_field_not_for_judgement": field in RENTAL_FIELDS} for r in rows)
    top = sorted(top, key=lambda r: (-r["count"], FIELDS.index(r["field"]), r["type"]))[:TOP_N]

    return {
        "generated_at": now_kst(),
        "source": {"provider": "한국관광공사", "service": "무장애 여행 정보_GW (KorWithService2)",
                   "operation": OPERATION, "url": "https://www.data.go.kr/data/15101897/openapi.do"},
        "note": ("판정하지 않음: DEC-026 표현 목록 확정 전. 문장 원문·필드 이름·빈도만 정리. "
                 "wheelchair·stroller 필드는 대여 여부일 수 있어 판정에 쓰지 않음 "
                 "(rental_field_not_for_judgement=true)."),
        "summary": {
            "targets": len(ids), "files": len(ids) - len(missing_file),
            "missing_file": missing_file, "with_response": with_response,
            "without_response": len(ids) - len(missing_file) - with_response,
            "contentid_matched": matched,
            "in_db": None if db_ids is None else sum(1 for p in places if p["in_db"]),
            "unknown_fields": dict(unknown_fields),
            "targets_by_contenttypeid": dict(sorted(targets_by_type.items())),
            "with_response_by_contenttypeid": dict(sorted(response_by_type.items())),
        },
        "field_groups": FIELD_GROUPS,
        "field_stats": field_stats,
        "type_frequency_by_field": type_frequency,
        "frequency_by_field": frequency,
        "top_types": top,
        "places": places,
    }


def cmd_phrases(args) -> int:
    report = build_phrases(Path(args.raw), Path(args.db) if args.db else None)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipelines.accessibility_collect")
    parser.add_argument("--raw", default=str(RAW_DIR), help="원본 폴더 (기본 data/raw/tourapi)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    fetch_p = sub.add_parser("fetch", help="detailWithTour2 원본 수집 (이어받기)")
    fetch_p.add_argument("--max-calls", type=int, default=300)
    fetch_p.add_argument("--limit", type=int, default=None, help="대상 앞에서 N곳만")
    fetch_p.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_S, help="호출 간격(초)")
    phrases_p = sub.add_parser("phrases", help="문장 원문·필드별 빈도표 (네트워크 없음)")
    phrases_p.add_argument("--out", default=str(DEFAULT_OUT))
    phrases_p.add_argument("--db", default=str(DEFAULT_DB), help="source_place_id 대조용 (읽기 전용)")
    args = parser.parse_args(argv)
    if args.cmd == "fetch" and (args.max_calls < 1 or (args.limit is not None and args.limit < 1)):
        parser.error("--max-calls and --limit must be >= 1")
    return {"fetch": cmd_fetch, "phrases": cmd_phrases}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
