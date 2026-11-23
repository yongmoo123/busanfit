"""날씨 판정 결과 형식과 순수 판정 함수 (FR-016, UC-003 2단계·2a, #33 A단계).

네트워크·파일을 쓰지 않는다. 입력은 이미 파싱한 예보 값과 특보 목록이고, 임계값은 ``WeatherSettings``.

판정(실외 장소에만 의미가 있다. 실내외 판정은 ``outdoor.outdoor_status``):
- ``EXCLUDE_OUTDOOR``: 강수확률 ≥ popGte, 또는 제외 대상 특보(한파·폭염) 발효 중 (HARD)
- ``PENALIZE_OUTDOOR``: 하늘상태가 skyCodes(흐림), 또는 풍속 ≥ windSpeedGteMps (SOFT)
- ``OK``: 위에 해당 없음
판정하지 못한 경우는 ``AreaWeather.status = NOT_APPLIED``와 이유 코드로 돌려준다. 맑음·0으로 채우지 않는다.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

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
WARNING_NOT_CHECKED = "NOT_CHECKED"                 # 예보부터 판정 못 함(NOT_APPLIED)

# 판정에 쓰는 예보 항목(단기예보 category)
REQUIRED_CATEGORIES = ("POP", "SKY", "WSD")
KEPT_CATEGORIES = ("POP", "SKY", "WSD", "PTY", "TMP", "PCP")


@dataclass(frozen=True)
class ActiveWarning:
    area_code: str
    area_name: str
    warn_var: str
    warn_name: str | None
    stress: str        # "0" 주의보, "1" 경보
    command: str
    tm_fc: str


@dataclass(frozen=True)
class HourlyJudgement:
    hour: int                       # 0~23, 그 시각 예보(fcstTime HH00)
    verdict: str                    # OK / PENALIZE_OUTDOOR / EXCLUDE_OUTDOOR
    reasons: tuple[str, ...]
    pop: int                        # 강수확률 %
    sky: str                        # SKY 코드 "1"/"3"/"4"
    wind_mps: float
    pty: str | None = None          # 강수형태 코드(판정에 안 씀, 표시용)
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
    settings_status: str = "PROPOSAL"
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
                       settings_status=settings.status if settings else "PROPOSAL")


def judge_hour(hour: int, values: Mapping[str, str], settings: WeatherSettings,
               warning_reasons: Sequence[str] = ()) -> HourlyJudgement:
    """한 시각 판정. ``values``: category → fcstValue(원문 문자열). 필요한 값이 없거나 숫자가 아니면 ValueError."""
    pop = int(_number(values, "POP"))
    sky = str(int(_number(values, "SKY")))
    wind = _number(values, "WSD")
    reasons: list[str] = []
    verdict = OK
    if pop >= settings.pop_exclude_gte:
        reasons.append(POP_HIGH)
        verdict = EXCLUDE_OUTDOOR
    if warning_reasons:
        reasons.extend(warning_reasons)
        verdict = EXCLUDE_OUTDOOR
    if sky in settings.sky_penalize:
        reasons.append(SKY_OVERCAST)
        verdict = worst((verdict, PENALIZE_OUTDOOR))
    if wind >= settings.wind_penalize_gte:
        reasons.append(WIND_STRONG)
        verdict = worst((verdict, PENALIZE_OUTDOOR))
    temperature = values.get("TMP")
    return HourlyJudgement(hour=hour, verdict=verdict, reasons=tuple(reasons), pop=pop, sky=sky,
                           wind_mps=wind, pty=values.get("PTY"),
                           temperature_c=_float_or_none(temperature))


def judge_area(area: str, visit_date: date, hours: Sequence[int],
               by_hour: Mapping[int, Mapping[str, str]], settings: WeatherSettings, *,
               grid: tuple[int, int], base: tuple[str, str], warning_check: str,
               active_warnings: Sequence[ActiveWarning] = ()) -> AreaWeather:
    """요청한 시각마다 판정. 한 시각이라도 필요한 값이 없으면 NOT_APPLIED(INCOMPLETE_FORECAST)."""
    missing = [h for h in hours if any(c not in by_hour.get(h, {}) for c in REQUIRED_CATEGORIES)]
    if missing:
        return not_applied(area, visit_date, INCOMPLETE_FORECAST, settings, grid=grid, base=base,
                           detail=f"missing hours {missing}")
    warning_reasons = tuple(sorted({settings.warning_exclude[w.warn_var] for w in active_warnings
                                    if w.warn_var in settings.warning_exclude}))
    try:
        judged = tuple(judge_hour(h, by_hour[h], settings, warning_reasons) for h in hours)
    except ValueError:
        return not_applied(area, visit_date, INVALID_RESPONSE, settings, grid=grid, base=base,
                           detail="non-numeric POP/SKY/WSD")
    reasons = {r for j in judged for r in j.reasons}
    if warning_check != WARNING_CHECKED:
        reasons.add(WARNING_UNCHECKED)
    return AreaWeather(area=area, visit_date=visit_date, status=APPLIED,
                       verdict=worst(j.verdict for j in judged), reasons=tuple(sorted(reasons)),
                       hours=judged, grid=grid, base_date=base[0], base_time=base[1],
                       warning_check=warning_check, active_warnings=tuple(active_warnings),
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


def active_busan_warnings(items: Iterable[Mapping[str, object]],
                          settings: WeatherSettings) -> tuple[ActiveWarning, ...]:
    """특보 코드 목록(getPwnCd) → 지금 해제되지 않은 부산 육상 특보.

    구역·종류·강도별로 가장 최근 발표(tmFc, tmSeq)만 보고, 그 명령이 해제(cancelCommands)가 아니면 발효 중으로 본다.
    구역은 이름이 ``areaNamePrefix``로 시작하고 ``ignoreAreaNameContains``가 없는 것(코드 미확인, weather.json 참고).
    """
    latest: dict[tuple[str, str, str], Mapping[str, object]] = {}
    for item in items:
        name = str(item.get("areaName") or "")
        if not name.startswith(settings.warning_name_prefix) or \
                any(part in name for part in settings.warning_ignore_contains):
            continue
        key = (str(item.get("areaCode")), str(item.get("warnVar")), str(item.get("warnStress")))
        order = (_int_or_zero(item.get("tmFc")), _int_or_zero(item.get("tmSeq")))
        current = latest.get(key)
        if current is None or order >= (_int_or_zero(current.get("tmFc")), _int_or_zero(current.get("tmSeq"))):
            latest[key] = item
    active = []
    for (code, var, stress), item in sorted(latest.items()):
        command = str(item.get("command"))
        if command in settings.warning_cancel_commands:
            continue
        active.append(ActiveWarning(area_code=code, area_name=str(item.get("areaName")), warn_var=var,
                                    warn_name=settings.warning_names.get(var), stress=stress,
                                    command=command, tm_fc=str(item.get("tmFc"))))
    return tuple(active)


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
