"""Single-worker API with ephemeral sessions."""
import asyncio
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI

from app.api.errors import install_error_handlers
from app.api.sessions import router
from app.api.profiles import router as profile_router
from app.api.session_models import Capabilities
from app.api.profile_models import ProfileUpdateRequest
from app.sessions.store import SessionStore


def create_app(store: SessionStore | None = None, *, cleanup_interval: float = 1) -> FastAPI:
    sessions = store if store is not None else SessionStore()

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
        title="BusanFit — 세션·조건 카드 API",
        version="0.0.4",
        description="세션 생성·종료·조건 카드 전체 교체를 지원합니다. 추천 엔진 미연결로 활성 조건은 현재 거절합니다. LLM·코스·장소 API는 미구현입니다.",
        debug=False,
        lifespan=lifespan,
    )
    app.state.sessions = sessions
    app.state.capabilities = Capabilities(
        supportedAreas=[], supportedTransports=[], supportedProfileFields=[],
        supportsUnknownAccessibilityInclusion=False,
        supportsCourseAdjustment=False, supportsWeather=False,
    )
    install_error_handlers(app)
    app.include_router(router)
    app.include_router(profile_router)
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
