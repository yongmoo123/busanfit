"""권역·방문일·시각 → ``AreaWeather`` (FR-016, #33 A단계). 아직 어디에도 연결하지 않는다(README).

순서:
1. 방문일이 오늘(KST)보다 이르거나 오늘 + ``maxDaysAhead``보다 늦으면 호출 없이 NOT_APPLIED(OUT_OF_RANGE).
2. ``KMA_SERVICE_KEY``가 없으면 호출 없이 NOT_APPLIED(NO_KEY).
3. 지금 받을 수 있는 가장 최근 발표(baseTimes 중 발표시각 + availableAfterMin 분이 지난 것)로 격자 예보 조회.
   실패 → NOT_APPLIED(FETCH_FAILED / INVALID_RESPONSE). 요청 시각 중 하나라도 값이 없으면 INCOMPLETE_FORECAST.
4. 방문일이 오늘이면 특보 조회(부산 육상 구역). 실패하면 판정은 하되 reasons에 WARNING_UNCHECKED,
   warning_check=FAILED. 오늘이 아니면 특보를 보지 않고 WARNING_UNCHECKED, warning_check=NOT_CHECKED_FUTURE.

같은 발표·격자의 예보와 같은 날의 특보는 한 provider 안에서 한 번만 호출한다(성공한 응답만 메모리 캐시,
실패는 캐시하지 않음). 특보는 같은 날 안에서는 다시 조회하지 않으므로 B단계에서 요청마다 provider를 새로 만들거나
캐시 시간을 정한다(README).
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import date, datetime, timedelta, timezone

from app.weather.judge import (NO_KEY, OUT_OF_RANGE, WARNING_CHECK_FAILED, WARNING_CHECKED,
                               WARNING_NOT_CHECKED_FUTURE, AreaWeather, active_busan_warnings,
                               forecast_by_hour, judge_area, not_applied)
from app.weather.kma_client import KmaClient, KmaError
from app.weather.settings import WeatherSettings, load_service_key, load_weather_settings

KST = timezone(timedelta(hours=9))


def latest_base(now: datetime, settings: WeatherSettings) -> tuple[str, str]:
    """(base_date YYYYMMDD, base_time HHMM): ``now``에 받을 수 있는 가장 최근 발표."""
    now = now.astimezone(KST)
    wait = timedelta(minutes=settings.available_after_min)
    for day in (now.date(), now.date() - timedelta(days=1)):
        for base_time in reversed(settings.base_times):
            issued = datetime(day.year, day.month, day.day, int(base_time[:2]), int(base_time[2:]), tzinfo=KST)
            if issued + wait <= now:
                return day.strftime("%Y%m%d"), base_time
    raise ValueError("no base time within two days")  # baseTimes가 비어 있지 않으면 도달하지 않음


class WeatherProvider:
    def __init__(self, settings: WeatherSettings | None = None, key: str | None = None, *,
                 read_key: bool = True, opener: Callable[..., object] | None = None,
                 clock: Callable[[], datetime] | None = None):
        """``key``를 주지 않으면 ``read_key=True``일 때 환경변수·.env에서 읽는다(테스트는 read_key=False)."""
        self.settings = settings if settings is not None else load_weather_settings()
        if key is None and read_key:
            key = load_service_key()
        self._client = KmaClient(key, opener=opener) if key else None
        self._clock = clock if clock is not None else (lambda: datetime.now(KST))
        self._forecasts: dict[tuple[str, str, int, int], list[dict]] = {}
        self._warnings: dict[str, list[dict]] = {}

    def __repr__(self) -> str:
        return f"WeatherProvider(has_key={self._client is not None}, calls={self.calls})"

    @property
    def calls(self) -> int:
        return self._client.calls if self._client else 0

    def area_weather(self, area: str, visit_date: date, hours: Iterable[int]) -> AreaWeather:
        hours = _check_hours(hours)
        if area not in self.settings.area_grids:
            raise ValueError(f"unknown area {area!r}")
        grid = self.settings.area_grids[area]
        now = self._clock().astimezone(KST)
        today = now.date()
        if not today <= visit_date <= today + timedelta(days=self.settings.max_days_ahead):
            return not_applied(area, visit_date, OUT_OF_RANGE, self.settings, grid=grid,
                               detail=f"forecast range {today}..+{self.settings.max_days_ahead}d")
        if self._client is None:
            return not_applied(area, visit_date, NO_KEY, self.settings, grid=grid)
        base = latest_base(now, self.settings)
        forecast = self._forecast(base, grid)
        if isinstance(forecast, KmaError):
            return not_applied(area, visit_date, forecast.kind, self.settings, grid=grid, base=base,
                               detail=str(forecast))
        if visit_date == today:
            warnings = self._warning_items(today)
            if isinstance(warnings, KmaError):
                check, active = WARNING_CHECK_FAILED, ()
            else:
                check, active = WARNING_CHECKED, active_busan_warnings(warnings, self.settings)
        else:
            check, active = WARNING_NOT_CHECKED_FUTURE, ()
        return judge_area(area, visit_date, hours, forecast_by_hour(forecast, visit_date, *grid), self.settings,
                          grid=grid, base=base, warning_check=check, active_warnings=active)

    def areas_weather(self, areas: Iterable[str], visit_date: date, hours: Iterable[int]) -> dict[str, AreaWeather]:
        hours = _check_hours(hours)
        return {area: self.area_weather(area, visit_date, hours) for area in areas}

    def _forecast(self, base: tuple[str, str], grid: tuple[int, int]) -> list[dict] | KmaError:
        key = (base[0], base[1], grid[0], grid[1])
        if key not in self._forecasts:
            assert self._client is not None
            try:
                items = self._client.items(self.settings.forecast_url, {
                    "pageNo": 1, "numOfRows": self.settings.forecast_rows, "dataType": "JSON",
                    "base_date": base[0], "base_time": base[1], "nx": grid[0], "ny": grid[1]})
            except KmaError as error:
                return error
            self._forecasts[key] = items
        return self._forecasts[key]

    def _warning_items(self, today: date) -> list[dict] | KmaError:
        key = today.isoformat()
        if key not in self._warnings:
            assert self._client is not None
            start = today - timedelta(days=self.settings.warning_lookback_days)
            try:
                items = self._client.items(self.settings.warning_url, {
                    "pageNo": 1, "numOfRows": self.settings.warning_rows, "dataType": "JSON",
                    "fromTmFc": start.strftime("%Y%m%d"), "toTmFc": today.strftime("%Y%m%d")})
            except KmaError as error:
                return error
            self._warnings[key] = items
        return self._warnings[key]


def _check_hours(hours: Iterable[int]) -> tuple[int, ...]:
    values = tuple(hours)
    if not values or any(type(h) is not int or not 0 <= h <= 23 for h in values):
        raise ValueError("hours must be a non-empty list of integers 0..23")
    return tuple(sorted(set(values)))

