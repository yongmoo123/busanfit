"""Read TourAPI service keys from the environment or a ``.env`` file (standard library only).

Key values are returned to the caller and never printed, logged or put into exception messages.
Errors name only the variable names.

Variable names:
- ``TOURAPI_SERVICE_KEY``: one key for both services.
- ``TOURAPI_KOR_SERVICE_KEY`` / ``TOURAPI_WITH_SERVICE_KEY``: per service (국문 관광정보 / 무장애 여행 정보).
  A per-service name wins over the shared one for that service.
The process environment wins over the ``.env`` file.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path

SHARED = "TOURAPI_SERVICE_KEY"
KOR = "TOURAPI_KOR_SERVICE_KEY"
WITH = "TOURAPI_WITH_SERVICE_KEY"
NAMES = (SHARED, KOR, WITH)


class MissingKeyError(RuntimeError):
    """No usable key name is set. The message lists names only."""


@dataclass(frozen=True)
class ServiceKeys:
    kor: str
    with_: str
    kor_name: str      # which variable name supplied each key (names only, for reporting)
    with_name: str

    def __repr__(self) -> str:  # never show the values
        return f"ServiceKeys(kor=<{self.kor_name}>, with_=<{self.with_name}>)"


def read_env_file(path: str | Path) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines. Blank lines and ``#`` comments are skipped; ``export`` and
    matching outer quotes are removed. A missing file is an empty mapping."""
    path = Path(path)
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


def load_service_keys(environ: Mapping[str, str] | None = None,
                      env_file: str | Path | None = ".env") -> ServiceKeys:
    file_values = read_env_file(env_file) if env_file is not None else {}
    process = os.environ if environ is None else environ

    def get(name: str) -> str:
        value = process.get(name, "").strip()
        return value if value else file_values.get(name, "").strip()

    shared = get(SHARED)
    kor, kor_name = (get(KOR), KOR) if get(KOR) else (shared, SHARED)
    with_, with_name = (get(WITH), WITH) if get(WITH) else (shared, SHARED)
    missing = [label for label, value in (("국문 관광정보", kor), ("무장애 여행 정보", with_)) if not value]
    if missing:
        raise MissingKeyError(f"TourAPI key not set for {', '.join(missing)}: set {SHARED}, "
                              f"or {KOR} and {WITH} (in the environment or .env)")
    return ServiceKeys(kor=kor, with_=with_, kor_name=kor_name, with_name=with_name)


def set_names(environ: Mapping[str, str] | None = None,
              env_file: str | Path | None = ".env") -> list[str]:
    """Which of the key names are set (names only, values never returned)."""
    file_values = read_env_file(env_file) if env_file is not None else {}
    process = os.environ if environ is None else environ
    return [name for name in NAMES
            if process.get(name, "").strip() or file_values.get(name, "").strip()]
