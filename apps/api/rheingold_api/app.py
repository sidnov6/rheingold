"""FastAPI app factory (spec §10). CORS: web origin only; slowapi on /api/memo."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .deps import limiter
from .routes import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="RHEINGOLD API",
        description="German onshore-wind underwriting: fleet, dossier, underwrite, memo SSE.",
        version=os.environ.get("GIT_SHA", "dev"),
    )
    origin = os.environ.get("ALLOWED_ORIGIN", "http://localhost:3000")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(router)
    return app
