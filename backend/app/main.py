"""Single-worker API with ephemeral sessions."""
import asyncio
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from fastapi import FastAPI

from app.api.errors import install_error_handlers
from app.api.sessions import router
from app.api.profiles import router as profile_router
from app.application.profile_support import INITIAL_FIELDS, ProfileSupport, build_profile_capabilities
from app.api.profile_models import ProfileUpdateRequest
from app.sessions.store import SessionStore
from app.application.extraction import build_extractor
from app.api.chat import router as chat_router
from app.api.courses import router as course_router
from app.api.places import router as place_router
from app.ai.service import AIService
from app.api.adjustments import router as adjustment_router
from app.application.adjustment_interpreter import AdjustmentInterpreter


def create_app(store: SessionStore | None = None, *, cleanup_interval: float = 1, extractor=None,
               profile_support: ProfileSupport | None = None, course_service=None,
               place_repository=None, explanation_generator=None, connect_real_data: bool = False,
               adjustment_interpreter=None) -> FastAPI:
    if type(connect_real_data) is not bool:
        raise ValueError('connect_real_data must be boolean')
    if connect_real_data and any(value is not None for value in (profile_support, course_service, place_repository)):
        raise ValueError('runtime connection cannot override injected course dependencies')
    sessions = store if store is not None else SessionStore()
    condition_extractor = extractor if extractor is not None else build_extractor()
    adjustment_interpreter = (adjustment_interpreter if adjustment_interpreter is not None else
        AdjustmentInterpreter(getattr(condition_extractor, 'ai', None)))

    @asynccontextmanager
    async def lifespan(app):
        async def cleanup():
            while True:
                await asyncio.sleep(cleanup_interval)
                sessions.purge_expired()
        async with AsyncExitStack() as resources:
            task = None
            try:
                opened = set()
                for component in (condition_extractor, explanation_generator, adjustment_interpreter):
                    ai = getattr(component, 'ai', None)
                    if isinstance(ai, AIService) and id(ai) not in opened:
                        await resources.enter_async_context(ai.session())
                        opened.add(id(ai))
                if connect_real_data:
                    from app.application.course_connection import prepare_runtime_connection
                    prepared = await asyncio.to_thread(prepare_runtime_connection)
                    capabilities = build_profile_capabilities(ProfileSupport(True, frozenset(INITIAL_FIELDS), True, True))
                    # Publish support only after DB, exclusions, weights and provider validate.
                    app.state.course_connection = prepared
                    app.state.course_service = prepared.service
                    app.state.place_repository = prepared.repository
                    app.state.capabilities = capabilities
                task = asyncio.create_task(cleanup())
                yield
            finally:
                if task is not None:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
                sessions.clear()
                if connect_real_data:
                    app.state.course_connection = None
                    app.state.course_service = None
                    app.state.place_repository = None
                    app.state.capabilities = build_profile_capabilities()

    app = FastAPI(
        title="BusanFit — 세션·조건 API",
        version="0.0.5",
        description=("세션 생성·종료·조건 카드 전체 교체를 지원합니다. "
                     + ("조건 채팅·규칙 대체 처리를 지원합니다. " if condition_extractor is not None else
                        "조건 채팅을 사용할 수 없습니다. ")
                     + "일반 서버는 설정된 DB로 4개 권역(해운대·서면·광안리·남포)·도보 코스와 장소 상세를 지원합니다. 실제 지원 범위는 세션 응답의 capabilities를 따릅니다. Gemini는 환경변수 설정 시 추출에 연결되며, 추천 이유는 설명 생성기 주입 시 연결됩니다."),
        debug=False,
        lifespan=lifespan,
    )
    app.state.sessions = sessions
    app.state.extractor = condition_extractor
    app.state.course_service = course_service
    app.state.course_connection = None
    app.state.place_repository = (place_repository if place_repository is not None else
                                  (course_service.repository if course_service is not None else None))
    app.state.explanation_generator = explanation_generator
    app.state.adjustment_interpreter = adjustment_interpreter
    app.state.capabilities = build_profile_capabilities(profile_support)
    install_error_handlers(app)
    app.include_router(router)
    app.include_router(profile_router)
    app.include_router(course_router)
    app.include_router(adjustment_router)
    app.include_router(place_router)
    if app.state.extractor is not None:
        app.include_router(chat_router)
    generated_openapi = app.openapi

    def openapi_with_nullable_example():
        schema = generated_openapi()
        # FastAPI's OpenAPI serialization removes None from nested examples.
        # Restore this implemented route's example, without replacing its schema.
        examples = ProfileUpdateRequest.model_json_schema()['examples']
        schema['components']['schemas']['ProfileUpdateRequest']['examples'] = examples
        schema['paths']['/api/sessions/{sessionId}/profile']['put']['requestBody']['content']['application/json']['example'] = examples[0]
        return schema

    app.openapi = openapi_with_nullable_example
    return app


def create_runtime_app() -> FastAPI:
    """Start with required BUSANFIT_DB_PATH; no empty DB or synthetic fallback."""
    return create_app(connect_real_data=True)


app = create_runtime_app()
