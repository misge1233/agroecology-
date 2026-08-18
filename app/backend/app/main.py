"""FastAPI application entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.config import get_settings
from app.helpers import RequestIdMiddleware
from app.routers import chat, health, metadata, models, recommend
from app.services.recommender_service import warmup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("Warming up recommender engine (model + dataset + rasters)…")
    warmup()
    logger.info("Recommender engine ready.")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestIdMiddleware)

    application.include_router(health.router)
    application.include_router(metadata.router)
    application.include_router(recommend.router)
    application.include_router(models.router)
    application.include_router(chat.router)

    @application.exception_handler(HTTPException)
    async def http_handler(_request: Request, exc: HTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "error" in detail:
            return JSONResponse(status_code=exc.status_code, content=detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": "http_error",
                    "message": str(detail),
                    "details": None,
                }
            },
        )

    @application.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Invalid request",
                    "details": jsonable_encoder(exc.errors()),
                }
            },
        )

    @application.exception_handler(Exception)
    async def unhandled(_request: Request, exc: Exception):
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred.",
                    "details": None,
                }
            },
        )

    return application


app = create_app()
