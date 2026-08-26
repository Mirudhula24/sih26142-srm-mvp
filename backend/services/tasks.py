"""Celery orchestration.

Two queues, deliberately bound to two different containers:
  * `ingest`    — GDAL / Rasterio / PySTAC (CPU, single-threaded C pools)
  * `inference` — PyTorch + CUDA (GPU)
Keeping them apart avoids OpenMP over-subscription and GPU/event-loop contention.
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from celery import Celery

from config import get_settings
from schemas import SRMResponse

settings = get_settings()
celery_app = Celery(
    "srm",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.task_routes = {
    "srm.ingest": {"queue": "ingest"},
    "srm.infer": {"queue": "inference"},
}

# In-memory job mirror. The authoritative record lives in PostGIS (`srm_jobs`);
# this keeps status polling cheap during a demo.
_JOBS: Dict[str, SRMResponse] = {}


@celery_app.task(name="srm.ingest")
def ingest_task(job_id: str, granule_id: str, bbox: List[float]) -> Dict:
    """Fetch bands, align SWIR to the 10 m grid, mask clouds; hand off to inference."""
    from services import preprocessor, stac_fetcher  # imported lazily: heavy GDAL deps

    scene = stac_fetcher.search_best_scene(bbox=bbox)
    prepared = preprocessor.build_input_tensor(scene["band_urls"], bbox)
    return {
        "job_id": job_id,
        "granule_id": granule_id,
        "crs": prepared["crs"],
        "valid_fraction": prepared["valid_fraction"],
    }


def dispatch_srm_job(
    granule_id: str,
    scale_factor: int,
    target_classes: List[str],
    apply_mrf_smoothing: bool,
) -> str:
    job_id = f"job_srm_{uuid.uuid4().hex[:12]}"
    _JOBS[job_id] = SRMResponse(
        job_id=job_id,
        status="PENDING",
        created_at=datetime.now(timezone.utc),
    )
    celery_app.send_task(
        "srm.infer",
        kwargs={
            "job_id": job_id,
            "granule_id": granule_id,
            "scale_factor": scale_factor,
            "target_classes": target_classes,
            "apply_mrf_smoothing": apply_mrf_smoothing,
        },
        queue="inference",
    )
    return job_id


def get_job_status(job_id: str) -> Optional[SRMResponse]:
    job = _JOBS.get(job_id)
    if job is None:
        return None
    if job.status in ("PENDING", "RUNNING"):
        result = celery_app.AsyncResult(job_id)
        if result.successful():
            payload = result.result or {}
            job.status = "COMPLETED"
            job.execution_time_seconds = payload.get("execution_time_seconds")
            job.class_distribution_percent = payload.get("class_distribution_percent")
            job.class_area_sqm = payload.get("class_area_sqm")
            job.miou_score = payload.get("miou_score")
            job.cog_output_url = f"/api/v1/jobs/{job_id}/export.tif"
            job.tile_url_template = (
                f"{settings.titiler_base_url}/cog/tiles/WebMercatorQuad/"
                f"{{z}}/{{x}}/{{y}}.png?url=/data/cogs/{job_id}.tif"
            )
        elif result.failed():
            job.status = "FAILED"
    return job
