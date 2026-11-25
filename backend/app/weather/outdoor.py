"""장소가 확실한 실외인지 판정하고, 시각별 날씨 판정을 장소에 적용 (FR-016, #33 A단계, DEC-034 4·5).

``places.indoor``는 모든 장소가 NULL이고 그대로 둔다(정보 없음을 실내·실외로 바꾸지 않음). 대신
``config/weather.json`` ``outdoorBy`` 규칙(TourAPI 분류 코드 접두어, 먹자골목 3곳 예외)으로
``pipelines/outdoor_ids.py``가 만든 장소 ID 목록 파일(``outdoorBy.placeIdFile``)에 있으면 OUTDOOR, 없으면 UNKNOWN.

UNKNOWN은 "실내"가 아니다(판단 필요 44곳 포함). DEC-034 5에 따라 UNKNOWN 장소는 날씨로 **제외도 감점도 하지 않고**
``OUTDOOR_UNKNOWN`` 이유만 붙인다(B단계 경고 "실내·실외 정보가 없는 장소는 날씨를 반영하지 않았어요").
목록 파일이 없거나 깨졌으면 오류다(빈 목록으로 보지 않음).
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from app.weather.judge import OK, HourlyJudgement
from app.weather.settings import CONFIG_DIR, CONFIG_FILE, WeatherSettingsError

OUTDOOR = "OUTDOOR"
UNKNOWN = "UNKNOWN"

# 장소 판정 이유: 실내·실외 정보가 없어 날씨를 반영하지 않음 (DEC-034 5, 경고용)
OUTDOOR_UNKNOWN = "OUTDOOR_UNKNOWN"


@dataclass(frozen=True)
class PlaceWeather:
    outdoor: str                 # OUTDOOR / UNKNOWN
    verdict: str                 # OK / PENALIZE_OUTDOOR / EXCLUDE_OUTDOOR (UNKNOWN이면 항상 OK)
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class OutdoorList:
    place_ids: frozenset[str]
    status: str

    def status_of(self, place: object) -> str:
        """``place``: 장소 ID 문자열 또는 ``id`` 속성이 있는 객체(PlaceRecord 등)."""
        place_id = place if isinstance(place, str) else getattr(place, "id", None)
        if not isinstance(place_id, str):
            raise TypeError("place must be a place ID string or have a string .id")
        return OUTDOOR if place_id in self.place_ids else UNKNOWN


def load_outdoor_list(config_dir: Path = CONFIG_DIR) -> OutdoorList:
    try:
        config = json.loads((config_dir / CONFIG_FILE).read_text(encoding="utf-8"))
        name = config["outdoorBy"]["placeIdFile"]
        listed = json.loads((config_dir / name).read_text(encoding="utf-8"))
        places = listed["places"]
        ids = [p["placeId"] for p in places]
        status = listed["status"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise WeatherSettingsError(f"outdoor place list unavailable ({type(error).__name__})") from None
    if not all(isinstance(i, str) and i for i in ids) or not isinstance(status, str):
        raise WeatherSettingsError("outdoor place list: placeId must be non-empty strings")
    return OutdoorList(place_ids=frozenset(ids), status=status)


_default: OutdoorList | None = None


def outdoor_status(place: object, outdoor_list: OutdoorList | None = None) -> str:
    """OUTDOOR 또는 UNKNOWN. ``outdoor_list``를 주지 않으면 config의 목록을 한 번 읽어 쓴다."""
    global _default
    if outdoor_list is None:
        if _default is None:
            _default = load_outdoor_list()
        outdoor_list = _default
    return outdoor_list.status_of(place)


def place_weather(place: object, judgement: HourlyJudgement, outdoor_list: OutdoorList | None = None) -> PlaceWeather:
    """그 장소 방문 시각의 판정(``HourlyJudgement``)을 장소에 적용한다.

    - OUTDOOR: 시각 판정 그대로(제외·감점·이유, WARNING_UNCHECKED 포함)
    - UNKNOWN: 제외·감점 없음(verdict OK), reasons ``(OUTDOOR_UNKNOWN,)`` — 날씨를 반영하지 않았다는 경고용
    날씨 자체가 NOT_APPLIED면 시각 판정이 없으므로 이 함수를 부르지 않고 "날씨 미반영"으로 처리한다(README).
    """
    status = outdoor_status(place, outdoor_list)
    if status == OUTDOOR:
        return PlaceWeather(OUTDOOR, judgement.verdict, judgement.reasons)
    return PlaceWeather(UNKNOWN, OK, (OUTDOOR_UNKNOWN,))
