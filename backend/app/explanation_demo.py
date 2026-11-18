"""#25 demonstration: fake DB/search/travel/model, explicitly synthetic only."""
from dataclasses import replace
from app.ai.gemini import UnconfiguredProvider
from app.ai.service import AIService
from app.application.extraction import AIConditionExtractor
from app.application.profile_support import INITIAL_FIELDS, ProfileSupport
from app.constraints.chat_parser import ChatRuleParser
from app.courses.fakes import synthetic_service, synthetic_place
from app.domain.place import OpenHoursRecord
from app.explanations.fakes import SyntheticExplanationProvider
from app.explanations.generator import ExplanationGenerator
from app.main import create_app


def create_demo(*, fallback=False):
    service = synthetic_service()
    # Detail-only unknown fixture: never enters retrieval or a PASSED course.
    unknown = replace(synthetic_place('unknown-detail'), accessibility=None,
                      open_hours=OpenHoursRecord(None, None), indoor=None)
    service.repository.places[unknown.id] = unknown
    provider = UnconfiguredProvider() if fallback else SyntheticExplanationProvider()
    app = create_app(
        extractor=AIConditionExtractor(AIService(UnconfiguredProvider()), ChatRuleParser()),
        course_service=service,
        explanation_generator=ExplanationGenerator(AIService(provider), service.repository),
        profile_support=ProfileSupport(candidate_search_connected=True,
            verified_fields=frozenset(INITIAL_FIELDS), mobility_verified=True))
    app.title = 'BusanFit — 가상 DB·가상 LLM 추천 이유 검증 전용' + (' (템플릿 대체)' if fallback else '')
    return app


app = create_demo()
fallback_app = create_demo(fallback=True)
