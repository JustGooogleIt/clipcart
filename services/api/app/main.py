"""ClipCart API entrypoint: ``uvicorn app.main:app`` from services/api."""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from app.config import Settings, load_settings
from app.jobs.search import recover_on_startup
from app.media.errors import MediaError
from app.routes.api import router
from app.routes.demo_orders import router as demo_orders_router
from app.routes.research import router as research_router
from app.routes.style import router as style_router
from app.sessions.service import ApiProblem
from app.state import build_state

log = logging.getLogger("clipcart")


def _err(status: int, code: str, message: str, retryable: bool = False) -> JSONResponse:
    rid = "req_" + uuid.uuid4().hex[:12]
    return JSONResponse(
        status_code=status,
        content={"code": code, "message": message, "retryable": retryable, "requestId": rid},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="ClipCart API", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    state = build_state(settings)
    app.state.clipcart = state
    recovery = recover_on_startup(state)
    if recovery["failed"] or recovery["resumed"]:
        log.warning("job recovery: %s", recovery)

    @app.exception_handler(ApiProblem)
    async def _problem(_: Request, exc: ApiProblem):
        return _err(exc.status, exc.code, exc.message, exc.retryable)

    @app.exception_handler(MediaError)
    async def _media(_: Request, exc: MediaError):
        return _err(exc.http_status, exc.code, exc.message, exc.retryable)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
        return _err(422, "invalid_request", f"{loc}: {first.get('msg', 'invalid')}".strip(": "))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")
        return _err(500, "internal_error", "Something went wrong on our side", True)

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        return resp

    app.include_router(router)
    app.include_router(style_router)
    app.include_router(research_router)
    app.include_router(demo_orders_router)

    dist = settings.web_dist
    if dist.is_dir():

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            target = (dist / path).resolve()
            if path and target.is_file() and dist.resolve() in target.parents:
                return FileResponse(target)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
