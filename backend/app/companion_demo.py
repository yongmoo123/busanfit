"""Explicit synthetic #27 proposal/baseline apps, not ordinary activation."""
from app.ai.gemini import UnconfiguredProvider
from app.ai.service import AIService
from app.application.course_service import CourseService
from app.application.extraction import AIConditionExtractor
from app.application.profile_support import INITIAL_FIELDS, ProfileSupport
from app.constraints.chat_parser import ChatRuleParser
from app.courses.companion_scoring import ProposalCompanionScorer, load_companion_proposal
from app.courses.fakes import FakeRepository, FakeRetriever, FakeTravel, synthetic_place
from app.courses.scheduler import CourseScheduler
from app.domain.place import CONTRACT_CATEGORIES
from app.explanations.fakes import SyntheticExplanationProvider
from app.explanations.generator import ExplanationGenerator
from app.main import create_app


def create_demo(*, proposal=False):
    # IDs deliberately do not encode the preference order. Durations, hours,
    # distances and travel are equal, isolating score effects in a 135-min window.
    categories = ('OTHER', 'CAFE', 'EXHIBITION', 'ATTRACTION', 'PARK', 'FOOD', 'SHOPPING')
    assert set(categories) == set(CONTRACT_CATEGORIES)
    places = [synthetic_place(f'p{index:02d}', category=category) for index, category in enumerate(categories, 1)]
    repo = FakeRepository(places)
    scheduler = CourseScheduler(scorer=ProposalCompanionScorer(load_companion_proposal())) if proposal else CourseScheduler()
    service = CourseService(FakeRetriever(places), FakeTravel(), repo, scheduler=scheduler)
    app = create_app(course_service=service,
        extractor=AIConditionExtractor(AIService(UnconfiguredProvider()), ChatRuleParser()),
        explanation_generator=ExplanationGenerator(AIService(SyntheticExplanationProvider()), repo),
        profile_support=ProfileSupport(True, frozenset(INITIAL_FIELDS), True))
    app.title = 'BusanFit — 가상 동행 가중치 ' + ('미승인 제안 검증 전용' if proposal else '기존 점수 기준선')
    return app


app = create_demo(proposal=True)
baseline_app = create_demo()
