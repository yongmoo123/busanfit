"""Search settings read from the environment (DEC-001: walking radius is a setting, 1.5 km).

The repository never picks a radius itself; the caller reads it here and passes it to
``PlaceRepository.find_within_radius``.
"""
from collections.abc import Mapping
import math
import os

ENV_WALK_RADIUS_M = "BUSANFIT_WALK_RADIUS_M"
DEFAULT_WALK_RADIUS_M = 1500.0


class SettingsError(ValueError):
    """A setting is present but not usable. Never replaced by the default silently."""


def walk_radius_m(environ: Mapping[str, str] | None = None) -> float:
    """Walking search radius in meters from ``BUSANFIT_WALK_RADIUS_M``.

    Unset or blank → 1500 (DEC-001 initial value). Set but not a positive finite number → error,
    so a typo cannot quietly turn into the default or into an unbounded search.
    """
    raw = (os.environ if environ is None else environ).get(ENV_WALK_RADIUS_M, "").strip()
    if not raw:
        return DEFAULT_WALK_RADIUS_M
    try:
        value = float(raw)
    except ValueError:
        raise SettingsError(f"{ENV_WALK_RADIUS_M} must be a number of meters") from None
    if not math.isfinite(value) or value <= 0:
        raise SettingsError(f"{ENV_WALK_RADIUS_M} must be a positive finite number of meters")
    return value
