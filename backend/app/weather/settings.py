"""날씨 판정 설정(``config/weather.json``)과 기상청 서비스키 읽기 (FR-016, #33 A단계).

- 설정 파일이 없거나 값이 틀리면 ``WeatherSettingsError``. 기본값으로 조용히 바꾸지 않는다.
- 권역 격자는 ``config/retrieval.json`` ``areaCenters``(DEC-032)에서 ``grid.to_grid``로 계산한다.
- 서비스키: ``KMA_SERVICE_KEY``. 프로세스 환경변수가 ``.env``보다 우선한다(pipelines/env.py와 같은 방식).
  값은 반환만 하고 출력·로그·예외 메시지에 넣지 않는다. 없으면 ``None``(호출하지 않고 NO_KEY).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path

from app.weather.grid import to_grid

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "config"
CONFIG_FILE = "weather.json"
CENTERS_FILE = "retrieval.json"
ENV_FILE = REPO_ROOT / ".env"
ENV_KEY = "KMA_SERVICE_KEY"


class WeatherSettingsError(ValueError):
    """weather.json 또는 권역 중심이 없거나 잘못됨."""


@dataclass(frozen=True)
class WeatherSettings:
    status: str
    pm_approved: bool
    forecast_url: str
    base_times: tuple[str, ...]
    available_after_min: int
    max_days_ahead: int
    forecast_rows: int
    pop_exclude_gte: int
    sky_penalize: frozenset[str]
    wind_penalize_gte: float
    warning_url: str
    warning_lookback_days: int
    warning_rows: int
    warning_name_prefix: str
    warning_ignore_contains: tuple[str, ...]
    warning_exclude: Mapping[str, str]       # warnVar -> reason code
    warning_names: Mapping[str, str]         # warnVar -> 이름
    warning_cancel_commands: frozenset[str]
    area_grids: Mapping[str, tuple[int, int]]


def load_weather_settings(config_dir: Path = CONFIG_DIR) -> WeatherSettings:
    config = _read(config_dir / CONFIG_FILE)
    centers = _read(config_dir / CENTERS_FILE).get("areaCenters")
    try:
        fc, th, wr = config["forecast"], config["thresholds"], config["warnings"]
        base_times = tuple(fc["baseTimes"])
        if not base_times or any(not (isinstance(t, str) and len(t) == 4 and t.isdigit()) for t in base_times):
            raise ValueError("baseTimes")
        settings = WeatherSettings(
            status=_str(config["status"]),
            pm_approved=_bool(config["pmApproved"]),
            forecast_url=_str(fc["url"]),
            base_times=tuple(sorted(base_times)),
            available_after_min=_int(fc["availableAfterMin"], 0, 120),
            max_days_ahead=_int(fc["maxDaysAhead"], 0, 10),
            forecast_rows=_int(fc["numOfRows"], 1, 10000),
            pop_exclude_gte=_int(th["excludeOutdoor"]["popGte"], 0, 100),
            sky_penalize=frozenset(str(_int(v, 1, 4)) for v in th["penalizeOutdoor"]["skyCodes"]),
            wind_penalize_gte=_number(th["penalizeOutdoor"]["windSpeedGteMps"]),
            warning_url=_str(wr["url"]),
            warning_lookback_days=_int(wr["lookbackDays"], 0, 31),
            warning_rows=_int(wr["numOfRows"], 1, 10000),
            warning_name_prefix=_str(wr["areaNamePrefix"]),
            warning_ignore_contains=tuple(_str(v) for v in wr["ignoreAreaNameContains"]),
            warning_exclude={str(k): _str(v) for k, v in wr["excludeOutdoorWarnVars"].items()},
            warning_names={str(k): _str(v) for k, v in wr["warnVarNames"].items()},
            warning_cancel_commands=frozenset(_str(v) for v in wr["cancelCommands"]),
            area_grids={area: to_grid(float(c["latitude"]), float(c["longitude"]))
                        for area, c in dict(centers).items()},
        )
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise WeatherSettingsError(f"{config_dir / CONFIG_FILE}: invalid ({type(error).__name__}: {error})") from None
    if not settings.area_grids:
        raise WeatherSettingsError(f"{config_dir / CENTERS_FILE}: areaCenters is empty")
    return settings


def load_service_key(environ: Mapping[str, str] | None = None,
                     env_file: str | Path | None = ENV_FILE) -> str | None:
    """``KMA_SERVICE_KEY`` 값 또는 None. 환경변수 → ``.env`` 순서. 값은 출력하지 않는다."""
    process = os.environ if environ is None else environ
    value = process.get(ENV_KEY, "").strip()
    if not value and env_file is not None:
        value = _read_env_file(Path(env_file)).get(ENV_KEY, "").strip()
    return value or None


def _read_env_file(path: Path) -> dict[str, str]:
    """``KEY=VALUE`` 줄만 읽는다(pipelines/env.py read_env_file과 같은 규칙). 파일이 없으면 빈 dict."""
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        name = name.strip()
        if name.startswith("export "):
            name = name[len("export "):].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name] = value
    return values


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise WeatherSettingsError(f"{path} is missing") from None
    except ValueError:
        raise WeatherSettingsError(f"{path} is not valid JSON") from None
    if not isinstance(data, dict):
        raise WeatherSettingsError(f"{path} must be a JSON object")
    return data


def _str(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("expected a non-empty string")
    return value


def _bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("expected true/false")
    return value


def _int(value: object, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"expected an integer in [{low}, {high}]")
    return value


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("expected a non-negative number")
    return float(value)
