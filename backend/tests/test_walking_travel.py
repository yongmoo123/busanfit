"""COMP-06 walking travel time (FR-009, DEC-016). Synthetic coordinates only."""
from dataclasses import replace
import inspect
import json
import math
from pathlib import Path

import pytest

from app.constraints.defaults import CONFIG
from app.courses.fakes import synthetic_place
from app.courses.scheduler import TravelCache
from app.data.geo import EARTH_RADIUS_M
from app.domain.course import TravelEstimate, TravelTimeProvider
from app.travel.walking import WalkingTravelTimeProvider, create_travel_provider

ORIGIN = (35.16, 129.16)


def at(identifier, meters_north=0.0, *, lat=None, lon=None):
    """[가상] place ``meters_north`` along the meridian from ORIGIN (exact great-circle meters)."""
    base = synthetic_place(identifier)
    if lat is None:
        lat = ORIGIN[0] + math.degrees(meters_north / EARTH_RADIUS_M)
    return replace(base, latitude=lat, longitude=ORIGIN[1] if lon is None else lon)


@pytest.fixture
def provider():
    return create_travel_provider()


def minutes(provider, meters, *, injury):
    return provider.estimate(at('a'), at('b', meters), injury=injury).minutes


def test_factory_reads_speeds_from_config_not_code(provider):
    assert provider.normal_kmh == CONFIG['injury']['normalWalkingKmh'] == 4
    assert provider.injury_kmh == CONFIG['injury']['walkingKmh'] == 3
    travel = json.loads((Path(__file__).resolve().parents[2] / 'config/travel.json').read_text(encoding='utf-8'))
    assert provider.detour_factor == travel['walk']['detourFactor'] == 1.0
    # Same signature as the port in app.domain.course (unchanged interface).
    assert inspect.signature(type(provider).estimate) == inspect.signature(TravelTimeProvider.estimate)


def test_known_distance_1km_normal_15_injury_20(provider):
    assert minutes(provider, 1000, injury=False) == 15
    assert minutes(provider, 1000, injury=True) == 20


def test_injury_flag_changes_speed(provider):
    for meters in (100, 400, 750, 1234):
        assert minutes(provider, meters, injury=True) >= minutes(provider, meters, injury=False)
    assert minutes(provider, 600, injury=False) == 9   # 600 m / 66.67 m/min = 9.0
    assert minutes(provider, 600, injury=True) == 12   # 600 m / 50 m/min = 12.0


@pytest.mark.parametrize('meters, normal, injury', [
    (999, 15, 20),      # 14.985 -> 15, 19.98 -> 20
    (1000, 15, 20),     # exact -> no extra minute from float noise
    (1001, 16, 21),     # 15.015 -> 16, 20.02 -> 21
    (500, 8, 10),       # 7.5 -> 8, exact 10
    (501, 8, 11),       # 7.515 -> 8, 10.02 -> 11
    (0.5, 1, 1),        # any positive distance is at least 1 minute
])
def test_rounding_is_ceiling_per_minute(provider, meters, normal, injury):
    assert minutes(provider, meters, injury=False) == normal
    assert minutes(provider, meters, injury=True) == injury


def test_injury_limit_boundary_with_config_values(provider):
    # maxLegWalkingMinutes is unchanged (10). 500 m is exactly 10 min for INJURY, 501 m is 11.
    assert CONFIG['injury']['maxLegWalkingMinutes'] == 10
    assert minutes(provider, 500, injury=True) == 10
    assert minutes(provider, 501, injury=True) == 11


def test_speed_and_detour_settings_are_applied():
    custom = WalkingTravelTimeProvider.from_config(
        {'injury': {'normalWalkingKmh': 5, 'walkingKmh': 2}},
        {'walk': {'detourFactor': 1.2, 'roundingToleranceMinutes': 1e-9}})
    assert minutes(custom, 1000, injury=False) == 15   # 1200 m / 83.33 = 14.4 -> 15
    assert minutes(custom, 1000, injury=True) == 36    # 1200 m / 33.33 = 36.0
    assert minutes(WalkingTravelTimeProvider(normal_kmh=6, injury_kmh=3), 1000, injury=False) == 10


def test_symmetric_and_integer(provider):
    a, b = at('a'), at('b', 0, lat=35.1631, lon=129.1635)
    there, back = provider.estimate(a, b, injury=False), provider.estimate(b, a, injury=False)
    assert isinstance(there, TravelEstimate) and type(there.minutes) is int
    assert there == back


def test_same_coordinates_different_places_is_zero(provider):
    # Two different places in the same building: a computed 0, not a fallback.
    assert provider.estimate(at('a'), at('b'), injury=True) == TravelEstimate(0)


def test_same_place_id_is_an_error(provider):
    with pytest.raises(ValueError, match='same place'):
        provider.estimate(at('a'), at('a', 300), injury=False)


@pytest.mark.parametrize('field', ['latitude', 'longitude'])
def test_missing_coordinate_is_unavailable_not_zero(provider, field):
    missing = replace(at('b', 300), **{field: None})
    assert provider.estimate(at('a'), missing, injury=False) is None
    assert provider.estimate(missing, at('a'), injury=True) is None


@pytest.mark.parametrize('field, value', [
    ('latitude', float('nan')), ('latitude', float('inf')), ('latitude', 91.0), ('latitude', -90.5),
    ('longitude', 180.5), ('longitude', float('-inf')), ('latitude', True), ('longitude', '129.16'),
])
def test_invalid_coordinate_raises(provider, field, value):
    with pytest.raises(ValueError):
        provider.estimate(at('a'), replace(at('b'), **{field: value}), injury=False)


@pytest.mark.parametrize('flag', [None, 0, 1, 'INJURY'])
def test_injury_flag_must_be_bool(provider, flag):
    with pytest.raises(ValueError):
        provider.estimate(at('a'), at('b', 100), injury=flag)


@pytest.mark.parametrize('kwargs', [
    {'normal_kmh': 0, 'injury_kmh': 3}, {'normal_kmh': -4, 'injury_kmh': 3},
    {'normal_kmh': 4, 'injury_kmh': float('nan')}, {'normal_kmh': True, 'injury_kmh': 3},
    {'normal_kmh': '4', 'injury_kmh': 3}, {'normal_kmh': 4, 'injury_kmh': 3, 'detour_factor': 0.9},
    {'normal_kmh': 4, 'injury_kmh': 3, 'rounding_tolerance': 0.5},
    {'normal_kmh': 4, 'injury_kmh': 3, 'rounding_tolerance': -1e-9},
])
def test_invalid_settings_fail_at_construction(kwargs):
    with pytest.raises(ValueError):
        WalkingTravelTimeProvider(**kwargs)


def test_missing_config_key_fails():
    with pytest.raises(KeyError):
        WalkingTravelTimeProvider.from_config({'injury': {'walkingKmh': 3}}, {'walk': {'detourFactor': 1.0}})


def test_works_through_scheduler_travel_cache(provider):
    a, b = at('a'), at('b', 1000)
    cache = TravelCache(provider, injury=True)
    assert cache(a, b) == TravelEstimate(20)
    assert cache.unavailable is False
    assert cache(a, replace(at('c'), latitude=None)) is None
    assert cache.unavailable is True
