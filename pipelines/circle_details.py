"""후보 원 안 대상의 상세 원본 수집 — FR-020, FR-008, 이슈 #36 (PM 결정 11/21: 권역 = 중심 1.5km 안).

    python -m pipelines.circle_details --center 1046349 --center 126078 --dry-run
    python -m pipelines.circle_details --center 1046349 --center 126078 --max-calls 790

- 대상: 저장된 부산 시군구 목록 전체(areas.sigungu_raw_dir) 중 mapping.TARGET_CONTENT_TYPES이고,
  --center로 준 contentid(목록에 있는 장소) 좌표에서 --radius m(직선, 하버사인) 안인 장소의 합집합.
- 원본은 장소가 속한 시군구 폴더에 저장한다: <폴더>/common, <폴더>/intro (국문 관광정보),
  <폴더>/accessibility (무장애 여행 정보). 이미 있는 파일은 다시 호출하지 않는다.
- --max-calls는 상세기능별(detailCommon2·detailIntro2·detailWithTour2) 한도다. 다다르면 그 기능에서 멈춘다.
- 응답이 정상(HTTP 200, resultCode 0000)이 아니거나 전송 오류면 그 자리에서 전체를 멈춘다. 재시도하지 않는다.
- 호출 간격: 국문은 haeundae_sample fetch와 같이 간격 없음, 무장애는 accessibility_collect와 같이 0.5초.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import time

from pipelines.haeundae_sample import (Fetcher, FetchStopped, RawStore, busan_sigungu, items_of)
from pipelines import accessibility_collect, areas, mapping
from pipelines.env import load_service_keys
from pipelines.tourapi_client import KOR_BASE, WITH_BASE, CallBudgetExceeded, TourApiClient, TourApiError
from app.data.geo import haversine_m  # noqa: E402  (backend/ 경로는 haeundae_sample이 넣음)

DEFAULT_RADIUS_M = 1500
OPERATIONS = ("detailCommon2", "detailIntro2", "detailWithTour2")


@dataclass(frozen=True)
class Target:
    content_id: str
    type_id: str
    sigungu: str
    latitude: float
    longitude: float


def load_listed(known: dict[str, str] | None = None) -> dict[str, tuple[dict, str]]:
    """{contentid: (list item, 시군구 코드)} over every stored 부산 시군구 list."""
    known = busan_sigungu() if known is None else known
    listed: dict[str, tuple[dict, str]] = {}
    for code in known:
        for path in sorted((areas.sigungu_raw_dir(code) / "list").glob("areaBasedList2_p*.json")):
            for item in items_of(json.loads(path.read_text(encoding="utf-8"))):
                listed.setdefault(str(item["contentid"]), (item, code))
    return listed


def _coord(item: dict) -> tuple[float, float] | None:
    try:
        lat, lon = float(item.get("mapy")), float(item.get("mapx"))
    except (TypeError, ValueError):
        return None
    return None if lat == 0 or lon == 0 else (lat, lon)


def targets_in_circles(listed: dict[str, tuple[dict, str]], center_ids: list[str],
                       radius_m: float = DEFAULT_RADIUS_M) -> list[Target]:
    centers = []
    for cid in center_ids:
        if cid not in listed or _coord(listed[cid][0]) is None:
            raise ValueError(f"center {cid} is not a listed place with coordinates")
        centers.append(_coord(listed[cid][0]))
    found = {}
    for cid, (item, code) in listed.items():
        type_id = str(item.get("contenttypeid"))
        point = _coord(item)
        if type_id not in mapping.TARGET_CONTENT_TYPES or point is None:
            continue
        if not mapping.valid_source_place_id(cid):
            continue  # never request with an ID we would refuse to store
        if any(haversine_m(c[0], c[1], point[0], point[1]) <= radius_m for c in centers):
            found[cid] = Target(cid, type_id, code, point[0], point[1])
    return sorted(found.values(), key=lambda t: (t.sigungu, len(t.content_id), t.content_id))


def pending(targets: list[Target]) -> dict[str, list[Target]]:
    """Targets whose file is missing, per operation."""
    out = {op: [] for op in OPERATIONS}
    for t in targets:
        root = areas.sigungu_raw_dir(t.sigungu)
        for op, sub in zip(OPERATIONS, ("common", "intro", "accessibility")):
            if not (root / sub / f"{t.content_id}.json").is_file():
                out[op].append(t)
    return out


def fetch_kor(client: TourApiClient, targets: list[Target], operation: str) -> int:
    """detailCommon2 or detailIntro2 for targets. Returns files saved. Raises on error/budget."""
    saved = 0
    stores: dict[str, Fetcher] = {}
    for t in targets:
        fetcher = stores.setdefault(t.sigungu, Fetcher(client, RawStore(areas.sigungu_raw_dir(t.sigungu)),
                                                       out=lambda *a: None))
        before = fetcher.saved
        if operation == "detailCommon2":
            fetcher.get(operation, {"contentId": t.content_id}, "common", f"{t.content_id}.json")
        else:
            fetcher.get(operation, {"contentId": t.content_id, "contentTypeId": t.type_id},
                        "intro", f"{t.content_id}.json")
        saved += fetcher.saved - before
    return saved


def fetch_with(client: TourApiClient, targets: list[Target], interval_s: float) -> Counter:
    stats: Counter = Counter()
    by_code: dict[str, list[str]] = {}
    for t in targets:
        by_code.setdefault(t.sigungu, []).append(t.content_id)
    for code, ids in by_code.items():
        store = RawStore(areas.sigungu_raw_dir(code) / "accessibility")
        stats.update(accessibility_collect.fetch(client, store, ids, interval_s=interval_s, out=lambda *a: None))
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipelines.circle_details")
    parser.add_argument("--center", action="append", required=True, help="중심 장소 contentid (여러 번)")
    parser.add_argument("--radius", type=float, default=DEFAULT_RADIUS_M)
    parser.add_argument("--max-calls", type=int, default=790, help="상세기능별 호출 한도")
    parser.add_argument("--interval", type=float, default=accessibility_collect.DEFAULT_INTERVAL_S,
                        help="무장애 호출 간격(초)")
    parser.add_argument("--dry-run", action="store_true", help="호출 없이 대상·남은 호출 수만")
    args = parser.parse_args(argv)
    if args.max_calls < 1:
        parser.error("--max-calls must be >= 1")

    targets = targets_in_circles(load_listed(), args.center, args.radius)
    todo = pending(targets)
    print(f"targets={len(targets)} by sigungu={dict(Counter(t.sigungu for t in targets))}")
    print("to call: " + ", ".join(f"{op}={len(v)}" for op, v in todo.items()))
    if args.dry_run:
        return 0
    if any(len(v) > args.max_calls for v in todo.values()):
        print(f"stop: more than --max-calls {args.max_calls} calls needed for one operation")
        return 1

    keys = load_service_keys()
    calls: dict[str, int] = {}
    status = "complete"
    started = time.monotonic()
    try:
        for op in ("detailCommon2", "detailIntro2"):
            client = TourApiClient(keys.kor, KOR_BASE, max_calls=args.max_calls)
            try:
                fetch_kor(client, todo[op], op)
            finally:
                calls[op] = client.calls
        client = TourApiClient(keys.with_, WITH_BASE, max_calls=args.max_calls)
        try:
            stats = fetch_with(client, todo["detailWithTour2"], args.interval)
            print(f"detailWithTour2 stats={dict(stats)}")
        finally:
            calls["detailWithTour2"] = client.calls
    except CallBudgetExceeded:
        status = f"stopped: --max-calls {args.max_calls} reached"
    except (FetchStopped, accessibility_collect.FetchStopped, TourApiError) as error:
        status = f"stopped on error: {error}"
    left = pending(targets)
    print(f"circle_details {status}; calls this run={calls}, elapsed {time.monotonic() - started:.1f}s, "
          f"key names: 국문={keys.kor_name}, 무장애={keys.with_name}")
    print("still missing: " + ", ".join(f"{op}={len(v)}" for op, v in left.items()))
    return 0 if status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
