"""FR-015 API: immutable course versions, optimistic commit, no profile mutation."""
from uuid import UUID, uuid4
from fastapi import APIRouter, Request, Response
from starlette.concurrency import run_in_threadpool

from app.api.adjustment_models import AdjustmentRequest, AdjustmentResponse
from app.api.course_models import Course
from app.api.errors import error_response
from app.api.profile_models import Profile
from app.application.course_adjustment import CourseAdjustmentService

router = APIRouter()


@router.post('/api/courses/{courseId}/adjust', response_model=AdjustmentResponse)
async def adjust_course(courseId: UUID, body: AdjustmentRequest, request: Request, response: Response):
    store = request.app.state.sessions
    sid, revision = str(body.sessionId), body.expectedProfileRevision
    current = store.begin_course(sid, revision)
    if not request.app.state.capabilities.supportsCourseAdjustment:
        return error_response(422, 'UNSUPPORTED_CONSTRAINT', '코스 수정 기능은 아직 활성화되지 않았어요.')
    current = store.check_course(sid, revision, current.course_epoch, str(courseId))
    service = request.app.state.course_service
    if service is None:
        return error_response(500, 'INTERNAL_ERROR', '코스 연결이 준비되지 않았어요.', True)
    if not body.message.strip():
        return error_response(422, 'INVALID_REQUEST', '수정할 내용을 입력해 주세요.')
    try:
        old = Course.model_validate(current.last_course)
        profile = Profile.model_validate(current.profile)
        interpreted = await request.app.state.adjustment_interpreter.interpret(
            body.message, old, profile, current.adjustment_context)
        store.check_course(sid, revision, current.course_epoch, str(courseId))
        outcome = await run_in_threadpool(CourseAdjustmentService(service).adjust, old, profile,
            revision, request.app.state.capabilities, interpreted.intent, current.course_metadata)
        store.check_course(sid, revision, current.course_epoch, str(courseId))
        if interpreted.fallback:
            outcome.metadata['warnings'].append({'code': 'AI_FALLBACK',
                'message': '수정 요청을 단순 규칙으로 확인했어요. 불명확한 내용은 다시 입력해 주세요.', 'placeIds': []})
        model = AdjustmentResponse(status=outcome.status, course=outcome.course, profileRevision=revision,
            changes=outcome.changes, questions=outcome.questions, sessionExpiresAt=current.expires_at,
            requestId=uuid4(), **outcome.metadata)
        wire = model.model_dump(mode='json')
    except Exception:
        store.check_course(sid, revision, current.course_epoch, str(courseId))
        return error_response(500, 'INTERNAL_ERROR', '코스를 수정하지 못했어요. 기존 코스를 유지합니다.', True)
    saved = store.commit_course(sid, revision, current.course_epoch, course=wire['course'],
        context=outcome.context, metadata={key: wire[key] for key in ('warnings', 'suggestions', 'excludedUnknown')})
    model.sessionExpiresAt = saved.expires_at
    response.headers['Cache-Control'] = 'no-store'
    return model
