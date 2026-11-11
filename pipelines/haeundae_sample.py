"""해운대구 표본 수집(fetch)과 적재(build) — 이슈 #7 작업 C, FR-020.

    python -m pipelines.haeundae_sample check                 # 서비스마다 1건 호출, HTTP 상태·resultCode만 출력
    python -m pipelines.haeundae_sample fetch --max-calls 200 # 원본을 data/raw/tourapi/ 에 저장 (이어받기)
    python -m pipelines.haeundae_sample build --db data/busanfit.sqlite3 [--report data/processed/report.json]

fetch만 네트워크를 쓴다. build는 data/raw/만 읽어 새 DB 파일을 만들며, 같은 원본이면 같은 DB가 나온다.
키는 .env 또는 환경변수에서만 읽고(pipelines.env), 출력하는 URL은 serviceKey를 가린다.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from pipelines import mapping  # noqa: E402
from pipelines.env import load_service_keys  # noqa: E402
from pipelines.tourapi_client import (KOR_BASE, WITH_BASE, CallBudgetExceeded,  # noqa: E402
                                      TourApiClient, TourApiError)

RAW_DIR = REPO_ROOT / "data" / "raw" / "tourapi"
KST = timezone(timedelta(hours=9))
OK = "0000"
BUSAN_NAME = "부산광역시"
HAEUNDAE_NAME = "해운대구"
LIST_ROWS = 1000
CHECK_WITH_CONTENT_ID = "988449"  # 포털 Swagger의 무장애정보조회 예시 contentId


class FetchStopped(RuntimeError):
    """A response was not OK. Fetch stops at that point (no retry)."""


def now_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


# ---------------------------------------------------------------- raw store

class RawStore:
    """Files under data/raw/tourapi/. A file exists only when its response was OK."""

    def __init__(self, root: Path = RAW_DIR):
        self.root = root

    def path(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)

    def has(self, *parts: str) -> bool:
        return self.path(*parts).is_file()

    def save(self, body: bytes, *parts: str) -> Path:
        target = self.path(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        tmp.write_bytes(body)
        os.replace(tmp, target)
        return target

    def log(self, entry: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / "fetch_log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")

    def read_json(self, *parts: str) -> dict:
        return json.loads(self.path(*parts).read_text(encoding="utf-8"))


def items_of(data: dict) -> list[dict]:
    """TourAPI body.items.item may be a list, a single dict, or '' when empty."""
    body = data["response"]["body"]
    items = body.get("items")
    if not items:
        return []
    item = items.get("item", [])
    return item if isinstance(item, list) else [item]


# ---------------------------------------------------------------- fetch

class Fetcher:
    def __init__(self, client: TourApiClient, store: RawStore, out=print):
        self.client = client
        self.store = store
        self.out = out
        self.saved = 0

    def get(self, operation: str, params: dict, *parts: str) -> dict:
        """Return the stored JSON, fetching it first if missing. Raises FetchStopped on non-OK."""
        if self.store.has(*parts):
            return self.store.read_json(*parts)
        resp = self.client.get(operation, params)
        code, msg = resp.result()
        entry = {"time": now_kst(), "operation": operation, "params": params,
                 "status": resp.status, "resultCode": code, "file": "/".join(parts)}
        if resp.status != 200 or code != OK:
            entry["file"] = None
            self.store.log(entry)
            raise FetchStopped(f"{operation} {params}: HTTP {resp.status}, resultCode={code}, "
                               f"resultMsg={msg} ({resp.url_masked})")
        self.store.save(resp.body, *parts)
        self.store.log(entry)
        self.saved += 1
        return json.loads(resp.body.decode("utf-8"))


def find_code(items: list[dict], name: str) -> str:
    found = [it["code"] for it in items if it.get("name") == name]
    if len(found) != 1:
        raise FetchStopped(f"법정동 코드에서 {name!r}를 하나로 찾지 못함 ({len(found)}개)")
    return str(found[0])


def run_fetch(fetcher: Fetcher) -> dict:
    regions = fetcher.get("ldongCode2", {"lDongListYn": "N", "numOfRows": 100, "pageNo": 1},
                          "ldong", "regions.json")
    busan = find_code(items_of(regions), BUSAN_NAME)
    sigungu = fetcher.get("ldongCode2", {"lDongRegnCd": busan, "lDongListYn": "N",
                                         "numOfRows": 100, "pageNo": 1},
                          "ldong", f"{busan}.json")
    haeundae = find_code(items_of(sigungu), HAEUNDAE_NAME)

    page = 1
    while True:
        params = {"lclsSystmListYn": "Y", "numOfRows": LIST_ROWS, "pageNo": page}
        data = fetcher.get("lclsSystmCode2", params, "lcls", f"list_p{page}.json")
        if page * LIST_ROWS >= int(data["response"]["body"].get("totalCount") or 0):
            break
        page += 1

    page, listed = 1, []
    while True:
        params = {"lDongRegnCd": busan, "lDongSignguCd": haeundae, "arrange": "A",
                  "numOfRows": LIST_ROWS, "pageNo": page}
        data = fetcher.get("areaBasedList2", params, "list", f"areaBasedList2_p{page}.json")
        listed.extend(items_of(data))
        if page * LIST_ROWS >= int(data["response"]["body"].get("totalCount") or 0):
            break
        page += 1

    targets = sorted({(str(it["contentid"]), str(it["contenttypeid"])) for it in listed
                      if str(it.get("contenttypeid")) in mapping.TARGET_CONTENT_TYPES},
                     key=lambda pair: (len(pair[0]), pair[0]))
    for content_id, type_id in targets:
        if not mapping.valid_source_place_id(content_id):
            continue  # build reports it; never request with an ID we would refuse to store
        fetcher.get("detailCommon2", {"contentId": content_id}, "common", f"{content_id}.json")
        fetcher.get("detailIntro2", {"contentId": content_id, "contentTypeId": type_id},
                    "intro", f"{content_id}.json")
    return {"busan": busan, "haeundae": haeundae, "listed": len(listed), "targets": len(targets)}


def cmd_fetch(args) -> int:
    keys = load_service_keys()
    client = TourApiClient(keys.kor, KOR_BASE, max_calls=args.max_calls)
    fetcher = Fetcher(client, RawStore(Path(args.raw)))
    started = time.monotonic()
    status = "complete"
    info: dict = {}
    try:
        info = run_fetch(fetcher)
    except CallBudgetExceeded:
        status = f"stopped: --max-calls {args.max_calls} reached (run again to continue)"
    except (FetchStopped, TourApiError) as error:
        status = f"stopped on error: {error}"
    elapsed = time.monotonic() - started
    print(f"fetch {status}")
    print(f"calls this run: {client.calls}, files saved this run: {fetcher.saved}, "
          f"elapsed {elapsed:.1f}s, key name: {keys.kor_name}")
    if info:
        print(f"busan lDongRegnCd={info['busan']}, haeundae lDongSignguCd={info['haeundae']}, "
              f"listed={info['listed']}, detail targets={info['targets']}")
    return 0 if status == "complete" or status.startswith("stopped: --max-calls") else 1


def cmd_check(args) -> int:
    keys = load_service_keys()
    print(f"key names: 국문={keys.kor_name}, 무장애={keys.with_name}")
    store = RawStore(Path(args.raw))
    failed = False
    for label, base, key, op, params, name in [
        ("국문 관광정보", KOR_BASE, keys.kor, "ldongCode2",
         {"lDongListYn": "N", "numOfRows": 100, "pageNo": 1}, "kor_ldongCode2_regions.json"),
        ("무장애 여행 정보", WITH_BASE, keys.with_, "detailWithTour2",
         {"contentId": CHECK_WITH_CONTENT_ID}, f"with_detailWithTour2_{CHECK_WITH_CONTENT_ID}.json"),
    ]:
        client = TourApiClient(key, base, max_calls=1)
        try:
            resp = client.get(op, params)
        except TourApiError as error:
            print(f"{label} {op}: {error}")
            failed = True
            continue
        code, msg = resp.result()
        store.save(resp.body, "check", name)
        print(f"{label} {op}: HTTP {resp.status}, resultCode={code}, resultMsg={msg}")
        failed |= resp.status != 200 or code != OK
    return 1 if failed else 0


# ---------------------------------------------------------------- build

def load_raw(store: RawStore) -> mapping.RawSample:
    log = {}
    log_path = store.path("fetch_log.jsonl")
    if log_path.is_file():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            if entry.get("file"):
                log[entry["file"]] = entry["time"]
    listed: dict[str, dict] = {}
    for path in sorted(store.path("list").glob("areaBasedList2_p*.json"),
                       key=lambda p: int(p.stem.rsplit("_p", 1)[1])):
        for item in items_of(json.loads(path.read_text(encoding="utf-8"))):
            listed.setdefault(str(item["contentid"]), item)
    lcls: dict[str, str] = {}
    for path in sorted(store.path("lcls").glob("list_p*.json")):
        for item in items_of(json.loads(path.read_text(encoding="utf-8"))):
            for level in ("1", "2", "3"):
                code, name = item.get(f"lclsSystm{level}Cd"), item.get(f"lclsSystm{level}Nm")
                if code and name:
                    lcls[str(code)] = str(name)

    def detail(kind: str, content_id: str) -> dict | None:
        if not mapping.valid_source_place_id(content_id) or not store.has(kind, f"{content_id}.json"):
            return None
        found = items_of(store.read_json(kind, f"{content_id}.json"))
        return found[0] if found else {}

    commons = {cid: detail("common", cid) for cid in listed}
    intros = {cid: detail("intro", cid) for cid in listed}
    times = {cid: log.get(f"common/{cid}.json") for cid in listed}
    return mapping.RawSample(listed=listed, commons=commons, intros=intros, lcls_names=lcls,
                             fetched_at=times, retrieved_at=max(log.values()) if log else None)


def cmd_build(args) -> int:
    from app.data import db  # backend/ is on sys.path (see top of file)

    started = time.monotonic()
    raw = load_raw(RawStore(Path(args.raw)))
    result = mapping.build_rows(raw)
    path = db.create_database(Path(args.db))  # refuses to overwrite an existing file
    conn = db.connect(path)
    try:
        mapping.insert_rows(conn, result)
        conn.commit()
    finally:
        conn.close()
    report = result.report(elapsed_s=round(time.monotonic() - started, 2))
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(text + "\n", encoding="utf-8")
    print(f"built {path}: places={report['loaded']}")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipelines.haeundae_sample")
    parser.add_argument("--raw", default=str(RAW_DIR), help="원본 폴더 (기본 data/raw/tourapi)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="서비스마다 1건 호출해 HTTP 상태·resultCode만 출력")
    fetch = sub.add_parser("fetch", help="해운대구 원본 수집 (이어받기)")
    fetch.add_argument("--max-calls", type=int, default=200)
    build = sub.add_parser("build", help="원본에서 새 SQLite DB 만들기 (네트워크 없음)")
    build.add_argument("--db", required=True)
    build.add_argument("--report", default=None)
    args = parser.parse_args(argv)
    if getattr(args, "max_calls", 1) < 1:
        parser.error("--max-calls must be >= 1")
    return {"check": cmd_check, "fetch": cmd_fetch, "build": cmd_build}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
