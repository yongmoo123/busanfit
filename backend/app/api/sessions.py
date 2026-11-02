from uuid import uuid4
from fastapi import APIRouter, Request, Response

from app.api.session_models import SessionRequest, SessionResponse

router = APIRouter()


@router.post('/api/sessions', status_code=201, response_model=SessionResponse)
def create_session(body: SessionRequest, request: Request, response: Response):
    # ASGI peer only: do not trust a caller-provided X-Forwarded-For header.
    client = request.client.host if request.client else 'unknown'
    session = request.app.state.sessions.create(client)
    response.headers['Cache-Control'] = 'no-store'
    return SessionResponse(
        sessionId=session.session_id, expiresAt=session.expires_at, requestId=uuid4(),
        capabilities=request.app.state.capabilities,
    )
