"""Single-worker API with ephemeral sessions."""
import asyncio
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI

from app.api.errors import install_error_handlers
from app.api.sessions import router
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
        title="BusanFit — 세션 API",
        version="0.0.2",
        description="세션 생성만 지원합니다. 조건 분석·코스·장소 API는 미구현입니다.",
        debug=False,
        lifespan=lifespan,
    )
    app.state.sessions = sessions
    install_error_handlers(app)
    app.include_router(router)
    return app


app = create_app()
