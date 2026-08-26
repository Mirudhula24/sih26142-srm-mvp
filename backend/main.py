"""FastAPI gateway for the GeoSRM Engine (SIH26142)."""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import LAND_COVER_CLASSES, get_settings
from routers import analysis, imagery, jobs, srm

logging.basicConfig(level=logging.INFO)
settings = get_settings()

app = FastAPI(
    title="SIH26142 — GeoSRM Engine API",
    description=(
        "Deep-learning Super-Resolution Mapping of Sentinel-2 L2A imagery: "
        "spectral unmixing plus sub-pixel spatial allocation at a 4x scale factor."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(imagery.router, prefix="/api/v1/imagery", tags=["imagery"])
app.include_router(srm.router, prefix="/api/v1/srm", tags=["srm"])
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])
app.include_router(analysis.router, prefix="/api/v1/analysis", tags=["analysis"])


@app.get("/health", tags=["system"])
def health() -> dict:
    return {
        "status": "ok",
        "offline_mode": settings.offline_mode,
        "scale_factor": settings.scale_factor,
        "classes": LAND_COVER_CLASSES,
    }
