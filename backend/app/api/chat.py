"""Contract-shaped condition chat; no raw messages retained in session history."""
from typing import Annotated
from uuid import UUID, uuid4
from pydantic import Field, StrictStr
from fastapi import APIRouter, Request, Response
from app.api.profile_models import NonnegativeInt, ProfileResponse
from app.api.session_models import ContractModel
from app.api.errors import error_response
from app.application.condition_policy import analyze_chat


class ChatRequest(ContractModel):
    sessionId: UUID
    message: Annotated[StrictStr, Field(min_length=1, max_length=1000)]
    expectedProfileRevision: NonnegativeInt


class ChatResponse(ProfileResponse):
    reply: str


router = APIRouter()


@router.post('/api/chat', response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request, response: Response):
    if not body.message.strip():
        return error_response(422, 'INVALID_REQUEST', '요청 형식을 확인해 주세요.')
    store = request.app.state.sessions
    sid, revision = str(body.sessionId), body.expectedProfileRevision
    current = store.begin(sid, revision)
    analysis = await request.app.state.extractor.extract(body.message)
    # Recheck slow results before returning503; commit rechecks atomically too.
    store.check_current(sid, revision)
    result = analyze_chat(current, analysis, request.app.state.capabilities)
    if result.unavailable:
        return error_response(503, 'AI_UNAVAILABLE',
                              '조건을 확인하지 못했어요. 조건 카드에 직접 입력해 주세요.', True)
    reply = '조건 카드에서 확인할 항목을 확인해 주세요.' if result.questions else '조건을 확인해 주세요.'
    payload = ChatResponse(
        status='NEEDS_INPUT' if result.questions or result.pending else 'READY',
        reply=reply, profile=result.profile, profileRevision=revision + 1,
        questions=result.questions, warnings=result.warnings,
        sessionExpiresAt=current.expires_at, requestId=uuid4(),
    )
    saved = store.commit_profile(sid, revision, profile=result.profile.model_dump(mode='json'),
                                 history=current.history, pending_fields=result.pending,
                                 companion_hints=result.hints)
    payload.sessionExpiresAt = saved.expires_at
    response.headers['Cache-Control'] = 'no-store'
    return payload
