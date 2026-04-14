from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from wviewer.routers import imports, networks

app = FastAPI(title="wViewer", version="0.1.0")

app.include_router(imports.router)
app.include_router(networks.router)

app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "static"),
    name="static",
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
