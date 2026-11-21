"""권역 원 판정 — FR-020, 이슈 #36 (PM 결정 11/21: 권역 = 중심 좌표에서 도보 반경 안).

- 중심 좌표는 런타임과 같은 ``config/retrieval.json`` ``areaCenters``에서만 읽는다(여기에 따로 적지 않음).
- 반경은 런타임과 같은 ``BUSANFIT_WALK_RADIUS_M``(``app.data.settings.walk_radius_m``, 비우면 1500 m, DEC-001).
- 거리는 하버사인(``app.data.geo.haversine_m``), 거리 ≤ 반경이면 안. Repository 반경 검색과 같은 기준.
- 한 장소가 두 원에 동시에 들어가면 ``CircleOverlap``으로 멈춘다(권역을 임의로 고르지 않음).
"""
from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.data.geo import haversine_m  # noqa: E402
from app.data.settings import walk_radius_m  # noqa: E402

RETRIEVAL_CONFIG = REPO_ROOT / "config" / "retrieval.json"

Centers = Mapping[str, tuple[float, float]]


class CircleOverlap(ValueError):
    """A place lies inside two area circles at once."""


def load_centers(path: Path = RETRIEVAL_CONFIG, required: tuple[str, ...] = ()) -> dict[str, tuple[float, float]]:
    """{권역: (위도, 경도)} from ``areaCenters``. A missing required area is an error."""
    config = json.loads(path.read_text(encoding="utf-8"))
    centers = {area: (float(v["latitude"]), float(v["longitude"]))
               for area, v in config.get("areaCenters", {}).items()}
    missing = [area for area in required if area not in centers]
    if missing:
        raise ValueError(f"{path}: areaCenters has no {', '.join(missing)}")
    return centers


def radius_m(environ: Mapping[str, str] | None = None) -> float:
    return walk_radius_m(environ)


def areas_containing(lat: float, lon: float, centers: Centers, radius: float) -> list[tuple[str, float]]:
    """[(권역, 거리 m)] of every circle that contains the point, nearest first."""
    hits = [(area, haversine_m(c[0], c[1], lat, lon)) for area, c in centers.items()]
    return sorted(((a, d) for a, d in hits if d <= radius), key=lambda pair: pair[1])


def area_of(lat: float, lon: float, centers: Centers, radius: float, label: str = "") -> str | None:
    """The one area whose circle contains the point, or None. Two or more → CircleOverlap."""
    hits = areas_containing(lat, lon, centers, radius)
    if len(hits) > 1:
        detail = ", ".join(f"{a} {d:.0f} m" for a, d in hits)
        raise CircleOverlap(f"{label or (lat, lon)} is inside more than one area circle: {detail}")
    return hits[0][0] if hits else None
