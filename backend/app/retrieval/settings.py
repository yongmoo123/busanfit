"""Retrieval settings — COMP-04 (FR-007, DEC-001, DEC-023).

- Area centers: ``config/retrieval.json`` ``areaCenters`` (DEC-023 ①; 해운대해수욕장 by default).
- Walking radius: ``BUSANFIT_WALK_RADIUS_M`` via ``app.data.settings.walk_radius_m`` (DEC-001, 1500 m).
- Candidate cap: ``CourseSettings.max_candidates`` (``config/courses.json``, SDD 7.3, 20).
- Excluded place IDs: files listed in ``excludedPlaceIdFiles``. Today only the 사후면세점 list
  (DEC-023 ④). DEC-023 ④ 판별 기준: 분류 코드 SH040300 (찬용 결정, 11/19) — see
  ``pipelines/duty_free_ids.py``.

A missing or broken setting raises ``RetrievalSettingsError`` (a ``ValueError``); it is never
replaced by a default silently. In particular a missing ``retrieval.json``,
``excludedPlaceIdFiles`` key or list file does not mean "no exclusion".
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
import math
from pathlib import Path

from app.data.settings import walk_radius_m
from app.domain.course import CourseSettings
from app.data.place_id import parse_place_id

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"
CONFIG_FILE = "retrieval.json"

# Used only when retrieval.json has no entry for HAEUNDAE (DEC-023 ①).
DEFAULT_AREA_CENTERS: Mapping[str, tuple[float, float]] = {"HAEUNDAE": (35.159084, 129.160279)}


@dataclass(frozen=True)
class RetrievalSettings:
    area_centers: Mapping[str, tuple[float, float]]
    radius_m: float
    max_candidates: int = 20
    excluded_place_ids: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        for area, center in self.area_centers.items():
            if not isinstance(area, str) or not isinstance(center, tuple) or len(center) != 2:
                raise ValueError("area center must be (latitude, longitude)")
            _check_coordinate(center[0], -90.0, 90.0, "latitude")
            _check_coordinate(center[1], -180.0, 180.0, "longitude")
        if not _is_number(self.radius_m) or not math.isfinite(self.radius_m) or self.radius_m <= 0:
            raise ValueError("radius_m must be a positive finite number")
        if type(self.max_candidates) is not int or not 1 <= self.max_candidates <= 20:
            raise ValueError("max_candidates must be an integer in [1, 20]")
        if not isinstance(self.excluded_place_ids, frozenset) or \
                not all(isinstance(value, str) for value in self.excluded_place_ids):
            raise ValueError("excluded_place_ids must be a frozenset of strings")


class RetrievalSettingsError(ValueError):
    """retrieval.json or an excluded-ID list is missing or broken (never "no exclusion")."""


def load_retrieval_settings(environ: Mapping[str, str] | None = None,
                            config_dir: Path = CONFIG_DIR) -> RetrievalSettings:
    """Load ``retrieval.json``. A missing file, a missing ``excludedPlaceIdFiles`` key or an
    unreadable list is an error: silently using ``[]`` would lift the 사후면세점 exclusion
    (DEC-023 ④). An explicit ``"excludedPlaceIdFiles": []`` means "no exclusion" on purpose.
    Tests without exclusions inject ``RetrievalSettings`` directly instead.
    """
    path = config_dir / CONFIG_FILE
    config = _read_json(path)
    if not isinstance(config, dict):
        raise RetrievalSettingsError(f"{path}: top level must be an object")
    centers = dict(DEFAULT_AREA_CENTERS)
    for area, value in config.get("areaCenters", {}).items():
        centers[area] = (value["latitude"], value["longitude"])
    if "excludedPlaceIdFiles" not in config:
        raise RetrievalSettingsError(f"{path}: excludedPlaceIdFiles is required (DEC-023 ④)")
    names = config["excludedPlaceIdFiles"]
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise RetrievalSettingsError(f"{path}: excludedPlaceIdFiles must be a list of file names")
    excluded: set[str] = set()
    for name in names:
        list_path = config_dir / name
        content = _read_json(list_path)
        listed = content.get("placeIds") if isinstance(content, dict) else None
        if not isinstance(listed, list) or not all(isinstance(value, str) for value in listed):
            raise RetrievalSettingsError(f"{list_path}: placeIds must be a list of place IDs")
        for place_id in listed:
            try:
                parse_place_id(place_id)  # a malformed ID is a broken setting, not "no exclusion"
            except ValueError as error:
                raise RetrievalSettingsError(f"{list_path}: malformed place ID {place_id!r}") from error
        excluded.update(listed)
    return RetrievalSettings(area_centers=centers, radius_m=walk_radius_m(environ),
                             max_candidates=CourseSettings().max_candidates,
                             excluded_place_ids=frozenset(excluded))


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RetrievalSettingsError(f"{path}: setting file not found") from error
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RetrievalSettingsError(f"{path}: cannot read setting file ({error})") from error


def _check_coordinate(value: object, low: float, high: float, name: str) -> None:
    if not _is_number(value) or not math.isfinite(value) or not low <= value <= high:  # type: ignore[operator]
        raise ValueError(f"{name} must be a number in [{low}, {high}]")


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
