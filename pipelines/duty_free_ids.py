"""사후면세점 제외 목록 만들기 (DEC-023 ④, FR-007). DEC-023 ④ 판별 기준: 분류 코드 SH040300 (찬용 결정, 11/19).

이미 내려받은 TourAPI 목록 원본(``data/raw/tourapi/list/areaBasedList2_p1.json``)만 읽는다.
API를 새로 호출하지 않는다. 결과는 ``config/duty-free-exclusion.proposal.json``에 쓴다.

판별 기준(DEC-023 ④ 판별 기준: 분류 코드 SH040300 (찬용 결정, 11/19)): TourAPI 신분류 ``lclsSystm3 == "SH040300"``(분류명
"사후면세점", 상위 SH04 "면세점"). DB ``places``에는 분류 코드 칸이 없어서, 런타임 후보 검색은
이 스크립트가 만든 장소 ID 목록으로 제외한다(``app.retrieval.settings``).

    .venv/Scripts/python.exe pipelines/duty_free_ids.py            # 저장소 루트에서
    .venv/Scripts/python.exe pipelines/duty_free_ids.py --check    # 파일과 원본이 같은지만 확인
    .venv/Scripts/python.exe pipelines/duty_free_ids.py --area SEOMYEON   # 다른 권역 (기본 HAEUNDAE)

권역별 원본 폴더는 pipelines/areas.py 권역 표를 따른다. 결과 기본 경로: 해운대는 위 config 파일,
다른 권역은 data/processed/duty-free-exclusion.<권역>.json (런타임 설정 config/retrieval.json은 바꾸지 않음).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # `python pipelines/duty_free_ids.py`로 실행해도 pipelines.areas를 찾게
    sys.path.insert(0, str(ROOT))

from pipelines import areas  # noqa: E402

LIST_PAGE1 = Path("list") / "areaBasedList2_p1.json"
RAW_LIST = areas.get(areas.DEFAULT_AREA).raw_dir / LIST_PAGE1
OUTPUT = ROOT / "config/duty-free-exclusion.proposal.json"


def raw_list_of(area: str) -> Path:
    return areas.get(area).raw_dir / LIST_PAGE1


def output_of(area: str) -> Path:
    if area == areas.DEFAULT_AREA:
        return OUTPUT
    return ROOT / "data" / "processed" / f"duty-free-exclusion.{area}.json"


def relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()

SOURCE_CODE = "tourapi-kor"      # data_sources.code of TourAPI 국문 관광정보 (DEC-017)
SHOPPING_CONTENT_TYPE = "38"     # TourAPI 콘텐츠 유형 쇼핑
DUTY_FREE_CODES = ("SH040300",)  # 신분류 "사후면세점"


def build(raw: dict, generated_from: str = "data/raw/tourapi/list/areaBasedList2_p1.json") -> dict:
    items = raw["response"]["body"]["items"]["item"]
    shopping = [item for item in items if item.get("contenttypeid") == SHOPPING_CONTENT_TYPE]
    hits = sorted({item["contentid"] for item in shopping if item.get("lclsSystm3") in DUTY_FREE_CODES},
                  key=lambda value: (len(value), value))
    return {
        "status": "DEC-023 ④ 판별 기준: 분류 코드 SH040300 (찬용 결정, 11/19)",
        "criterion": {
            "source": "TourAPI areaBasedList2 lclsSystm3",
            "codes": list(DUTY_FREE_CODES),
            "codeNames": {"SH040300": "사후면세점"},
            "contentTypeId": SHOPPING_CONTENT_TYPE,
        },
        "generatedFrom": f"{generated_from} (pipelines/duty_free_ids.py)",
        "shoppingTotal": len(shopping),
        "count": len(hits),
        "placeIds": [f"{SOURCE_CODE}:{content_id}" for content_id in hits],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--area", default=areas.DEFAULT_AREA, choices=areas.AREA_CODES)
    parser.add_argument("--raw", type=Path, default=None, help="기본: 권역 원본 폴더의 list/areaBasedList2_p1.json")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--check", action="store_true", help="do not write; fail if the file differs")
    args = parser.parse_args(argv)
    raw_path = args.raw or raw_list_of(args.area)
    args.out = args.out or output_of(args.area)
    if raw_path.with_name("areaBasedList2_p2.json").exists():
        print(f"{raw_path.parent} has more than one list page; only p1 is supported", file=sys.stderr)
        return 1
    result = build(json.loads(raw_path.read_text(encoding="utf-8")), relative(raw_path))
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        same = args.out.exists() and args.out.read_text(encoding="utf-8") == text
        print("up to date" if same else "differs", file=sys.stderr)
        return 0 if same else 1
    args.out.write_text(text, encoding="utf-8")
    print(f"shopping {result['shoppingTotal']}, duty-free {result['count']} -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
