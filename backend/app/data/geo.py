"""Distance on WGS84 coordinates (DEC-005: Python coordinate math instead of PostGIS).

Radius search is two steps (DEC-005, SDD 5.2): a latitude/longitude bounding box that can use
the plain index ``idx_places_lat_lon``, then the exact haversine distance. The box must contain
the whole circle, so it may return extra points (its corners) but must never miss one.
"""
from dataclasses import dataclass
import math

EARTH_RADIUS_M = 6_371_008.8  # mean Earth radius (IUGG), meters

# Widens the box by about 0.1 mm so float rounding can never drop a point on the circle.
_BOX_MARGIN_DEG = 1e-9


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters between two points given in decimal degrees."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


@dataclass(frozen=True)
class BoundingBox:
    """Inclusive latitude/longitude ranges in decimal degrees."""
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    def contains(self, lat: float, lon: float) -> bool:
        return self.min_lat <= lat <= self.max_lat and self.min_lon <= lon <= self.max_lon


def bounding_box(lat: float, lon: float, radius_m: float) -> BoundingBox:
    """Smallest lat/lon box that contains every point within ``radius_m`` of (lat, lon).

    Latitude half-height is the angular radius ``r / R``. Longitude half-width is corrected for
    latitude: a degree of longitude is ``cos(lat)`` times shorter than a degree of latitude, so the
    width grows as ``asin(sin(r / R) / cos(lat))`` (≈ ``(r / R) / cos(lat)`` for small radii).
    Near a pole, or when the box would cross ±180°, the whole longitude range is used: a wider
    box only costs extra rows that the haversine step removes.
    """
    angular = radius_m / EARTH_RADIUS_M
    dlat = math.degrees(angular)
    min_lat, max_lat = lat - dlat - _BOX_MARGIN_DEG, lat + dlat + _BOX_MARGIN_DEG
    if min_lat <= -90.0 or max_lat >= 90.0:
        return BoundingBox(max(min_lat, -90.0), min(max_lat, 90.0), -180.0, 180.0)
    ratio = math.sin(angular) / math.cos(math.radians(lat))
    if ratio >= 1.0:
        return BoundingBox(min_lat, max_lat, -180.0, 180.0)
    dlon = math.degrees(math.asin(ratio)) + _BOX_MARGIN_DEG
    min_lon, max_lon = lon - dlon, lon + dlon
    if min_lon < -180.0 or max_lon > 180.0:
        return BoundingBox(min_lat, max_lat, -180.0, 180.0)
    return BoundingBox(min_lat, max_lat, min_lon, max_lon)
