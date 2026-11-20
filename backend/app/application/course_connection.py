"""Prepare #22 -> #23 dependencies without starting or activating a server.

COMP-06 remains the data owner's implementation. Never substitute FakeTravel.
"""
from dataclasses import dataclass, replace
from pathlib import Path

from app.application.course_service import CourseService
from app.application.sqlite_adapter import ConnectionPerCallRepository
from app.courses.companion_scoring import ProposalCompanionScorer, load_companion_proposal
from app.courses.scheduler import CourseScheduler
from app.domain.course import CourseSettings


class CourseConnectionError(ValueError):
    """A required implementation or input is unavailable; not an empty course."""


@dataclass(frozen=True)
class PreparedCourseConnection:
    service: CourseService
    repository: ConnectionPerCallRepository
    retrieval_settings: object
    settings: CourseSettings
    weights_version: str


def prepare_course_connection(db_path, *, travel_provider, retrieval_settings=None, weights_path=None):
    """Dependency construction only. Does not claim real-data verification.

    Explicit settings are for controlled tests. Otherwise #65's mandatory
    exclusion loader is used. Search radius is passed to scheduler/validator.
    """
    if not callable(getattr(travel_provider, 'estimate', None)):
        raise CourseConnectionError('COMP-06 TravelTimeProvider.estimate is required')
    path = Path(db_path).resolve()
    if not path.is_file():
        raise CourseConnectionError('an existing SQLite file is required')
    try:
        from app.retrieval.retriever import PlaceRetriever
        from app.retrieval.settings import load_retrieval_settings
    except ModuleNotFoundError as error:
        if error.name not in ('app.retrieval', 'app.retrieval.retriever', 'app.retrieval.settings'):
            raise
        raise CourseConnectionError('PR #65 retrieval implementation is required') from None
    retrieval_settings = retrieval_settings if retrieval_settings is not None else load_retrieval_settings()
    settings = replace(CourseSettings(), radius_meters=retrieval_settings.radius_m,
                       max_candidates=retrieval_settings.max_candidates)
    weights = load_companion_proposal(weights_path, approved_only=True)
    repository = ConnectionPerCallRepository(path, read_only=True)
    center = retrieval_settings.area_centers.get('HAEUNDAE')
    if center is None:
        raise CourseConnectionError('HAEUNDAE center is required')
    # Fail during preparation for a corrupt/missing-schema DB; no fake fallback.
    repository.find_within_radius(*center, settings.radius_meters, area='HAEUNDAE', limit=1)
    service = CourseService(PlaceRetriever(repository, retrieval_settings), travel_provider,
        repository, settings=settings,
        scheduler=CourseScheduler(settings, scorer=ProposalCompanionScorer(weights)))
    return PreparedCourseConnection(service, repository, retrieval_settings, settings, weights.version)
