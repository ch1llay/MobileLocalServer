from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

from app import logger
from app.config import get_settings
from app.routers import api_upload, web


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        logger.debug("%s %s", request.method, request.url.path)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    upload_dir = settings.get_upload_dir_resolved()
    upload_dir.mkdir(parents=True, exist_ok=True)
    codes_path = settings.codes_file.resolve()
    codes_path.parent.mkdir(parents=True, exist_ok=True)
    if not codes_path.exists():
        codes_path.write_text("[]", encoding="utf-8")
    settings_path = codes_path.parent / "settings.json"
    if not settings_path.exists():
        settings_path.write_text('{"parallel_upload": false}', encoding="utf-8")
    yield
    # shutdown: nothing to clean up


def create_app() -> FastAPI:
    app = FastAPI(title="Mobile Local File Server", lifespan=lifespan)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.include_router(web.router, tags=["web"])
    app.include_router(api_upload.router, prefix="/api", tags=["api"])
    return app


app = create_app()
