"""TourAPI 원본 → places 행 변환 (네트워크 없음, 같은 원본이면 같은 결과).

규칙 (문서 근거는 pipelines/README.md):
- 장소 ID: ``{data_sources.code}:{contentid}``. contentid가 허용 문자 규칙(app.data.place_id)에 어긋나면
  값을 바꾸지 않고 건너뛰고 건수로 보고한다.
- 카테고리: DEC-013의 7개 값. 매핑표는 ``category_of`` (이슈 #7 "정할 것 2" 제안).
- 가격: DEC-014. 스프린트 2는 원문(price_text)만, 금액·기준은 NULL. 원문이 없으면 NULL(무료 아님).
- 운영시간: 확실히 읽을 수 있는 경우만 구조화(``analyze_open_hours``). 아니면 open_hours NULL, 원문만 보존.
  마지막 주문·입장 마감을 close로 쓰는 것은 제안(임시), 팀 확인 대기.
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

# 확실히 읽을 수 있는 문장만 구조화하고, 나머지는 None(원문만 보존)과 사유를 돌려준다.
# 구조와 검증(validate_open_hours: 요일 키, HH:mm, close에만 24:00, 빈 객체 금지)은 바꾸지 않는다.
#
# 처리하는 것: 시간 범위 하나 또는 "상시 개방" / 마지막 주문·입장·발권 마감 / 준비시간(브레이크)으로
# 하루 여러 구간 / 평일·주말·요일 범위별 시간 / "매일"·"월~일" 접두어 / ※ 참고 문구("자세한 사항은
# 홈페이지 참조" 같은 안내만) / 쉬는날: 연중무휴, 명절·설·추석(구조에 넣지 않음, 원문 보존),
# 매주 하나 이상 요일, 몇째 주·월 1회 + 요일(그 요일을 매주 비움 → 영업일을 부풀리지 않음).
#
# None으로 두는 것: 이용시간·쉬는날이 비었거나 "상이·문의"뿐, 계절·월별 시간, 시설·층별 시간,
# 불규칙·외부 기준·공휴일 휴무, 요일 모르는 월 1회·정기휴무, 예약제·조건부 시간, 그 밖 해석 못 한 문장.
# 쉬는날이 비어 있으면 연중무휴로 채우지 않는다.

R_NO_USE = "이용시간 없음"
R_NO_REST = "쉬는날 없음"
R_VARIES = "이용시간 상이·문의"
R_SEASONAL = "계절·월별 시간"
R_FACILITY = "시설·층별 시간"
R_CONDITIONAL = "예약제·조건부 시간"
R_REST_UNKNOWN_DAY = "휴무 요일 불명(월 1회·정기휴무 등)"
R_REST_IRREGULAR = "불규칙·외부 기준·공휴일 휴무"
R_CONFLICT = "수상: 영업 요일과 휴무 요일 모순"
R_OTHER = "해석 불가(그 밖)"

S_NO_REST_ALL_DAY = "쉬는날 없음 + 01:00~24:00"
S_CONFLICT = "영업 요일과 휴무 요일 모순"

F_ALWAYS = "상시 개방"
F_LAST = "마지막 주문·입장 마감 → close"
F_BREAK = "준비시간으로 하루 두 구간 이상"
F_BREAK_BY_DAY = "요일마다 다른 준비시간"
F_DAY_GROUPS = "평일·주말 등 요일별 시간"
F_EVERY_DAY_PREFIX = "매일·월~일 접두어"
F_NOTE = "※ 참고 문구 무시"
F_NO_CLOSE = "연중무휴"
F_HOLIDAY = "명절 휴무 표기(구조 밖, 원문 보존)"
F_WEEKLY_ONE = "매주 한 요일 휴무"
F_WEEKLY_MANY = "매주 여러 요일 휴무"
F_MONTHLY_DAY = "몇째 주·월 1회 요일 휴무(그 요일 비움)"


@dataclass(frozen=True)
class OpenHoursResult:
    parsed: dict | None
    reason: str | None = None              # parsed is None일 때 사유
    features: frozenset[str] = frozenset()  # parsed가 있을 때 쓰인 규칙
    suspicious: str | None = None           # 수상한 입력 (건수만 보고)


_T = r"(\d{1,2}):(\d{2})"
_DAY = r"[월화수목금토일](?:요일)?"
_DAY_TERM = rf"(?:법정\s*공휴일|공휴일|평일|주말|매일|{_DAY}(?:\s*[~\-]\s*{_DAY})?)"
_DAY_SPEC = rf"{_DAY_TERM}(?:\s*[,/·]\s*{_DAY_TERM})*"
_LABEL = re.compile(rf"\[\s*({_DAY_SPEC})\s*\]|({_DAY_SPEC})(?=\s*\d)")
_DAY_BRACKET = re.compile(rf"\[\s*{_DAY_SPEC}\s*\]")
_BRACKET = re.compile(r"\[[^\]]*\]")
_TOKEN = re.compile(
    rf"(?P<range>{_T}\s*[~\-]\s*{_T})"
    rf"|(?P<time>{_T})"
    r"|(?P<brk>(?:준비\s*시간|브레이크\s*타임|휴게\s*시간)(?:\s*\(\s*(?P<scope>평일|주말)\s*\))?)"
    r"|(?P<last>마지막\s*주문|라스트\s*오더|주문\s*마감|(?:입장|발권)\s*마감)"
    r"|(?P<always>상시\s*개방|24\s*시간)"
    r"|(?P<fill>[\s\-,/()]+|점심|저녁)")
_ANY_TIME = re.compile(_T)
_SEASONAL = re.compile(r"\d+\s*월|하절기|동절기|간절기|성수기|매년|계절")
_CONDITIONAL = re.compile(r"예약|견학|운항|기상|변동|입장\s*가능|조기\s*마감")
_VARIES = re.compile(r"상이|다르|문의")
_HARMLESS_NOTE = re.compile(r"자세한\s*사항은\s*(?:홈페이지\s*(?:참조|참고)|전화\s*문의)\s*(?:요망|바람)?")

_HOLIDAY = re.compile(r"(?:명절|설날?|추석)(?:\s*[·,]\s*(?:설날?|추석))*"
                      r"\s*(?:당일|연휴|전날|전일(?:\s*및\s*당일)?)?")
_DAY_LIST = rf"{_DAY}(?:\s*[,~\-]\s*{_DAY})*"
_WEEKLY = re.compile(rf"매주\s*({_DAY_LIST})(?:\s*정기\s*휴무)?")
_ORDINAL = r"(?:첫째|둘째|셋째|넷째|다섯째)"
_MONTHLY = re.compile(rf"(?:(?:매월|매달)\s*)?(?:{_ORDINAL}(?:\s*,\s*{_ORDINAL})*|[1-5](?:\s*,\s*[1-5])*\s*주)"
                      rf"\s*({_DAY})|월\s*1\s*회\s*({_DAY})")
_UNKNOWN_DAY_REST = re.compile(r"월\s*1\s*회|매월|매달|연\s*\d+\s*회|(?<!부)정기\s*휴[무점]")
_ALL_DAY_SUSPECT = re.compile(r"0?1:00\s*[~\-]\s*24:00")


def _hhmm(h: str, m: str) -> str | None:
    hour, minute = int(h), int(m)
    if minute > 59 or hour > 24 or (hour == 24 and minute != 0):
        return None
    return f"{hour:02d}:{minute:02d}"


def _minutes(h: str, m: str) -> int | None:
    value = _hhmm(h, m)
    return None if value is None else int(value[:2]) * 60 + int(value[3:])


def _fmt(minutes: int, close: bool) -> str:
    if close and minutes == 1440:
        return "24:00"
    minutes %= 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _split_note(value: str) -> tuple[str, str | None]:
    main, sep, note = value.partition("※")
    return main.strip(), (re.sub(r"\s+", " ", note.replace("※", " ")).strip() if sep else None)


def _harmless(note: str | None) -> bool:
    return note is None or bool(_HARMLESS_NOTE.fullmatch(note))


def _day_index(name: str) -> int:
    return DAYS.index(KOREAN_DAYS[name[0]])


def _day_range(first: str, last: str) -> list[str]:
    a, b = _day_index(first), _day_index(last)
    return [DAYS[(a + i) % 7] for i in range((b - a) % 7 + 1)]


def _day_spec(spec: str) -> tuple[set[str], set[str]] | None:
    """(days, explicitly named days). 평일·주말·매일·월~일(7일 전체)은 일반 표기라 explicit에 넣지 않는다.
    공휴일 시간은 요일 구조 밖이라 무시한다."""
    days: set[str] = set()
    explicit: set[str] = set()
    for part in re.split(r"\s*[,/·]\s*", spec.strip()):
        if re.fullmatch(r"(?:법정\s*)?공휴일", part):
            continue
        if part in ("매일", "평일", "주말"):
            days |= set(DAYS if part == "매일" else DAYS[:5] if part == "평일" else DAYS[5:])
            continue
        match = re.fullmatch(rf"({_DAY})(?:\s*[~\-]\s*({_DAY}))?", part)
        if not match:
            return None
        span = _day_range(match[1], match[2] or match[1])
        days |= set(span)
        if len(span) < 7:
            explicit |= set(span)
    return days, explicit


def _day_list(spec: str) -> set[str]:
    days: set[str] = set()
    for part in re.split(r"\s*,\s*", spec.strip()):
        ends = re.split(r"\s*[~\-]\s*", part)
        days |= set(_day_range(ends[0], ends[-1]))
    return days


@dataclass
class _Group:
    days: set[str]
    explicit: set[str]
    main: tuple[int, int]
    breaks: list[tuple[int, int, str | None]]
    lasts: list[int]
    always: bool


def _parse_body(body: str, days: set[str], explicit: set[str]) -> _Group | None:
    main: tuple[int, int] | None = None
    breaks: list[tuple[int, int, str | None]] = []
    lasts: list[int] = []
    mode, scope, always, pos = None, None, False, 0
    while pos < len(body):
        tok = _TOKEN.match(body, pos)
        if tok is None:
            return None
        pos = tok.end()
        if tok["range"]:
            h1, m1, h2, m2 = _ANY_TIME.findall(tok["range"])[0] + _ANY_TIME.findall(tok["range"])[1]
            start, end = _minutes(h1, m1), _minutes(h2, m2)
            if start is None or end is None or start == 1440 or start == end:
                return None
            if mode is None and main is None:
                main = (start, end)
            elif mode == "break":
                breaks.append((start, end, scope))
            else:
                return None
        elif tok["time"]:
            value = _minutes(*_ANY_TIME.match(tok["time"]).groups())
            if mode != "last" or value is None:
                return None
            lasts.append(value % 1440)
        elif tok["brk"]:
            mode, scope = "break", tok["scope"]
        elif tok["last"]:
            mode = "last"
        elif tok["always"]:
            if main is not None or mode is not None:
                return None
            main, always = (0, 1440), True
    if main is None:
        return None
    return _Group(days, explicit, main, breaks, lasts, always)


def _intervals(group: _Group, day: str) -> list[dict] | None:
    start, end = group.main
    if end <= start:
        end += 1440                       # 자정 넘김
    segments = [[start, end]]
    weekday = day in DAYS[:5]
    for b_start, b_end, scope in sorted(group.breaks):
        if scope is not None and (scope == "평일") != weekday:
            continue
        if b_start < start:
            b_start += 1440
        if b_end <= b_start:
            b_end += 1440
        inside = next((s for s in segments if s[0] < b_start and b_end < s[1]), None)
        if inside is None:
            return None
        segments.remove(inside)
        segments += [[inside[0], b_start], [b_end, inside[1]]]
        segments.sort()
    for last in group.lasts:
        # 제안(임시), 팀 확인 대기: 마지막 주문·입장 마감 시각을 그 구간의 close로 쓴다 (보수적 처리).
        t = last + 1440 if last <= start else last
        inside = next((s for s in segments if s[0] < t <= s[1]), None)
        if inside is None:
            return None
        inside[1] = t
    return [{"open": _fmt(a, close=False), "close": _fmt(b, close=True)} for a, b in segments]


def _rest(rest: str) -> tuple[set[str], set[str]] | str:
    """(closed days, features) or a reason string."""
    main, note = _split_note(rest)
    features: set[str] = set()
    if not _harmless(note):
        return R_VARIES if "상이" in (note or "") else R_REST_IRREGULAR
    if note is not None:
        features.add(F_NOTE)
    main = re.sub(r"\(\s*전화\s*문의\s*\)", "", main).strip()
    if not main:
        return R_REST_IRREGULAR
    closed: set[str] = set()
    weekly_days = 0
    after_weekly = False  # "매주 월요일, 화요일" / "매주 일요일 / 월요일"처럼 이어지는 요일
    for item in re.split(r"\s*/\s*", main):
        pieces = [item] if any(p.fullmatch(item) for p in (_HOLIDAY, _WEEKLY, _MONTHLY)) \
            else re.split(r"\s*,\s*", item)
        for piece in pieces:
            weekly, monthly = _WEEKLY.fullmatch(piece), _MONTHLY.fullmatch(piece)
            if piece == "연중무휴":
                features.add(F_NO_CLOSE)
            elif _HOLIDAY.fullmatch(piece):
                features.add(F_HOLIDAY)
            elif weekly or (after_weekly and re.fullmatch(_DAY_LIST, piece)):
                days = _day_list(weekly[1] if weekly else piece)
                closed |= days
                weekly_days += len(days)
                after_weekly = True
                continue
            elif monthly:
                # 몇째 주·월 1회 휴무: 해당 요일을 매주 비운다. 매주 영업으로 바꾸지 않는다.
                closed.add(KOREAN_DAYS[(monthly[1] or monthly[2])[0]])
                features.add(F_MONTHLY_DAY)
            else:
                return R_REST_UNKNOWN_DAY if _UNKNOWN_DAY_REST.search(piece) else R_REST_IRREGULAR
            after_weekly = False
    if F_NO_CLOSE in features and closed:
        return R_OTHER
    if weekly_days:
        features.add(F_WEEKLY_MANY if weekly_days > 1 else F_WEEKLY_ONE)
    return closed, features


def analyze_open_hours(usetime: str | None, restdate: str | None) -> OpenHoursResult:
    """Structure only what is certain; otherwise ``parsed`` is None with a reason (원문은 따로 보존)."""
    use, rest = text(usetime), text(restdate)
    if use is not None:
        use = re.sub(r"<br\s*/?>", "\n", use, flags=re.IGNORECASE).strip() or None
    if use is None:
        return OpenHoursResult(None, R_NO_USE)
    use_main, use_note = _split_note(use)
    if rest is None:  # 쉬는날 모름 → 연중무휴·매일 영업으로 채우지 않는다
        suspect = S_NO_REST_ALL_DAY if _ALL_DAY_SUSPECT.fullmatch(use_main) else None
        return OpenHoursResult(None, R_NO_REST, suspicious=suspect)
    if not _ANY_TIME.search(use_main) and not _TOKEN.fullmatch(use_main):
        return OpenHoursResult(None, R_VARIES if _VARIES.search(use) else R_OTHER)
    if _SEASONAL.search(use):
        return OpenHoursResult(None, R_SEASONAL)
    if any(not _DAY_BRACKET.fullmatch(b[0]) for b in _BRACKET.finditer(use_main)):
        return OpenHoursResult(None, R_FACILITY)
    if _CONDITIONAL.search(use):
        return OpenHoursResult(None, R_CONDITIONAL)
    if not _harmless(use_note):
        return OpenHoursResult(None, R_VARIES if "상이" in (use_note or "") else R_OTHER)

    rest_result = _rest(rest)
    if isinstance(rest_result, str):
        return OpenHoursResult(None, rest_result)
    closed, features = rest_result
    if use_note is not None:
        features.add(F_NOTE)

    labels = list(_LABEL.finditer(use_main))
    groups: list[_Group] = []
    if not labels:
        group = _parse_body(use_main, set(DAYS), set())
        if group is None:
            return OpenHoursResult(None, R_OTHER)
        groups.append(group)
    else:
        if use_main[:labels[0].start()].strip(" -\n\t"):
            return OpenHoursResult(None, R_OTHER)
        for i, label in enumerate(labels):
            spec = _day_spec(label[1] or label[2])
            end = labels[i + 1].start() if i + 1 < len(labels) else len(use_main)
            group = None if spec is None else _parse_body(use_main[label.end():end], *spec)
            if group is None:
                return OpenHoursResult(None, R_OTHER)
            groups.append(group)
        if len(groups) == 1 and groups[0].days == set(DAYS):
            features.add(F_EVERY_DAY_PREFIX)

    covered: set[str] = set()
    for group in groups:
        if covered & group.days:
            return OpenHoursResult(None, R_OTHER)
        covered |= group.days
        if group.explicit & closed:   # 시간을 적은 요일이 휴무 요일 → 어느 쪽도 믿지 않는다
            return OpenHoursResult(None, R_CONFLICT, suspicious=S_CONFLICT)
    if covered | closed != set(DAYS) or closed == set(DAYS):
        return OpenHoursResult(None, R_OTHER)

    parsed: dict[str, list[dict]] = {}
    for group in groups:
        for day in group.days:
            if day in closed:
                parsed[day] = []
                continue
            intervals = _intervals(group, day)
            if intervals is None:
                return OpenHoursResult(None, R_OTHER)
            parsed[day] = intervals
    for day in closed:
        parsed[day] = []
    parsed = {day: parsed[day] for day in DAYS}
    validate_open_hours(parsed)

    if len(groups) > 1:
        features.add(F_DAY_GROUPS)
    if any(g.always for g in groups):
        features.add(F_ALWAYS)
    if any(g.lasts for g in groups):
        features.add(F_LAST)
    gaps = {tuple((a["close"], b["open"]) for a, b in zip(v, v[1:])) for v in parsed.values() if v}
    if any(gaps_of_day for gaps_of_day in gaps):
        features.add(F_BREAK)
        if len(gaps) > 1:
            features.add(F_BREAK_BY_DAY)
    return OpenHoursResult(parsed, features=frozenset(features))


def parse_open_hours(usetime: str | None, restdate: str | None) -> dict | None:
    """Structured hours, or None when not certain (see analyze_open_hours)."""
    return analyze_open_hours(usetime, restdate).parsed


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
    hours_patterns: Counter = field(default_factory=Counter)
    hours_null_reasons: Counter = field(default_factory=Counter)
    hours_suspicious: Counter = field(default_factory=Counter)
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
            "open_hours_patterns": dict(sorted(self.hours_patterns.items())),
            "open_hours_null_reasons": dict(sorted(self.hours_null_reasons.items())),
            "open_hours_suspicious": {"count": sum(self.hours_suspicious.values()),
                                      "by_kind": dict(sorted(self.hours_suspicious.items()))},
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
    hours_by_id: dict[str, OpenHoursResult] = {}
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
        hours = analyze_open_hours(usetime, restdate)
        hours_by_id[content_id] = hours
        parsed = hours.parsed
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
    for row in result.rows:
        if row["open_hours_text"] is None:
            continue
        hours = hours_by_id[row["source_place_id"]]
        if hours.parsed is None:
            result.hours_null_reasons[hours.reason] += 1
        result.hours_patterns.update(hours.features)
        if hours.suspicious:
            result.hours_suspicious[hours.suspicious] += 1
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
