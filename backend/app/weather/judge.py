"""날씨 판정 결과 형식과 순수 판정 함수 (FR-016, UC-003 2단계·2a, #33 A단계, DEC-034).

네트워크·파일을 쓰지 않는다. 입력은 이미 파싱한 예보 값과 특보 목록이고, 임계값은 ``WeatherSettings``.

판정(실외 장소에만 의미가 있다. 실내외 판정과 장소별 적용은 ``outdoor``):
- ``EXCLUDE_OUTDOOR``: 강수확률 ≥ popGte, 또는 제외 대상 특보(폭염·한파·호우·대설·태풍)가 그 시각에 발효 중 (HARD)
- ``PENALIZE_OUTDOOR``: 하늘상태가 skyCodes(흐림), 풍속 ≥ windSpeedGteMps, 또는 강풍 특보가 그 시각에 발효 중 (SOFT)
- ``OK``: 위에 해당 없음
강수형태(PTY)는 판정에 쓰지 않는다(DEC-034). 판정하지 못한 경우는 ``AreaWeather.status = NOT_APPLIED``와
이유 코드로 돌려준다. 맑음·0으로 채우지 않는다.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.weather.settings import WeatherSettings

# 판정 (심한 순서)
OK = "OK"
PENALIZE_OUTDOOR = "PENALIZE_OUTDOOR"
EXCLUDE_OUTDOOR = "EXCLUDE_OUTDOOR"
_RANK = {OK: 0, PENALIZE_OUTDOOR: 1, EXCLUDE_OUTDOOR: 2}

# 상태
APPLIED = "APPLIED"
NOT_APPLIED = "NOT_APPLIED"

# NOT_APPLIED 이유
NO_KEY = "NO_KEY"
OUT_OF_RANGE = "OUT_OF_RANGE"
FETCH_FAILED = "FETCH_FAILED"
INVALID_RESPONSE = "INVALID_RESPONSE"
INCOMPLETE_FORECAST = "INCOMPLETE_FORECAST"

# 판정 이유
POP_HIGH = "POP_HIGH"
SKY_OVERCAST = "SKY_OVERCAST"
WIND_STRONG = "WIND_STRONG"
WARNING_UNCHECKED = "WARNING_UNCHECKED"

# 특보 확인 상태
WARNING_CHECKED = "CHECKED"
WARNING_NOT_CHECKED_FUTURE = "NOT_CHECKED_FUTURE"   # 방문일이 오늘이 아님
WARNING_CHECK_FAILED = "FAILED"                     # 오늘인데 조회 실패
WARNING_CHECK_INCOMPLETE = "INCOMPLETE"             # 조회는 됐지만 방문 시각의 특보 상태를 정할 수 없는 기록이 있음
WARNING_NOT_CHECKED = "NOT_CHECKED"                 # 예보부터 판정 못 함(NOT_APPLIED)

# 특보가 판정에 주는 효과
EFFECT_EXCLUDE = "EXCLUDE"
EFFECT_PENALIZE = "PENALIZE"

# 판정에 쓰는 예보 항목(단기예보 category)
REQUIRED_CATEGORIES = ("POP", "SKY", "WSD")
KEPT_CATEGORIES = ("POP", "SKY", "WSD", "PTY", "TMP", "PCP")

_ON, _OFF, _UNKNOWN = "ON", "OFF", "UNKNOWN"


@dataclass(frozen=True)
class ActiveWarning:
    """방문 시각 중 한 시각이라도 효력이 있는 부산 육상 특보 한 건(구역·종류별)."""
    area_code: str
    area_name: str
    warn_var: str
    warn_name: str | None
    stress: str                  # "0" 주의보, "1" 경보 (효력을 시작한 발표 기준)
    command: str                 # 효력을 시작한 발표의 command
    tm_fc: str                   # 효력을 시작한 발표의 발표시각
    effect: str = EFFECT_EXCLUDE  # EXCLUDE / PENALIZE
    starts_at: datetime | None = None   # 발효 시각(KST, tz 없음)
    ends_at: datetime | None = None     # 해제 발효 시각. None이면 해제 발표 없음


@dataclass(frozen=True)
class _Change:
    at: datetime
    state: str                   # ON / OFF / UNKNOWN
    item: Mapping[str, object]


@dataclass(frozen=True)
class WarningTrack:
    """구역·특보 종류 하나의 효력 변화(발표 순서대로 적용한 결과). ``changes``는 시각 오름차순."""
    area_code: str
    area_name: str
    warn_var: str
    effect: str
    reason: str
    changes: tuple[_Change, ...]

    def state_during(self, start: datetime, end: datetime) -> tuple[str, _Change | None]:
        """[start, end) 동안의 상태: ON이 한 번이라도 있으면 ON, 아니면 UNKNOWN이 있으면 UNKNOWN, 아니면 OFF.

        첫 변화 전은 OFF(기록 없음 = 특보 없음). ON이면 그 효력을 시작한 변화도 돌려준다.
        """
        before = [c for c in self.changes if c.at <= start]
        during = [c for c in self.changes if start < c.at < end]
        states = ([before[-1]] if before else []) + during
        on = next((c for c in states if c.state == _ON), None)
        if on is not None:
            return _ON, on
        return (_UNKNOWN if any(c.state == _UNKNOWN for c in states) else _OFF), None

    def ends_after(self, change: _Change) -> datetime | None:
        later = [c for c in self.changes if c.at > change.at and c.state != _ON]
        return later[0].at if later else None


@dataclass(frozen=True)
class HourlyJudgement:
    hour: int                       # 0~23, 그 시각 예보(fcstTime HH00). 특보는 [HH:00, HH+1:00)과 비교
    verdict: str                    # OK / PENALIZE_OUTDOOR / EXCLUDE_OUTDOOR
    reasons: tuple[str, ...]
    pop: int                        # 강수확률 %
    sky: str                        # SKY 코드 "1"/"3"/"4"
    wind_mps: float
    pty: str | None = None          # 강수형태 코드(판정에 안 씀, 표시용, DEC-034)
    temperature_c: float | None = None


@dataclass(frozen=True)
class AreaWeather:
    area: str
    visit_date: date
    status: str                                 # APPLIED / NOT_APPLIED
    not_applied_reason: str | None = None       # NO_KEY / OUT_OF_RANGE / FETCH_FAILED / ...
    verdict: str | None = None                  # APPLIED일 때 시간별 판정 중 가장 심한 것
    reasons: tuple[str, ...] = ()
    hours: tuple[HourlyJudgement, ...] = ()
    grid: tuple[int, int] | None = None
    base_date: str | None = None                # 발표일 YYYYMMDD
    base_time: str | None = None                # 발표시각 HHMM
    warning_check: str = WARNING_NOT_CHECKED
    active_warnings: tuple[ActiveWarning, ...] = ()
    settings_status: str = "APPROVED"
    source: str = "기상청 단기예보 조회서비스"
    detail: str | None = None                   # 실패 내용(키·URL 없음)

    @property
    def applied(self) -> bool:
        return self.status == APPLIED


def not_applied(area: str, visit_date: date, reason: str, settings: WeatherSettings | None = None,
                *, grid: tuple[int, int] | None = None, detail: str | None = None,
                base: tuple[str, str] | None = None) -> AreaWeather:
    return AreaWeather(area=area, visit_date=visit_date, status=NOT_APPLIED, not_applied_reason=reason,
                       grid=grid, detail=detail,
                       base_date=base[0] if base else None, base_time=base[1] if base else None,
                       settings_status=settings.status if settings else "APPROVED")


def judge_hour(hour: int, values: Mapping[str, str], settings: WeatherSettings,
               exclude_warnings: Sequence[str] = (), penalize_warnings: Sequence[str] = (),
               warning_unchecked: bool = False) -> HourlyJudgement:
    """한 시각 판정. ``values``: category → fcstValue(원문 문자열). 필요한 값이 없거나 숫자가 아니면 ValueError.

    ``exclude_warnings``·``penalize_warnings``: 그 시각에 효력이 있는 특보의 이유 코드.
    ``warning_unchecked``: 그 시각의 특보 상태를 정할 수 없음(판정은 바꾸지 않고 WARNING_UNCHECKED만 붙임).
    """
    pop = int(_number(values, "POP"))
    sky = str(int(_number(values, "SKY")))
    wind = _number(values, "WSD")
    reasons: list[str] = []
    verdict = OK
    if pop >= settings.pop_exclude_gte:
        reasons.append(POP_HIGH)
        verdict = EXCLUDE_OUTDOOR
    if exclude_warnings:
        reasons.extend(exclude_warnings)
        verdict = EXCLUDE_OUTDOOR
    if sky in settings.sky_penalize:
        reasons.append(SKY_OVERCAST)
        verdict = worst((verdict, PENALIZE_OUTDOOR))
    if wind >= settings.wind_penalize_gte:
        reasons.append(WIND_STRONG)
        verdict = worst((verdict, PENALIZE_OUTDOOR))
    if penalize_warnings:
        reasons.extend(penalize_warnings)
        verdict = worst((verdict, PENALIZE_OUTDOOR))
    if warning_unchecked:
        reasons.append(WARNING_UNCHECKED)
    temperature = values.get("TMP")
    return HourlyJudgement(hour=hour, verdict=verdict, reasons=tuple(reasons), pop=pop, sky=sky,
                           wind_mps=wind, pty=values.get("PTY"),
                           temperature_c=_float_or_none(temperature))


def judge_area(area: str, visit_date: date, hours: Sequence[int],
               by_hour: Mapping[int, Mapping[str, str]], settings: WeatherSettings, *,
               grid: tuple[int, int], base: tuple[str, str], warning_check: str,
               warning_tracks: Sequence[WarningTrack] = ()) -> AreaWeather:
    """요청한 시각마다 판정. 한 시각이라도 필요한 값이 없으면 NOT_APPLIED(INCOMPLETE_FORECAST).

    특보(``warning_tracks``)는 시각마다 [HH:00, HH+1:00)에 효력이 있는지 따로 본다. 상태를 정할 수 없는 시각이
    하나라도 있으면 ``warning_check``를 INCOMPLETE로 바꾼다.
    """
    missing = [h for h in hours if any(c not in by_hour.get(h, {}) for c in REQUIRED_CATEGORIES)]
    if missing:
        return not_applied(area, visit_date, INCOMPLETE_FORECAST, settings, grid=grid, base=base,
                           detail=f"missing hours {missing}")
    active: dict[tuple[str, str], ActiveWarning] = {}
    judged: list[HourlyJudgement] = []
    incomplete = False
    try:
        for h in hours:
            start = datetime.combine(visit_date, time(h))
            exclude, penalize, unknown = set(), set(), False
            for track in warning_tracks:
                state, change = track.state_during(start, start + timedelta(hours=1))
                if state == _UNKNOWN:
                    unknown = True
                elif state == _ON and change is not None:
                    (exclude if track.effect == EFFECT_EXCLUDE else penalize).add(track.reason)
                    active.setdefault((track.area_code, track.warn_var), _active(track, change, settings))
            incomplete = incomplete or unknown
            judged.append(judge_hour(h, by_hour[h], settings, tuple(sorted(exclude)), tuple(sorted(penalize)),
                                     unknown))
    except ValueError:
        return not_applied(area, visit_date, INVALID_RESPONSE, settings, grid=grid, base=base,
                           detail="non-numeric POP/SKY/WSD")
    if incomplete and warning_check == WARNING_CHECKED:
        warning_check = WARNING_CHECK_INCOMPLETE
    reasons = {r for j in judged for r in j.reasons}
    if warning_check != WARNING_CHECKED:
        reasons.add(WARNING_UNCHECKED)
    return AreaWeather(area=area, visit_date=visit_date, status=APPLIED,
                       verdict=worst(j.verdict for j in judged), reasons=tuple(sorted(reasons)),
                       hours=tuple(judged), grid=grid, base_date=base[0], base_time=base[1],
                       warning_check=warning_check, active_warnings=tuple(active[k] for k in sorted(active)),
                       settings_status=settings.status)


def worst(verdicts: Iterable[str]) -> str:
    result = OK
    for verdict in verdicts:
        if _RANK[verdict] > _RANK[result]:
            result = verdict
    return result


def forecast_by_hour(items: Iterable[Mapping[str, object]], visit_date: date,
                     nx: int, ny: int) -> dict[int, dict[str, str]]:
    """단기예보 item 목록 → {시: {category: fcstValue}}. 방문일·격자가 다른 항목은 버린다."""
    day = visit_date.strftime("%Y%m%d")
    result: dict[int, dict[str, str]] = {}
    for item in items:
        if str(item.get("fcstDate")) != day or str(item.get("nx")) != str(nx) or str(item.get("ny")) != str(ny):
            continue
        category, time_text = str(item.get("category")), str(item.get("fcstTime"))
        if category not in KEPT_CATEGORIES or len(time_text) != 4 or not time_text.isdigit() \
                or time_text[2:] != "00":
            continue
        result.setdefault(int(time_text[:2]), {})[category] = str(item.get("fcstValue"))
    return result


def busan_warning_tracks(items: Iterable[Mapping[str, object]],
                         settings: WeatherSettings) -> tuple[WarningTrack, ...]:
    """특보 코드 목록(getPwnCd) → 판정에 쓰는 부산 육상 특보의 구역·종류별 효력 변화.

    필드 의미 출처: 공공데이터포털 기상청_기상특보 조회서비스 명세(data.go.kr/data/15000415, 특보코드조회)
    - command "1-발표, 2-해제, 3-연장, 6-정정, 7-변경발표, 8-변경해제"
    - cancel "0-정상, 1-취소된 특보"
    - startTime "발표발효시각(특보발표시에만 제공)", endTime "해제발효시각(특보해제시에만 제공)"
    11/24 실제 응답(전국 528건)에서 확인: command 1은 startTime만 있고 발표 시각보다 늦은 경우가 있다(발효 예정),
    2는 endTime만 있고 발표 시각보다 늦은 경우가 있다(해제 예정), 7은 같은 구역·종류의 주의보↔경보 변경이며
    바뀌기 전 강도의 해제 기록이 따로 오지 않는다. 그래서 강도(주의보·경보)를 나누지 않고 구역·종류별로 본다.

    규칙(``config/weather.json`` warnings):
    - 대상: 이름이 ``areaNamePrefix``로 시작하고 ``ignoreAreaNameContains``가 없는 구역, 제외·감점 대상 warnVar
    - cancel이 ``cancelledValues``이면 효력 없는 기록이라 무시한다
    - 발표 순서(tmFc, tmSeq, 같은 발표에서는 해제 먼저)대로 적용한다. 발표(``issueCommands``)는 startTime부터 ON,
      해제(``releaseCommands``)는 endTime부터 OFF. 뒤 발표는 자기 효력 시각 이후의 앞 예정을 덮어쓴다
    - 필요한 시각이 없거나, 정정(6)·명세에 없는 command면 그 발표 시각부터 상태를 UNKNOWN으로 둔다
      (보수적으로 제외하거나 무시하지 않고 WARNING_UNCHECKED로 알린다)
    """
    effects = {**{v: (EFFECT_PENALIZE, r) for v, r in settings.warning_penalize.items()},
               **{v: (EFFECT_EXCLUDE, r) for v, r in settings.warning_exclude.items()}}
    grouped: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    for item in items:
        name = str(item.get("areaName") or "")
        if not name.startswith(settings.warning_name_prefix) or \
                any(part in name for part in settings.warning_ignore_contains):
            continue
        var = str(item.get("warnVar"))
        if var not in effects or str(item.get("cancel")) in settings.warning_cancelled_values:
            continue
        grouped.setdefault((str(item.get("areaCode")), var), []).append(item)
    tracks = []
    for (code, var), records in sorted(grouped.items()):
        def order(item: Mapping[str, object]) -> tuple[int, int, int]:
            release_first = 0 if str(item.get("command")) in settings.warning_release_commands else 1
            return _int_or_zero(item.get("tmFc")), _int_or_zero(item.get("tmSeq")), release_first
        changes: list[_Change] = []
        for item in sorted(records, key=order):
            command = str(item.get("command"))
            if command in settings.warning_issue_commands:
                at, state = _kst(item.get("startTime")), _ON
            elif command in settings.warning_release_commands:
                at, state = _kst(item.get("endTime")), _OFF
            else:
                at, state = None, _UNKNOWN
            if at is None:
                at, state = _kst(item.get("tmFc")), _UNKNOWN
                if at is None:   # 발표 시각도 없으면 언제부터인지 모른다: 처음부터 UNKNOWN
                    at = datetime.min
            changes = [c for c in changes if c.at < at] + [_Change(at, state, item)]
        effect, reason = effects[var]
        tracks.append(WarningTrack(area_code=code, area_name=str(records[-1].get("areaName")), warn_var=var,
                                   effect=effect, reason=reason, changes=tuple(changes)))
    return tuple(tracks)


def _active(track: WarningTrack, change: _Change, settings: WeatherSettings) -> ActiveWarning:
    item = change.item
    return ActiveWarning(area_code=track.area_code, area_name=track.area_name, warn_var=track.warn_var,
                         warn_name=settings.warning_names.get(track.warn_var), stress=str(item.get("warnStress")),
                         command=str(item.get("command")), tm_fc=str(item.get("tmFc")), effect=track.effect,
                         starts_at=change.at, ends_at=track.ends_after(change))


def _kst(value: object) -> datetime | None:
    """기상청 시각 숫자 YYYYMMDDHHMM(KST) → datetime(tz 없음). 0·빈 값·형식 오류는 None."""
    text = str(value if value is not None else "").strip()
    if len(text) != 12 or not text.isdigit():
        return None
    try:
        return datetime.strptime(text, "%Y%m%d%H%M")
    except ValueError:
        return None


def _number(values: Mapping[str, str], category: str) -> float:
    raw = values[category]
    value = float(raw)  # ValueError for text such as "강수없음"
    # 기상청 결측 표시: +900 이상 / -900 이하 (활용가이드). 결측을 값으로 판정하지 않는다.
    if value != value or value >= 900 or value <= -900:
        raise ValueError(category)
    return value


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _int_or_zero(value: object) -> int:
    try:
        return int(str(value))
    except ValueError:
        return 0
