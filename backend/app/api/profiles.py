from uuid import UUID, uuid4
from fastapi import APIRouter, Request, Response
from app.api.profile_models import ProfileResponse, ProfileUpdateRequest
from app.constraints.profile import validate_profile
from app.application.condition_policy import replace_card

router = APIRouter()


@router.put('/api/sessions/{sessionId}/profile', response_model=ProfileResponse)
def replace_profile(sessionId: UUID, body: ProfileUpdateRequest, request: Request, response: Response):
    store = request.app.state.sessions
    current = store.begin(str(sessionId), body.expectedProfileRevision)
    policy = (replace_card(current, body.profile, request.app.state.capabilities)
              if request.app.state.extractor is not None else None)
    questions = (policy.questions if policy else
                 validate_profile(body.profile, current.profile, request.app.state.capabilities))
    profile = policy.profile if policy else body.profile
    # Construct/validate the response before committing any state.
    result = ProfileResponse(
        status='NEEDS_INPUT' if questions else 'READY', profile=profile,
        profileRevision=current.revision + 1, questions=questions, warnings=policy.warnings if policy else [],
        sessionExpiresAt=current.expires_at, requestId=uuid4(),
    )
    saved = store.commit_profile(str(sessionId), body.expectedProfileRevision,
                                 profile=profile.model_dump(mode='json'), history=current.history,
                                 pending_fields=policy.pending if policy else None,
                                 companion_hints=policy.hints if policy else None)
    result.sessionExpiresAt = saved.expires_at
    response.headers['Cache-Control'] = 'no-store'
    return result
