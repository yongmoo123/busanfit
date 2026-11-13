"""Explicit synthetic scenario server. Not a production capability declaration."""
from app.ai.gemini import UnconfiguredProvider
from app.ai.service import AIService
from app.application.extraction import AIConditionExtractor, blank_profile
from app.constraints.chat_parser import ChatRuleParser
from app.main import create_app

app = create_app(extractor=AIConditionExtractor(AIService(UnconfiguredProvider()), ChatRuleParser()))
app.title = 'BusanFit — 가상 시나리오 검증 전용'
app.state.capabilities.supportedAreas = ['HAEUNDAE']
app.state.capabilities.supportedTransports = ['WALK']
app.state.capabilities.supportedProfileFields = list(blank_profile())[:-1]
