"""Explicit synthetic scenario server. Not a production capability declaration."""
from app.ai.gemini import UnconfiguredProvider
from app.ai.service import AIService
from app.application.extraction import AIConditionExtractor
from app.application.profile_support import INITIAL_FIELDS, ProfileSupport
from app.constraints.chat_parser import ChatRuleParser
from app.main import create_app

app = create_app(extractor=AIConditionExtractor(AIService(UnconfiguredProvider()), ChatRuleParser()),
                 profile_support=ProfileSupport(candidate_search_connected=True,
                     verified_fields=frozenset(INITIAL_FIELDS), mobility_verified=True))
app.title = 'BusanFit — 가상 시나리오 검증 전용'
