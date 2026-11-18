"""POST /api/courses; serialized output and session recheck before renewing TTL."""
from uuid import uuid4

from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

from app.api.course_models import CourseInsufficient, CourseRequest, CourseResponse, CourseSuccess
from app.api.errors import error_response
from app.api.profile_models import Profile
from app.constraints.profile import ProfileError

router = APIRouter()


@router.post('/api/courses', response_model=CourseResponse)
async def generate_course(body: CourseRequest, request: Request, response: Response):
    store = request.app.state.sessions
    sid, revision = str(body.sessionId), body.profileRevision
    current = store.begin_course(sid, revision)
    service = request.app.state.course_service
    if service is None:
        return error_response(500, 'INTERNAL_ERROR', '코스 생성 연결이 준비되지 않았어요.', True)
    try:
        profile = Profile.model_validate(current.profile)
        result = await run_in_threadpool(service.generate, profile, revision, request.app.state.capabilities)
        store.check_current(sid, revision)
        payload = dict(course=result.course, suggestions=[], warnings=result.warnings,
                       excludedUnknown=result.excluded_unknown, sessionExpiresAt=current.expires_at,
                       requestId=uuid4())
        if result.course is None:
            model = CourseInsufficient(status='INSUFFICIENT_PLACES', **payload)
        else:
            model = CourseSuccess(status='SUCCESS', **payload)
    except ProfileError:
        store.check_current(sid, revision)
        raise
    except Exception:
        # Dependency exception strings can contain storage details. Never log or
        # rethrow them through server-error middleware. Stale/expired wins.
        store.check_current(sid, revision)
        return error_response(500, 'INTERNAL_ERROR', '코스를 구성하지 못했어요. 잠시 후 다시 시도해 주세요.', True)
    saved = store.finish_read(sid, revision)
    model.sessionExpiresAt = saved.expires_at
    response.headers['Cache-Control'] = 'no-store'
    return model
