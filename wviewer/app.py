import logging
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from wviewer.routers import imports, networks

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Ensure the database schema exists before the first request is served.

    Runs inside uvicorn's event loop, avoiding cross-loop issues with the
    async engine. create_all is idempotent — safe to call on every startup.
    """
    from wviewer.db import Base, engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema ready.")
    yield


try:
    _version = version("wviewer")
except PackageNotFoundError:
    _version = "0.0.0"  # fallback when running outside an installed package

app = FastAPI(title="wViewer", version=_version, lifespan=_lifespan)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: log and return a consistent JSON error instead of an HTML 500 page."""
    logger.exception("Unhandled exception for %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error."},
    )

app.include_router(imports.router)
app.include_router(networks.router)

app.mount(
    "/static",
    StaticFiles(directory=_STATIC_DIR),
    name="static",
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")
