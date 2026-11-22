"""권역별 표본 수집(fetch)과 적재(build) — 이슈 #7 작업 C, 이슈 #36, FR-020.

    python -m pipelines.haeundae_sample check                 # 서비스마다 1건 호출, HTTP 상태·resultCode만 출력
    python -m pipelines.haeundae_sample fetch --max-calls 200 # 원본을 data/raw/tourapi/ 에 저장 (이어받기)
    python -m pipelines.haeundae_sample --area SEOMYEON fetch --list-only   # areaBasedList2만
    python -m pipelines.haeundae_sample fetch-sigungu-list --all            # 부산 시군구별 목록만 (11/21 PM 결정)
    python -m pipelines.haeundae_sample build --db data/busanfit.sqlite3 [--report data/processed/report.json]

--area 기본값은 HAEUNDAE (권역 표: pipelines/areas.py). --raw를 주지 않으면 권역의 원본 폴더를 쓴다
(해운대 data/raw/tourapi/, 다른 권역 data/raw/tourapi/<권역>/).
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

from pipelines import areas, mapping  # noqa: E402
from pipelines.env import load_service_keys  # noqa: E402
from pipelines.tourapi_client import (KOR_BASE, WITH_BASE, CallBudgetExceeded,  # noqa: E402
                                      TourApiClient, TourApiError)

RAW_DIR = areas.RAW_ROOT  # 해운대 원본 폴더 (= areas.get("HAEUNDAE").raw_dir)
KST = timezone(timedelta(hours=9))
OK = "0000"
BUSAN_NAME = areas.BUSAN_NAME
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


def fetch_list(fetcher: Fetcher, busan: str, sigungu_cd: str) -> list[dict]:
    """areaBasedList2 every page for one 시군구 (resumable; stored pages are not requested again)."""
    page, listed = 1, []
    while True:
        params = {"lDongRegnCd": busan, "lDongSignguCd": sigungu_cd, "arrange": "A",
                  "numOfRows": LIST_ROWS, "pageNo": page}
        data = fetcher.get("areaBasedList2", params, "list", f"areaBasedList2_p{page}.json")
        listed.extend(items_of(data))
        if page * LIST_ROWS >= int(data["response"]["body"].get("totalCount") or 0):
            break
        page += 1
    return listed


def busan_sigungu(ldong_path: Path = areas.LDONG_BUSAN) -> dict[str, str]:
    """{시군구 코드: 이름} from the stored ldongCode2 부산 file (no network)."""
    data = json.loads(ldong_path.read_text(encoding="utf-8"))
    return {str(it["code"]): str(it["name"]) for it in items_of(data)}


def run_fetch(fetcher: Fetcher, area: str = areas.DEFAULT_AREA, *, list_only: bool = False) -> dict:
    """Fetch one area's raw files into ``fetcher.store`` (resumable).

    list_only: call areaBasedList2 only, with the codes from the area table (no ldongCode2,
    lclsSystmCode2, detailCommon2, detailIntro2). Otherwise the codes are looked up by name and
    must equal the area table, or the fetch stops.
    """
    spec = areas.get(area)
    if list_only:
        busan, sigungu_cd = spec.ldong_regn_cd, spec.ldong_signgu_cd
    else:
        regions = fetcher.get("ldongCode2", {"lDongListYn": "N", "numOfRows": 100, "pageNo": 1},
                              "ldong", "regions.json")
        busan = find_code(items_of(regions), BUSAN_NAME)
        sigungu = fetcher.get("ldongCode2", {"lDongRegnCd": busan, "lDongListYn": "N",
                                             "numOfRows": 100, "pageNo": 1},
                              "ldong", f"{busan}.json")
        sigungu_cd = find_code(items_of(sigungu), spec.sigungu_name)
        if (busan, sigungu_cd) != (spec.ldong_regn_cd, spec.ldong_signgu_cd):
            raise FetchStopped(f"{area} 법정동 코드가 권역 표와 다름: 응답 {busan}/{sigungu_cd}, "
                               f"표 {spec.ldong_regn_cd}/{spec.ldong_signgu_cd}")

        page = 1
        while True:
            params = {"lclsSystmListYn": "Y", "numOfRows": LIST_ROWS, "pageNo": page}
            data = fetcher.get("lclsSystmCode2", params, "lcls", f"list_p{page}.json")
            if page * LIST_ROWS >= int(data["response"]["body"].get("totalCount") or 0):
                break
            page += 1

    listed = fetch_list(fetcher, busan, sigungu_cd)
    targets = sorted({(str(it["contentid"]), str(it["contenttypeid"])) for it in listed
                      if str(it.get("contenttypeid")) in mapping.TARGET_CONTENT_TYPES},
                     key=lambda pair: (len(pair[0]), pair[0]))
    info = {"area": area, "busan": busan, "sigungu": sigungu_cd, "listed": len(listed),
            "targets": len(targets)}
    if list_only:
        return info
    for content_id, type_id in targets:
        if not mapping.valid_source_place_id(content_id):
            continue  # build reports it; never request with an ID we would refuse to store
        fetcher.get("detailCommon2", {"contentId": content_id}, "common", f"{content_id}.json")
        fetcher.get("detailIntro2", {"contentId": content_id, "contentTypeId": type_id},
                    "intro", f"{content_id}.json")
    return info


def cmd_fetch(args) -> int:
    keys = load_service_keys()
    client = TourApiClient(keys.kor, KOR_BASE, max_calls=args.max_calls)
    fetcher = Fetcher(client, RawStore(Path(args.raw)))
    started = time.monotonic()
    status = "complete"
    info: dict = {}
    try:
        info = run_fetch(fetcher, args.area, list_only=args.list_only)
    except CallBudgetExceeded:
        status = f"stopped: --max-calls {args.max_calls} reached (run again to continue)"
    except (FetchStopped, TourApiError) as error:
        status = f"stopped on error: {error}"
    elapsed = time.monotonic() - started
    print(f"fetch {status}")
    print(f"calls this run: {client.calls}, files saved this run: {fetcher.saved}, "
          f"elapsed {elapsed:.1f}s, key name: {keys.kor_name}")
    if info:
        print(f"area={info['area']}, busan lDongRegnCd={info['busan']}, "
              f"lDongSignguCd={info['sigungu']}, listed={info['listed']}, detail targets={info['targets']}"
              + (" (list only: details not fetched)" if args.list_only else ""))
    return 0 if status == "complete" or status.startswith("stopped: --max-calls") else 1


def run_sigungu_lists(client: TourApiClient, codes: list[str], known: dict[str, str],
                      out=print) -> list[dict]:
    """areaBasedList2 only, for each 시군구 code in order. Stops at the first error (raises)."""
    unknown = [c for c in codes if c not in known]
    if unknown:
        raise FetchStopped(f"부산 시군구 목록(ldong/{areas.BUSAN_LDONG_REGN_CD}.json)에 없는 코드: {unknown}")
    done = []
    for code in codes:
        fetcher = Fetcher(client, RawStore(areas.sigungu_raw_dir(code)), out=out)
        before = client.calls
        listed = fetch_list(fetcher, areas.BUSAN_LDONG_REGN_CD, code)
        done.append({"sigungu": code, "name": known[code], "listed": len(listed),
                     "calls": client.calls - before, "raw": str(fetcher.store.root)})
        out(f"{code} {known[code]}: listed={len(listed)}, calls={client.calls - before}, "
            f"raw={fetcher.store.root}")
    return done


def cmd_fetch_sigungu_list(args) -> int:
    known = busan_sigungu()
    codes = list(known) if args.all else args.sigungu
    if not codes:
        print("give --sigungu CODE ... or --all")
        return 2
    keys = load_service_keys()
    client = TourApiClient(keys.kor, KOR_BASE, max_calls=args.max_calls)
    status = "complete"
    try:
        run_sigungu_lists(client, codes, known)
    except CallBudgetExceeded:
        status = f"stopped: --max-calls {args.max_calls} reached (run again to continue)"
    except (FetchStopped, TourApiError) as error:
        status = f"stopped on error: {error}"
    print(f"fetch-sigungu-list {status}; calls this run: {client.calls}, key name: {keys.kor_name}")
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
    result = mapping.build_rows(raw, area=args.area)
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
    # 수상한 운영시간 입력은 건수만 남긴다 (open_hours NULL, 원문 보존)
    print(f"open_hours suspicious (NULL, original kept): {report['open_hours_suspicious']['count']}")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipelines.haeundae_sample")
    add_area_args(parser)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="서비스마다 1건 호출해 HTTP 상태·resultCode만 출력")
    fetch = sub.add_parser("fetch", help="권역 원본 수집 (이어받기)")
    fetch.add_argument("--max-calls", type=int, default=200)
    fetch.add_argument("--list-only", action="store_true",
                       help="areaBasedList2만 호출 (상세 detailCommon2·detailIntro2 호출 안 함)")
    sig = sub.add_parser("fetch-sigungu-list",
                         help="부산 시군구별 areaBasedList2만 수집 (권역 원에 걸치는 옆 구, 이어받기)")
    sig.add_argument("--sigungu", nargs="*", default=[], help="시군구 코드 (ldong/26.json)")
    sig.add_argument("--all", action="store_true", help="ldong/26.json의 부산 시군구 전부")
    sig.add_argument("--max-calls", type=int, default=30)
    build = sub.add_parser("build", help="원본에서 새 SQLite DB 만들기 (네트워크 없음)")
    build.add_argument("--db", required=True)
    build.add_argument("--report", default=None)
    args = parse_area_args(parser, argv)
    if getattr(args, "max_calls", 1) < 1:
        parser.error("--max-calls must be >= 1")
    return {"check": cmd_check, "fetch": cmd_fetch, "fetch-sigungu-list": cmd_fetch_sigungu_list,
            "build": cmd_build}[args.cmd](args)


def add_area_args(parser: argparse.ArgumentParser) -> None:
    """--area (기본 HAEUNDAE)와 --raw (기본: 그 권역의 원본 폴더)."""
    parser.add_argument("--area", default=areas.DEFAULT_AREA, choices=areas.AREA_CODES,
                        help="권역 코드 (pipelines/areas.py, 기본 HAEUNDAE)")
    parser.add_argument("--raw", default=None,
                        help="원본 폴더 (기본: 해운대 data/raw/tourapi, 다른 권역 data/raw/tourapi/<권역>)")


def parse_area_args(parser: argparse.ArgumentParser, argv: list[str] | None) -> argparse.Namespace:
    args = parser.parse_args(argv)
    if args.raw is None:
        args.raw = str(areas.get(args.area).raw_dir)
    return args


if __name__ == "__main__":
    raise SystemExit(main())
