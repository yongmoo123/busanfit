"""Runnable skeleton. Business endpoints are deliberately not registered yet."""
from fastapi import FastAPI

from app.api.errors import install_error_handlers


def create_app() -> FastAPI:
    app = FastAPI(
        title="BusanFit — 개발 골격",
        version="0.0.1",
        description="실제 기능 API는 아직 구현되지 않았습니다. 계약 초안은 contracts/openapi.json을 확인하세요.",
        debug=False,
    )
    install_error_handlers(app)
    return app


app = create_app()
