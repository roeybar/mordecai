import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import __version__, frames, hosted
from .routes import health, translate

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
log = logging.getLogger("mordecai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("frame store: %s", frames.store().stats())
    cfg = hosted.config()
    log.info("%s", hosted.describe(cfg))
    if cfg.on and not cfg.trusted:
        log.warning("hosted: TRUSTED_PROXIES is empty, so every visitor shares the connecting proxy's limit")
    yield


app = FastAPI(title="mordecai", version=__version__, lifespan=lifespan)
app.include_router(health.router)
app.include_router(translate.router)


@app.exception_handler(RequestValidationError)
async def bad_request(request: Request, exc: RequestValidationError):
    # exc.errors() carries the offending input values: never log or return them.
    return JSONResponse({"error": "bad_request"}, status_code=422)
