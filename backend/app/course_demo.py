"""Synthetic #22 and travel connections for the real #23 pipeline. No real data."""
from app.ai.gemini import UnconfiguredProvider
from app.ai.service import AIService
from app.application.extraction import AIConditionExtractor
from app.application.profile_support import INITIAL_FIELDS, ProfileSupport
from app.constraints.chat_parser import ChatRuleParser
from app.courses.fakes import synthetic_service
from app.main import create_app

app = create_app(extractor=AIConditionExtractor(AIService(UnconfiguredProvider()), ChatRuleParser()),
                 course_service=synthetic_service(),
                 profile_support=ProfileSupport(candidate_search_connected=True,
                     verified_fields=frozenset(INITIAL_FIELDS), mobility_verified=True))
app.title = 'BusanFit — 가상 코스 API 검증 전용'
