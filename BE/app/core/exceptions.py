import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.utils.response import error_response

logger = logging.getLogger(__name__)

HTTP_ERROR_CODES = {
    400: ("BAD_REQUEST", "잘못된 요청입니다."),
    401: ("UNAUTHORIZED", "인증이 필요합니다."),
    403: ("FORBIDDEN", "접근 권한이 없습니다."),
    404: ("NOT_FOUND", "요청한 리소스를 찾을 수 없습니다."),
    405: ("METHOD_NOT_ALLOWED", "허용되지 않은 메서드입니다."),
}


def add_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(_: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response(exc.code, exc.message),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException):
        code, message = HTTP_ERROR_CODES.get(exc.status_code, ("HTTP_ERROR", str(exc.detail)))
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response(code, message),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError):
        fields = [".".join(str(p) for p in err["loc"][1:]) for err in exc.errors()]
        fields = [f for f in fields if f]
        message = "요청 값이 올바르지 않습니다."
        if fields:
            message += f" ({', '.join(fields)})"
        return JSONResponse(
            status_code=422,
            content=error_response("VALIDATION_ERROR", message),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception: %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=error_response("INTERNAL_SERVER_ERROR", "서버 내부 오류가 발생했습니다."),
        )


class AppException(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)
