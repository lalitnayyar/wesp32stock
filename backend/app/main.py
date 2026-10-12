"""Lalit Stock Application - FastAPI entrypoint.

Owner: Lalit Nayyar <consult@lalit.cloud>, +971568391973.
Disclaimer: not financial advice; market data may be delayed or inaccurate; no warranty.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .core.config import get_settings
from .core.db import SessionLocal
from .core.logging import setup_logging
from .routers import ai, auth, devices, portfolios, simulator, stocks, system
from .services import scheduler, seed

log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    setup_logging(s.log_level)
    db = SessionLocal()
    try:
        seed.bootstrap(db)
    finally:
        db.close()
    if s.scheduler_enabled:
        scheduler.start()
    log.info("Lalit Stock Application %s started (env=%s, provider=%s, simulator=%s)", __version__, s.app_env,
             s.market_provider, s.simulator_active)
    yield
    scheduler.shutdown()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="Lalit Stock Application API",
        version=__version__,
        description=("Portfolio administration, market data, analytics, AI and ESP32 E-Paper device API. "
                     "Owner: Lalit Nayyar (consult@lalit.cloud). Not financial advice; data may be delayed."),
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    if s.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in s.cors_origins.split(",") if o.strip()],
                           allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if request.url.path.startswith("/api/v1/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        return JSONResponse({"error": {"status": exc.status_code, "message": exc.detail}}, status_code=exc.status_code,
                            headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        details = [{"loc": list(e["loc"]), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse({"error": {"status": 422, "message": "Validation failed", "details": details}},
                            status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse({"error": {"status": 500, "message": "Internal server error"}}, status_code=500)

    for r in (system.router, auth.router, stocks.router, portfolios.router, devices.router, ai.router,
              simulator.router):
        app.include_router(r)
    return app


app = create_app()
