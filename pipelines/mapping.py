"""TourAPI 원본 → places 행 변환 (네트워크 없음, 같은 원본이면 같은 결과).

규칙 (문서 근거는 pipelines/README.md):
- 장소 ID: ``{data_sources.code}:{contentid}``. contentid가 허용 문자 규칙(app.data.place_id)에 어긋나면
  값을 바꾸지 않고 건너뛰고 건수로 보고한다.
- 카테고리: DEC-013의 7개 값. 매핑표는 ``category_of`` (이슈 #7 "정할 것 2" 제안).
- 가격: DEC-014. 스프린트 2는 원문(price_text)만, 금액·기준은 NULL. 원문이 없으면 NULL(무료 아님).
- 운영시간: 확실히 읽을 수 있는 경우만 구조화(``parse_open_hours``). 아니면 open_hours NULL, 원문만 보존.
- 누락을 채우지 않는다: 운영시간 누락 ≠ 상시 영업, 가격 누락 ≠ 무료, 실내 여부·접근성은 NULL 그대로.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
import math
import re
import sqlite3

from app.data.place_id import validate_source_place_id
from app.domain.place import validate_open_hours

# contentTypeId (포털 Swagger: 12 관광지, 14 문화시설, 15 축제공연행사, 25 여행코스, 28 레포츠, 32 숙박, 38 쇼핑, 39 음식점)
TARGET_CONTENT_TYPES = {"12", "14", "28", "38", "39"}
CONTENT_TYPE_NAMES = {"12": "관광지", "14": "문화시설", "15": "축제공연행사", "25": "여행코스",
                      "28": "레포츠", "32": "숙박", "38": "쇼핑", "39": "음식점"}

SOURCE = {
    "code": "tourapi-kor",
    "provider": "한국관광공사",
    "dataset_name": "국문 관광정보 서비스_GW (KorService2)",
    "license": None,      # 이용허락범위: 담당자가 포털에서 확인 후 기록 (README "확인 필요")
    "url": "https://www.data.go.kr/data/15101578/openapi.do",
    "base_date": None,    # 제공기관 기준일: 문서에 없음
}
AREA = "HAEUNDAE"

# 소개정보(detailIntro2) 필드: 유형별 이용시간·쉬는날·이용요금 (포털 Swagger 응답 필드 설명)
HOURS_FIELDS = {"12": ("usetime", "restdate"), "14": ("usetimeculture", "restdateculture"),
                "28": ("usetimeleports", "restdateleports"), "38": ("opentime", "restdateshopping"),
                "39": ("opentimefood", "restdatefood")}
FEE_FIELDS = {"14": "usefee", "28": "usefeeleports"}
SPEND_TIME_FIELDS = {"14": "spendtime"}

# DEC-018 기본 체류시간 (분)
STAY_MIN = {"CAFE": 60, "FOOD": 70, "EXHIBITION": 60}
STAY_MIN_OTHER = 60

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
KOREAN_DAYS = dict(zip("월화수목금토일", DAYS))


def valid_source_place_id(value: object) -> bool:
    try:
        validate_source_place_id(value)  # type: ignore[arg-type]
    except ValueError:
        return False
    return True


def text(value: object) -> str | None:
    """Stripped string, or None when absent/blank. Never turns missing into a value."""
    if value is None:
        return None
    s = str(value).strip()
    return s or None


# ---------------------------------------------------------------- category (DEC-013)

CATEGORY_RULES = [  # (설명, 판정) — 위에서부터 처음 맞는 규칙
    ("분류체계 FD050100(카페/찻집 > 카페)", lambda t, l: l.startswith("FD050100") and "CAFE"),
    ("음식점(39) 또는 분류체계 FD(음식)", lambda t, l: (t == "39" or l.startswith("FD")) and "FOOD"),
    ("쇼핑(38) 또는 분류체계 SH(쇼핑)", lambda t, l: (t == "38" or l.startswith("SH")) and "SHOPPING"),
    ("문화시설(14)", lambda t, l: t == "14" and "EXHIBITION"),
    ("관광지(12) 중 분류체계 NA(자연관광) 또는 VE03(도시공원)",
     lambda t, l: t == "12" and (l.startswith("NA") or l.startswith("VE03")) and "PARK"),
    ("관광지(12)·레포츠(28) 나머지", lambda t, l: t in ("12", "28") and "ATTRACTION"),
]


def category_of(content_type: str, lcls3: str | None) -> tuple[str, str]:
    """(category, rule) — OTHER when no rule matches (counted as unmapped)."""
    code = lcls3 or ""
    for rule, judge in CATEGORY_RULES:
        found = judge(content_type, code)
        if found:
            return found, rule
    return "OTHER", "규칙 없음 → OTHER"


# ---------------------------------------------------------------- opening hours

_RANGE = re.compile(r"^(\d{1,2}):(\d{2})\s*[~\-]\s*(\d{1,2}):(\d{2})$")
_ALWAYS_OPEN = {"상시 개방", "상시개방", "24시간"}
_NO_WEEKLY_CLOSE = {"연중무휴"}
_HOLIDAYS_ONLY = {"명절", "설·추석 당일", "설날·추석 당일", "설날, 추석 당일", "설, 추석 당일"}
_WEEKLY_ONE_DAY = re.compile(r"^매주\s*([월화수목금토일])요일$")


def _hhmm(h: str, m: str) -> str | None:
    hour, minute = int(h), int(m)
    if minute > 59 or hour > 24 or (hour == 24 and minute != 0):
        return None
    return f"{hour:02d}:{minute:02d}"


def parse_open_hours(usetime: str | None, restdate: str | None) -> dict | None:
    """Structure only what is certain; otherwise None (the original text is kept separately).

    Accepted 이용시간: one range "HH:mm~HH:mm" (or "-"), or "상시 개방"/"24시간" (00:00–24:00).
    Accepted 쉬는날 (needed: without it closed days are unknown, so nothing is filled):
    "연중무휴", holiday-only text (holidays are out of scope, DEC-017 structure), or "매주 X요일".
    """
    use, rest = text(usetime), text(restdate)
    if use is None or rest is None:
        return None
    if use in _ALWAYS_OPEN:
        interval = {"open": "00:00", "close": "24:00"}
    else:
        match = _RANGE.match(use)
        if not match:
            return None
        open_, close = _hhmm(*match.group(1, 2)), _hhmm(*match.group(3, 4))
        if open_ is None or close is None or open_ == "24:00" or open_ == close:
            return None
        interval = {"open": open_, "close": close}
    if rest in _NO_WEEKLY_CLOSE or rest in _HOLIDAYS_ONLY:
        closed: set[str] = set()
    else:
        weekly = _WEEKLY_ONE_DAY.match(rest)
        if not weekly:
            return None
        closed = {KOREAN_DAYS[weekly.group(1)]}
    parsed = {day: ([] if day in closed else [dict(interval)]) for day in DAYS}
    validate_open_hours(parsed)
    return parsed


def hours_text(usetime: str | None, restdate: str | None) -> str | None:
    parts = []
    if text(usetime):
        parts.append(f"이용시간: {text(usetime)}")
    if text(restdate):
        parts.append(f"쉬는날: {text(restdate)}")
    return "\n".join(parts) or None


_SPEND = [(re.compile(r"^(\d+)\s*시간\s*(\d+)\s*분$"), lambda m: int(m[1]) * 60 + int(m[2])),
          (re.compile(r"^(\d+)\s*시간$"), lambda m: int(m[1]) * 60),
          (re.compile(r"^(\d+)\s*분$"), lambda m: int(m[1]))]


def stay_minutes(category: str, spendtime: str | None) -> tuple[int, bool]:
    """(minutes, from_source). DEC-018: TourAPI 관람소요시간이 있고 확실히 읽히면 우선."""
    raw = text(spendtime)
    if raw:
        for pattern, convert in _SPEND:
            match = pattern.match(raw)
            if match and convert(match) > 0:
                return convert(match), True
    return STAY_MIN.get(category, STAY_MIN_OTHER), False


# ---------------------------------------------------------------- rows

@dataclass
class RawSample:
    listed: dict[str, dict]
    commons: dict[str, dict | None]
    intros: dict[str, dict | None]
    lcls_names: dict[str, str]
    fetched_at: dict[str, str | None]
    retrieved_at: str | None


@dataclass
class BuildResult:
    rows: list[dict] = field(default_factory=list)
    skipped: Counter = field(default_factory=Counter)
    skipped_ids: dict[str, list[str]] = field(default_factory=dict)
    listed_by_type: Counter = field(default_factory=Counter)
    category_rules: Counter = field(default_factory=Counter)
    lcls_by_category: dict[str, Counter] = field(default_factory=dict)
    no_intro: int = 0
    stay_from_source: int = 0
    retrieved_at: str | None = None

    def skip(self, reason: str, content_id: str) -> None:
        self.skipped[reason] += 1
        self.skipped_ids.setdefault(reason, []).append(content_id)

    def report(self, elapsed_s: float | None = None) -> dict:
        n = len(self.rows)

        def rate(count: int, total: int = n) -> dict:
            return {"count": count, "total": total, "rate": round(count / total, 4) if total else None}

        with_text = [r for r in self.rows if r["open_hours_text"] is not None]
        listed_total = sum(self.listed_by_type.values())
        return {
            "listed_total": listed_total,
            "listed_by_content_type": {f"{k} {CONTENT_TYPE_NAMES.get(k, '?')}": v
                                       for k, v in sorted(self.listed_by_type.items())},
            "target_content_types": sorted(TARGET_CONTENT_TYPES),
            "loaded": n,
            "skipped": dict(sorted(self.skipped.items())),
            "skipped_ids": {k: sorted(v) for k, v in sorted(self.skipped_ids.items())},
            "missing": {
                "address": rate(sum(r["address"] is None for r in self.rows)),
                "coordinates_skipped": self.skipped.get("좌표 없음·범위 밖", 0),
                "open_hours_text": rate(sum(r["open_hours_text"] is None for r in self.rows)),
                "price_text": rate(sum(r["price_text"] is None for r in self.rows)),
                "overview": rate(sum(r["overview"] is None for r in self.rows)),
                "intro_item_missing": self.no_intro,
            },
            "open_hours_parsed": rate(sum(r["open_hours"] is not None for r in with_text), len(with_text)),
            "category": dict(sorted(Counter(r["category"] for r in self.rows).items())),
            "category_mapped_not_other": rate(sum(r["category"] != "OTHER" for r in self.rows)),
            "category_rules": dict(sorted(self.category_rules.items())),
            "lcls_by_category": {c: dict(sorted(v.items())) for c, v in sorted(self.lcls_by_category.items())},
            "default_stay_from_source": self.stay_from_source,
            "retrieved_at": self.retrieved_at,
            "elapsed_s": elapsed_s,
        }


def _coordinate(value: object, low: float, high: float) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and low <= number <= high and number != 0 else None


def build_rows(raw: RawSample) -> BuildResult:
    result = BuildResult(retrieved_at=raw.retrieved_at)
    for content_id in sorted(raw.listed, key=lambda cid: (len(cid), cid)):
        item = raw.listed[content_id]
        type_id = str(item.get("contenttypeid") or "")
        result.listed_by_type[type_id] += 1
        if type_id not in TARGET_CONTENT_TYPES:
            result.skip(f"대상 아닌 유형 {type_id} {CONTENT_TYPE_NAMES.get(type_id, '?')}", content_id)
            continue
        if not valid_source_place_id(content_id):
            result.skip("contentid 허용 문자 규칙 위반", content_id)
            continue
        common = raw.commons.get(content_id)
        if common is None:
            result.skip("공통정보 미수집", content_id)
            continue
        base = {**item, **{k: v for k, v in common.items() if text(v) is not None}}
        lat = _coordinate(base.get("mapy"), -90, 90)    # mapy = WGS84 위도 (위치기반조회 mapY 설명)
        lon = _coordinate(base.get("mapx"), -180, 180)  # mapx = WGS84 경도
        if lat is None or lon is None:
            result.skip("좌표 없음·범위 밖", content_id)
            continue
        intro = raw.intros.get(content_id)
        if not intro:
            result.no_intro += 1
            intro = {}
        use_field, rest_field = HOURS_FIELDS[type_id]
        usetime, restdate = intro.get(use_field), intro.get(rest_field)
        lcls3 = text(base.get("lclsSystm3"))
        category, rule = category_of(type_id, lcls3)
        result.category_rules[rule] += 1
        label = f"{lcls3} {raw.lcls_names.get(lcls3 or '', '?')}"
        result.lcls_by_category.setdefault(category, Counter())[label] += 1
        stay, from_source = stay_minutes(category, intro.get(SPEND_TIME_FIELDS.get(type_id, ""), None))
        result.stay_from_source += from_source
        addr = " ".join(p for p in (text(base.get("addr1")), text(base.get("addr2"))) if p) or None
        parsed = parse_open_hours(usetime, restdate)
        result.rows.append({
            "source_place_id": content_id,
            "name": text(base.get("title")),
            "category": category,
            "area": AREA,
            "address": addr,
            "latitude": lat,
            "longitude": lon,
            "indoor": None,  # 원본에 실내 여부 필드 없음 → 미확인
            "open_hours": None if parsed is None else json.dumps(parsed, ensure_ascii=False, sort_keys=True),
            "open_hours_text": hours_text(usetime, restdate),
            "price_amount": None,
            "price_basis": None,
            "price_text": text(intro.get(FEE_FIELDS.get(type_id, ""), None)),
            "default_stay_min": stay,
            "overview": text(base.get("overview")),
            "updated_at": raw.fetched_at.get(content_id) or raw.retrieved_at,
        })
    missing_name = [r["source_place_id"] for r in result.rows if r["name"] is None]
    for content_id in missing_name:
        result.skip("장소명 없음", content_id)
    result.rows = [r for r in result.rows if r["name"] is not None]
    return result


def insert_rows(conn: sqlite3.Connection, result: BuildResult) -> None:
    if result.retrieved_at is None:
        raise ValueError("원본 조회 시각이 없음 (fetch_log.jsonl 필요)")
    source_id = conn.execute(
        "INSERT INTO data_sources (code, provider, dataset_name, license, url, base_date, retrieved_at) "
        "VALUES (:code, :provider, :dataset_name, :license, :url, :base_date, :retrieved_at)",
        {**SOURCE, "retrieved_at": result.retrieved_at}).lastrowid
    columns = ["source_place_id", "name", "category", "area", "address", "latitude", "longitude", "indoor",
               "open_hours", "open_hours_text", "price_amount", "price_basis", "price_text",
               "default_stay_min", "overview", "updated_at"]
    conn.executemany(
        f"INSERT INTO places ({', '.join(columns)}, source_id) "
        f"VALUES ({', '.join(':' + c for c in columns)}, :source_id)",
        [{**row, "source_id": source_id} for row in result.rows])
