"""Bounding box (cos-latitude correction) and the walking-radius setting. [가상] coordinates only."""
import math

import pytest

from app.data.geo import EARTH_RADIUS_M, bounding_box, haversine_m
from app.data.settings import (DEFAULT_WALK_RADIUS_M, ENV_WALK_RADIUS_M, SettingsError,
                               walk_radius_m)

HAEUNDAE_LIKE = (35.16, 129.16)  # [가상] test point, not the agreed area center


def test_box_height_is_angular_radius():
    box = bounding_box(*HAEUNDAE_LIKE, 1500)
    dlat = math.degrees(1500 / EARTH_RADIUS_M)
    assert box.max_lat - HAEUNDAE_LIKE[0] == pytest.approx(dlat, abs=1e-8)
    assert HAEUNDAE_LIKE[0] - box.min_lat == pytest.approx(dlat, abs=1e-8)


@pytest.mark.parametrize("lat", [0.0, 35.16, 60.0, -45.0])
def test_box_width_is_corrected_by_cos_latitude(lat):
    box = bounding_box(lat, 129.16, 1500)
    dlat = math.degrees(1500 / EARTH_RADIUS_M)
    half_width = box.max_lon - 129.16
    assert half_width == pytest.approx(dlat / math.cos(math.radians(lat)), rel=1e-6)
    assert half_width >= dlat  # never narrower than the height


@pytest.mark.parametrize("bearing", range(0, 360, 5))
def test_every_point_on_the_circle_is_inside_the_box(bearing):
    lat, lon = HAEUNDAE_LIKE
    box = bounding_box(lat, lon, 1500)
    # destination point at exactly 1500 m on a great circle
    d, theta = 1500 / EARTH_RADIUS_M, math.radians(bearing)
    phi1, lmb1 = math.radians(lat), math.radians(lon)
    phi2 = math.asin(math.sin(phi1) * math.cos(d) + math.cos(phi1) * math.sin(d) * math.cos(theta))
    lmb2 = lmb1 + math.atan2(math.sin(theta) * math.sin(d) * math.cos(phi1),
                             math.cos(d) - math.sin(phi1) * math.sin(phi2))
    point = (math.degrees(phi2), math.degrees(lmb2))
    assert haversine_m(lat, lon, *point) == pytest.approx(1500, abs=1e-6)
    assert box.contains(*point)


@pytest.mark.parametrize("lat, lon", [(89.999, 0.0), (-89.999, 10.0), (35.0, 179.999),
                                      (35.0, -179.999)])
def test_box_near_pole_or_antimeridian_uses_full_longitude(lat, lon):
    box = bounding_box(lat, lon, 1500)
    assert (box.min_lon, box.max_lon) == (-180.0, 180.0)
    assert -90.0 <= box.min_lat <= box.max_lat <= 90.0


def test_walk_radius_default_and_value():
    assert walk_radius_m({}) == DEFAULT_WALK_RADIUS_M == 1500.0
    assert walk_radius_m({ENV_WALK_RADIUS_M: "  "}) == 1500.0
    assert walk_radius_m({ENV_WALK_RADIUS_M: "1200"}) == 1200.0
    assert walk_radius_m({ENV_WALK_RADIUS_M: "1499.5"}) == 1499.5


@pytest.mark.parametrize("raw", ["abc", "0", "-1", "nan", "inf", "1.5km"])
def test_walk_radius_invalid_is_error_not_default(raw):
    with pytest.raises(SettingsError):
        walk_radius_m({ENV_WALK_RADIUS_M: raw})


def test_walk_radius_reads_process_environment(monkeypatch):
    monkeypatch.setenv(ENV_WALK_RADIUS_M, "900")
    assert walk_radius_m() == 900.0
    monkeypatch.delenv(ENV_WALK_RADIUS_M)
    assert walk_radius_m() == 1500.0
