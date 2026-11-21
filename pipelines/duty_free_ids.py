"""사후면세점 제외 목록 만들기 (DEC-023 ④, FR-007, FR-020). DEC-023 ④ 판별 기준: 분류 코드 SH040300 (찬용 결정, 11/19).

이미 내려받은 부산 시군구별 TourAPI 목록 원본(``areas.sigungu_raw_dir(<코드>)/list/areaBasedList2_p*.json``)만
읽는다. API를 새로 호출하지 않는다. 결과는 ``config/duty-free-exclusion.proposal.json``에 쓴다.

    .venv/Scripts/python.exe pipelines/duty_free_ids.py            # 저장소 루트에서
    .venv/Scripts/python.exe pipelines/duty_free_ids.py --check    # 파일과 원본이 같은지만 확인

판별 기준(DEC-023 ④): TourAPI 신분류 ``lclsSystm3 == "SH040300"``(분류명 "사후면세점", 상위 SH04 "면세점")인
쇼핑(38) 장소. DB ``places``에는 분류 코드 칸이 없어서, 런타임 후보 검색은 이 스크립트가 만든 장소 ID 목록으로
제외한다(``app.retrieval.settings``).

범위(PM 결정 11/21): 4개 권역 원 안(``config/retrieval.json`` ``areaCenters`` 중심, 반경 ``BUSANFIT_WALK_RADIUS_M``
기본 1500 m, ``pipelines/circles.py``)의 장소만. 원 판정은 목록 원본 좌표(mapy·mapx)로 한다(상세 수집
``circle_details``와 같은 기준).

예외(PM 결정 11/21): ``config/duty-free-exceptions.json``의 장소(백화점 본점 항목)는 목록에서 뺀다.
예외 장소가 원 안 SH040300 장소가 아니거나 이름이 원본과 다르면 오류로 멈춘다(오래된 예외를 조용히 두지 않음).
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # `python pipelines/duty_free_ids.py`로 실행해도 pipelines를 찾게
    sys.path.insert(0, str(ROOT))

from pipelines import areas, circles  # noqa: E402

OUTPUT = ROOT / "config" / "duty-free-exclusion.proposal.json"
EXCEPTIONS = ROOT / "config" / "duty-free-exceptions.json"

SOURCE_CODE = "tourapi-kor"      # data_sources.code of TourAPI 국문 관광정보 (DEC-017)
SHOPPING_CONTENT_TYPE = "38"     # TourAPI 콘텐츠 유형 쇼핑
DUTY_FREE_CODES = ("SH040300",)  # 신분류 "사후면세점"
STATUS = "DEC-023 ④ 판별 기준: 분류 코드 SH040300 (찬용 결정, 11/19)"


class ExceptionMismatch(ValueError):
    """An exception entry does not match a duty-free place inside the circles."""


def place_id(content_id: str) -> str:
    return f"{SOURCE_CODE}:{content_id}"


def load_exceptions(path: Path = EXCEPTIONS) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("exceptions")
    if not isinstance(entries, list) or not all(isinstance(e, dict) and isinstance(e.get("placeId"), str)
                                                and isinstance(e.get("name"), str) for e in entries):
        raise ValueError(f"{path}: exceptions must be a list of {{placeId, name, ...}}")
    return entries


def _point(item: dict) -> tuple[float, float] | None:
    try:
        lat, lon = float(item.get("mapy")), float(item.get("mapx"))
    except (TypeError, ValueError):
        return None
    return None if lat == 0 or lon == 0 else (lat, lon)


def build(listed: dict[str, dict], centers: circles.Centers, radius: float, exceptions: list[dict],
          generated_from: str = "부산 시군구 목록 원본") -> dict:
    """``listed``: {contentid: 목록 항목} over every stored 시군구 list."""
    shopping: dict[str, str] = {}   # contentid -> area, shopping places inside a circle
    duty_free: dict[str, str] = {}
    for cid, item in listed.items():
        if str(item.get("contenttypeid")) != SHOPPING_CONTENT_TYPE:
            continue
        point = _point(item)
        if point is None:
            continue
        area = circles.area_of(point[0], point[1], centers, radius, label=f"contentid {cid}")
        if area is None:
            continue
        shopping[cid] = area
        if item.get("lclsSystm3") in DUTY_FREE_CODES:
            duty_free[cid] = area
    excepted = []
    for entry in exceptions:
        cid = entry["placeId"].removeprefix(f"{SOURCE_CODE}:")
        if cid not in duty_free:
            raise ExceptionMismatch(f"exception {entry['placeId']} is not a SH040300 place inside the circles")
        if listed[cid].get("title") != entry["name"]:
            raise ExceptionMismatch(f"exception {entry['placeId']} name {entry['name']!r} != "
                                    f"source title {listed[cid].get('title')!r}")
        excepted.append(cid)
    hits = sorted(set(duty_free) - set(excepted), key=lambda value: (len(value), value))
    return {
        "status": STATUS,
        "criterion": {
            "source": "TourAPI areaBasedList2 lclsSystm3",
            "codes": list(DUTY_FREE_CODES),
            "codeNames": {"SH040300": "사후면세점"},
            "contentTypeId": SHOPPING_CONTENT_TYPE,
        },
        "scope": {
            "rule": "권역 원 안 장소만 (PM 11/21). 중심: config/retrieval.json areaCenters, 목록 원본 좌표로 판정",
            "areas": sorted(centers),
            "radiusM": radius,
        },
        "generatedFrom": f"{generated_from} (pipelines/duty_free_ids.py)",
        "exceptionsFrom": "config/duty-free-exceptions.json",
        "shoppingInCircles": len(shopping),
        "dutyFreeInCircles": len(duty_free),
        "exceptedPlaceIds": [place_id(cid) for cid in sorted(excepted, key=lambda v: (len(v), v))],
        "count": len(hits),
        "countByArea": dict(sorted(Counter(duty_free[cid] for cid in hits).items())),
        "placeIds": [place_id(cid) for cid in hits],
    }


def load_listed() -> dict[str, dict]:
    from pipelines.circle_details import load_listed as listed_with_codes  # lazy: keeps import light
    return {cid: item for cid, (item, _code) in listed_with_codes().items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument("--exceptions", type=Path, default=EXCEPTIONS)
    parser.add_argument("--check", action="store_true", help="do not write; fail if the file differs")
    args = parser.parse_args(argv)
    centers = circles.load_centers(required=areas.AREA_CODES)
    result = build(load_listed(), centers, circles.radius_m(), load_exceptions(args.exceptions),
                   "data/raw/tourapi 부산 시군구 목록 원본 전체")
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        same = args.out.exists() and args.out.read_text(encoding="utf-8") == text
        print("up to date" if same else "differs", file=sys.stderr)
        return 0 if same else 1
    args.out.write_text(text, encoding="utf-8")
    print(f"shopping in circles {result['shoppingInCircles']}, duty-free {result['dutyFreeInCircles']}, "
          f"excepted {len(result['exceptedPlaceIds'])}, listed {result['count']} {result['countByArea']} "
          f"-> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
