"""API place.id format (DEC-017): ``"{data_sources.code}:{places.source_place_id}"``.

DEC-017 left the format to the data owner. The DB integer ``places.id`` changes when the DB file
is rebuilt, so the API ID is built from values that survive a reload: the fixed source code the
loader writes (e.g. ``tourapi-kor``, ``tourapi-barrierfree``) and the original place ID.

The code allows only ``[a-z0-9-]`` (same rule as the CHECK in schema.sql), so it never contains
the separator and the first ``:`` always splits the ID. ``:`` is allowed as-is in a URL path
segment (RFC 3986 pchar), so ``/api/places/tourapi-kor:12345`` needs no escaping. ``/`` is not
allowed in the original ID because it would split the path.
"""
import re

SEPARATOR = ":"
SOURCE_CODE_PATTERN = re.compile(r"[a-z0-9-]+")


def validate_source_code(code: str) -> str:
    if not isinstance(code, str) or not SOURCE_CODE_PATTERN.fullmatch(code):
        raise ValueError(f"source code must match [a-z0-9-]+: {code!r}")
    return code


def validate_source_place_id(source_place_id: str) -> str:
    if not isinstance(source_place_id, str) or not source_place_id or "/" in source_place_id:
        raise ValueError(f"source_place_id must be a non-empty string without '/': "
                         f"{source_place_id!r}")
    return source_place_id


def make_place_id(source_code: str, source_place_id: str) -> str:
    return (f"{validate_source_code(source_code)}{SEPARATOR}"
            f"{validate_source_place_id(source_place_id)}")


def parse_place_id(place_id: str) -> tuple[str, str]:
    """Split an API place.id into (source code, source_place_id). Raises ValueError if malformed."""
    if not isinstance(place_id, str) or SEPARATOR not in place_id:
        raise ValueError(f"malformed place id: {place_id!r}")
    code, source_place_id = place_id.split(SEPARATOR, 1)
    return validate_source_code(code), validate_source_place_id(source_place_id)
