"""확실한 실외 장소 ID 목록 만들기 (FR-016, #33 A단계, DEC-034 4). 사후면세점 목록(duty_free_ids.py)과 같은 방식.

이미 내려받은 부산 시군구별 TourAPI 목록 원본(``areas.sigungu_raw_dir(<코드>)/list/areaBasedList2_p*.json``)만
읽는다. API를 새로 호출하지 않는다. 결과는 ``config/outdoor-places.json``에 쓴다.

    .venv/Scripts/python.exe pipelines/outdoor_ids.py            # 저장소 루트에서
    .venv/Scripts/python.exe pipelines/outdoor_ids.py --check    # 파일과 원본이 같은지만 확인

기준: ``config/weather.json`` ``outdoorBy.codePrefixes``. TourAPI 신분류 ``lclsSystm3``가 접두어 중 하나로 시작하는
대상 유형(mapping.TARGET_CONTENT_TYPES) 장소. ``places.indoor``는 바꾸지 않는다(모두 NULL 그대로).
``outdoorBy.excludePlaceIds``(DEC-034 먹자골목 3곳)는 규칙에 맞아도 목록에서 빼고 ``excludedPlaces``로 이유와 함께
보고한다. 규칙에 맞는 장소가 아니면(오래된 예외) 오류. ``outdoorBy.needsDecision`` 코드의 장소는 목록에 넣지 않고
``needsDecisionPlaces``로만 보고한다.

범위: 4개 권역 원 안(``config/retrieval.json`` ``areaCenters``, 반경 ``BUSANFIT_WALK_RADIUS_M`` 기본 1500 m).
원 판정은 목록 원본 좌표(mapy·mapx), duty_free_ids와 같은 기준.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # `python pipelines/outdoor_ids.py`로 실행해도 pipelines를 찾게
    sys.path.insert(0, str(ROOT))

from pipelines import areas, circles, mapping  # noqa: E402

WEATHER_CONFIG = ROOT / "config" / "weather.json"
SOURCE_CODE = "tourapi-kor"
STATUS = "APPROVED (DEC-034, PM 김세민 2026-11-24. 분류 코드로 확실한 실외만, 먹자골목 3곳 제외)"


def place_id(content_id: str) -> str:
    return f"{SOURCE_CODE}:{content_id}"


def load_rules(path: Path = WEATHER_CONFIG) -> tuple[dict[str, str], dict[str, str], dict[str, str], Path]:
    """(codePrefixes, needsDecision, excludePlaceIds, 출력 파일 경로)."""
    outdoor_by = json.loads(path.read_text(encoding="utf-8"))["outdoorBy"]
    prefixes, undecided = outdoor_by["codePrefixes"], outdoor_by["needsDecision"]
    excluded = outdoor_by.get("excludePlaceIds", {})
    if not isinstance(excluded, dict) or not all(isinstance(k, str) and isinstance(v, str) and v
                                                 for k, v in excluded.items()):
        raise ValueError(f"{path}: outdoorBy.excludePlaceIds must map placeId to a reason")
    if not prefixes or not all(isinstance(k, str) and k for k in prefixes):
        raise ValueError(f"{path}: outdoorBy.codePrefixes must be a non-empty object")
    overlap = [code for code in undecided if any(code.startswith(p) for p in prefixes)]
    if overlap:
        raise ValueError(f"{path}: needsDecision codes also match codePrefixes: {overlap}")
    return dict(prefixes), dict(undecided), dict(excluded), path.parent / outdoor_by["placeIdFile"]


def _point(item: dict) -> tuple[float, float] | None:
    try:
        lat, lon = float(item.get("mapy")), float(item.get("mapx"))
    except (TypeError, ValueError):
        return None
    return None if lat == 0 or lon == 0 else (lat, lon)


def _order(cid: str) -> tuple[int, str]:
    return len(cid), cid


def build(listed: dict[str, dict], centers: circles.Centers, radius: float, prefixes: dict[str, str],
          undecided: dict[str, str], generated_from: str = "부산 시군구 목록 원본",
          excluded: dict[str, str] | None = None) -> dict:
    """``listed``: {contentid: 목록 항목} over every stored 시군구 list. ``excluded``: {placeId: 이유}."""
    excluded = excluded or {}
    targets = 0
    outdoor: list[tuple[str, str, str, str]] = []      # (cid, area, code, title)
    dropped: list[tuple[str, str, str, str]] = []
    pending: list[tuple[str, str, str, str]] = []
    for cid, item in listed.items():
        if str(item.get("contenttypeid")) not in mapping.TARGET_CONTENT_TYPES:
            continue
        point = _point(item)
        if point is None:
            continue
        area = circles.area_of(point[0], point[1], centers, radius, label=f"contentid {cid}")
        if area is None:
            continue
        targets += 1
        code = str(item.get("lclsSystm3") or "")
        row = (cid, area, code, str(item.get("title") or ""))
        if any(code.startswith(prefix) for prefix in prefixes):
            (dropped if place_id(cid) in excluded else outdoor).append(row)
        elif code in undecided:
            pending.append(row)
    stale = sorted(set(excluded) - {place_id(r[0]) for r in dropped})
    if stale:
        raise ValueError(f"excludePlaceIds not matching any outdoor place in circles: {stale}")
    outdoor.sort(key=lambda r: (r[1], _order(r[0])))
    dropped.sort(key=lambda r: (r[1], _order(r[0])))
    pending.sort(key=lambda r: (r[2], r[1], _order(r[0])))
    return {
        "status": STATUS,
        "criterion": {
            "source": "TourAPI areaBasedList2 lclsSystm3",
            "rulesFrom": "config/weather.json outdoorBy",
            "codePrefixes": prefixes,
            "contentTypeIds": sorted(mapping.TARGET_CONTENT_TYPES),
        },
        "scope": {
            "rule": "권역 원 안 장소만 (PM 11/21). 중심: config/retrieval.json areaCenters, 목록 원본 좌표로 판정",
            "areas": sorted(centers),
            "radiusM": radius,
        },
        "generatedFrom": f"{generated_from} (pipelines/outdoor_ids.py)",
        "targetsInCircles": targets,
        "count": len(outdoor),
        "countByArea": dict(sorted(Counter(r[1] for r in outdoor).items())),
        "countByCode": dict(sorted(Counter(r[2] for r in outdoor).items())),
        "places": [{"placeId": place_id(c), "area": a, "code": k, "name": t} for c, a, k, t in outdoor],
        "excludedCount": len(dropped),
        "excludedPlaces": [{"placeId": place_id(c), "area": a, "code": k, "name": t, "note": excluded[place_id(c)]}
                           for c, a, k, t in dropped],
        "needsDecisionCount": len(pending),
        "needsDecisionPlaces": [{"placeId": place_id(c), "area": a, "code": k, "name": t, "note": undecided[k]}
                                for c, a, k, t in pending],
    }


def load_listed() -> dict[str, dict]:
    from pipelines.circle_details import load_listed as listed_with_codes  # lazy: keeps import light
    return {cid: item for cid, (item, _code) in listed_with_codes().items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rules", type=Path, default=WEATHER_CONFIG)
    parser.add_argument("--check", action="store_true", help="do not write; fail if the file differs")
    args = parser.parse_args(argv)
    prefixes, undecided, excluded, out = load_rules(args.rules)
    centers = circles.load_centers(required=areas.AREA_CODES)
    result = build(load_listed(), centers, circles.radius_m(), prefixes, undecided,
                   "data/raw/tourapi 부산 시군구 목록 원본 전체", excluded)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        same = out.exists() and out.read_text(encoding="utf-8") == text
        print("up to date" if same else "differs", file=sys.stderr)
        return 0 if same else 1
    out.write_text(text, encoding="utf-8")
    print(f"targets in circles {result['targetsInCircles']}, outdoor {result['count']} {result['countByArea']}, "
          f"excluded {result['excludedCount']}, needs decision {result['needsDecisionCount']} -> {out}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
