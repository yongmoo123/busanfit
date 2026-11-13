"""API place.id format (DEC-017): ``"{data_sources.code}:{places.source_place_id}"``.

DEC-017 left the format to the data owner. The DB integer ``places.id`` changes when the DB file
is rebuilt, so the API ID is built from values that survive a reload: the fixed source code the
loader writes (e.g. ``tourapi-kor``, ``tourapi-barrierfree``) and the original place ID.

Allowed characters (same rules as the CHECKs in schema.sql):
- source code: ``[a-z0-9-]+``
- original place ID: ``[A-Za-z0-9_-]{1,64}`` — ASCII letters, digits, ``_`` and ``-`` only.
  Anything else (``? # % /``, space, ``.``, non-ASCII, ...) is rejected, never rewritten.

Every character in a place ID is therefore an RFC 3986 "unreserved" character or the separator
``:``, which may appear as-is in a path segment. The ID can be put into ``/api/places/{placeId}``
without encoding and comes back unchanged: no ``?``/``#`` to cut it, no ``%`` to be decoded into
something else, no ``/`` to split the path. The code never contains ``:``, so the first ``:``
always splits the ID.
"""
import re

SEPARATOR = ":"
SOURCE_CODE_PATTERN = re.compile(r"[a-z0-9-]+")
SOURCE_PLACE_ID_MAX_LENGTH = 64
SOURCE_PLACE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,%d}" % SOURCE_PLACE_ID_MAX_LENGTH)


def validate_source_code(code: str) -> str:
    if not isinstance(code, str) or not SOURCE_CODE_PATTERN.fullmatch(code):
        raise ValueError(f"source code must match [a-z0-9-]+: {code!r}")
    return code


def validate_source_place_id(source_place_id: str) -> str:
    if not isinstance(source_place_id, str) or not SOURCE_PLACE_ID_PATTERN.fullmatch(
            source_place_id):
        raise ValueError(f"source_place_id must be 1-{SOURCE_PLACE_ID_MAX_LENGTH} characters of "
                         f"[A-Za-z0-9_-]: {source_place_id!r}")
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
