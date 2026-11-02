from uuid import UUID, uuid4
from fastapi import APIRouter, Request, Response
from app.api.profile_models import ProfileResponse, ProfileUpdateRequest
from app.constraints.profile import validate_profile

router = APIRouter()


@router.put('/api/sessions/{sessionId}/profile', response_model=ProfileResponse)
def replace_profile(sessionId: UUID, body: ProfileUpdateRequest, request: Request, response: Response):
    store = request.app.state.sessions
    current = store.begin(str(sessionId), body.expectedProfileRevision)
    questions = validate_profile(body.profile, current.profile, request.app.state.capabilities)
    # Construct/validate the response before committing any state.
    result = ProfileResponse(
        status='NEEDS_INPUT' if questions else 'READY', profile=body.profile,
        profileRevision=current.revision + 1, questions=questions, warnings=[],
        sessionExpiresAt=current.expires_at, requestId=uuid4(),
    )
    saved = store.commit_profile(str(sessionId), body.expectedProfileRevision,
                                 profile=body.profile.model_dump(mode='json'), history=current.history)
    result.sessionExpiresAt = saved.expires_at
    response.headers['Cache-Control'] = 'no-store'
    return result
