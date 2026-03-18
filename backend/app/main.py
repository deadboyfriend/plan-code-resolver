import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api import resolver
from app.core.config import settings
from app.services import csv_loader

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# Load xlsx into memory before anything else — fail fast if missing
csv_loader.load()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Resolves benefit configuration values to legacy plancodes via xlsx lookup.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/admin")


@app.get("/health", tags=["Infrastructure"])
def health():
    info = csv_loader.get_load_info()
    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "version": settings.VERSION,
        "rows_loaded": info.get("row_count", 0),
        "data_loaded_at": info.get("loaded_at"),
    }


app.include_router(resolver.router)
