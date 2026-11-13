"""Single-worker API with ephemeral sessions."""
import asyncio
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI

from app.api.errors import install_error_handlers
from app.api.sessions import router
from app.api.profiles import router as profile_router
from app.application.profile_support import ProfileSupport, build_profile_capabilities
from app.api.profile_models import ProfileUpdateRequest
from app.sessions.store import SessionStore
from app.application.extraction import build_extractor
from app.api.chat import router as chat_router


def create_app(store: SessionStore | None = None, *, cleanup_interval: float = 1, extractor=None,
               profile_support: ProfileSupport | None = None) -> FastAPI:
    sessions = store if store is not None else SessionStore()
    condition_extractor = extractor if extractor is not None else build_extractor()

    @asynccontextmanager
    async def lifespan(app):
        async def cleanup():
            while True:
                await asyncio.sleep(cleanup_interval)
                sessions.purge_expired()
        task = asyncio.create_task(cleanup())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            sessions.clear()

    app = FastAPI(
        title="BusanFit — 세션·조건 API",
        version="0.0.4",
        description=("세션 생성·조건 카드 전체 교체를 지원합니다. "
                     + ("조건 채팅·규칙 대체 처리를 지원합니다. " if condition_extractor is not None else
                        "조건 채팅을 사용할 수 없습니다. ")
                     + "Gemini는 환경변수 설정 시 추출에 연결됩니다. #21·#22 활성화 전 일반 capabilities는 비어 있습니다. 코스·장소 API는 미완료입니다."),
        debug=False,
        lifespan=lifespan,
    )
    app.state.sessions = sessions
    app.state.extractor = condition_extractor
    app.state.capabilities = build_profile_capabilities(profile_support)
    install_error_handlers(app)
    app.include_router(router)
    app.include_router(profile_router)
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


app = create_app()
