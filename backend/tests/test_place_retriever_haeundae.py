"""#22 PlaceRetriever on the real 해운대 DB (data/haeundae_sample.sqlite3).

The DB file is not committed (DEC-005), so CI skips this module. Opened read-only.
Counts are printed for the report (``pytest -s``) and not asserted: they change when the
data, the 무장애 표현 목록 (DEC-026) or the 사후면세점 기준 (DEC-023 ④) change.
"""
from pathlib import Path
import sqlite3

import pytest

from app.courses.validator import candidate_violations
from app.data.sqlite_repository import SqlitePlaceRepository
from app.domain.course import CourseSettings
from app.retrieval import PlaceRetriever, load_retrieval_settings
from test_place_retriever import profile

DB = Path(__file__).resolve().parents[2] / 'data/haeundae_sample.sqlite3'
pytestmark = pytest.mark.skipif(not DB.exists(), reason='real 해운대 DB is not available (not committed, DEC-005)')

# Saturday afternoon, KST
WINDOW = {'start': '2026-11-21T13:00:00+09:00', 'end': '2026-11-21T18:00:00+09:00'}
SCENARIOS = {'general': [], 'wheelchair': ['WHEELCHAIR'], 'stroller': ['STROLLER'], 'injury': ['INJURY']}


@pytest.fixture(scope='module')
def repository():
    connection = sqlite3.connect(f'{DB.resolve().as_uri()}?mode=ro', uri=True)
    yield SqlitePlaceRepository(connection)
    connection.close()


@pytest.mark.parametrize('name', SCENARIOS)
def test_real_db_scenario(repository, name, monkeypatch):
    monkeypatch.delenv('BUSANFIT_WALK_RADIUS_M', raising=False)
    settings = load_retrieval_settings()
    prof = profile(SCENARIOS[name], **WINDOW)
    result = PlaceRetriever(repository, settings).retrieve(prof)
    assert len(result.candidates) <= 20
    for candidate in result.candidates:
        assert candidate_violations(candidate, prof, CourseSettings()) == ()
        assert candidate.place.id not in settings.excluded_place_ids
    print(f'\n[{name}] candidates={len(result.candidates)} '
          f'excludedUnknown={len(result.excluded_unknown_ids)} fields={sorted(result.excluded_unknown_fields)}')
