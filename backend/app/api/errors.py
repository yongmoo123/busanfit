"""Return contract-shaped errors without reflecting input or exception text."""
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from app.sessions.store import SessionError


def error_response(status: int, code: str, message: str, retryable: bool = False):
    return JSONResponse(
        status_code=status,
        headers={"Cache-Control": "no-store"},
        content={
            "error": {"code": code, "message": message, "retryable": retryable, "details": []},
            "requestId": str(uuid4()),
        },
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(SessionError)
    async def session_error(request: Request, exc: SessionError):
        messages = {
            'SESSION_EXPIRED': '세션이 없거나 만료되었습니다. 새 세션을 시작해 주세요.',
            'REVISION_CONFLICT': '조건이 변경되었습니다. 최신 조건을 확인해 주세요.',
            'RATE_LIMITED': '요청이 많습니다. 잠시 후 다시 시도해 주세요.',
        }
        response = error_response(exc.status, exc.code, messages[exc.code], exc.status == 429)
        if exc.retry_after is not None:
            response.headers['Retry-After'] = str(exc.retry_after)
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        malformed = any(error["type"] == "json_invalid" for error in exc.errors())
        return error_response(400 if malformed else 422, "INVALID_REQUEST", "요청 형식을 확인해 주세요.")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        # Specific business errors will be added with their owning API.
        code = "NOT_FOUND" if exc.status_code == 404 else "INVALID_REQUEST"
        return error_response(exc.status_code, code, "요청한 경로 또는 요청 방법을 확인해 주세요.")

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        return error_response(500, "INTERNAL_ERROR", "요청을 처리하지 못했습니다.", True)
