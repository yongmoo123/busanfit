"""Explicit synthetic ports for #23 tests/demo. No distance formula or SQL."""
from copy import deepcopy

from app.application.course_service import CourseService
from app.data.repository import RepositoryError
from app.domain.course import RetrievalResult, TravelEstimate
from app.domain.place import AccessibilityRecord, DataSourceRecord, OpenHoursRecord, PlaceCandidate, PlaceRecord, WEEKDAY_KEYS


class FakeRepository:
    def __init__(self, places, sources=None):
        self.places = {place.id: deepcopy(place) for place in places}
        self.sources = {source.id: source for source in (sources if sources is not None else [synthetic_source()])}

    def get_place(self, place_id):
        return deepcopy(self.places.get(place_id))

    def find_within_radius(self, *args, **kwargs):
        raise NotImplementedError('Use FakeRetriever; the course engine must not perform spatial queries.')

    def existing_place_ids(self, place_ids):
        return frozenset(place_id for place_id in place_ids if place_id in self.places)

    def get_sources(self, source_ids):
        unique = list(dict.fromkeys(source_ids))
        if any(source_id not in self.sources for source_id in unique):
            raise RepositoryError('missing source')
        return [self.sources[source_id] for source_id in unique]


class FakeRetriever:
    def __init__(self, places, *, distances=None, unknown_ids=(), unknown_fields=()):
        self.places = tuple(places)
        self.distances = distances or {}
        self.unknown_ids, self.unknown_fields = frozenset(unknown_ids), frozenset(unknown_fields)
        self.calls = 0

    def retrieve(self, profile):
        self.calls += 1
        return RetrievalResult(tuple(PlaceCandidate(place, self.distances.get(place.id, 100.0)) for place in self.places),
                               self.unknown_ids, self.unknown_fields)


class FakeTravel:
    def __init__(self, minutes=5, *, matrix=None):
        self.minutes, self.matrix = minutes, matrix or {}
        self.calls = 0
        self.injury_flags = []

    def estimate(self, origin, destination, *, injury):
        self.calls += 1
        self.injury_flags.append(injury)
        minutes = self.matrix.get((origin.id, destination.id), self.minutes)
        return TravelEstimate(minutes) if minutes is not None else None


def synthetic_source():
    return DataSourceRecord('synthetic-source', 'synthetic', '[가상] 제공기관', '[가상] 코스 테스트 데이터',
                            None, 'https://example.invalid/synthetic', None, '2026-11-13T10:00:00+09:00')


def synthetic_place(identifier, *, category='CAFE', wheelchair=True, stroller=True, hours=None, indoor=True):
    if hours is None:
        hours = {day: [{'open': '09:00', 'close': '20:00'}] for day in WEEKDAY_KEYS}
    return PlaceRecord('synthetic', str(identifier), f'[가상] 장소 {identifier}', category, 'HAEUNDAE',
                       '[가상] 해운대 테스트 주소', 35.16, 129.16, indoor,
                       OpenHoursRecord(hours, '[가상] 정규화 운영시간'), None, None, None, 60, None,
                       'synthetic-source', '2026-11-13T10:00:00+09:00',
                       AccessibilityRecord('VERIFIED', wheelchair, stroller, None, None, None, 'synthetic-source'))


def synthetic_service():
    places = [synthetic_place(index) for index in range(1, 5)]
    return CourseService(FakeRetriever(places), FakeTravel(), FakeRepository(places))
