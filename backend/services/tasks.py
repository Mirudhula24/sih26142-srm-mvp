"""Celery orchestration.

Two queues, deliberately bound to two different containers:
  * `ingest`    — GDAL / Rasterio / PySTAC (CPU, single-threaded C pools)
  * `inference` — PyTorch + CUDA (GPU)
Keeping them apart avoids OpenMP over-subscription and GPU/event-loop contention.

A job is a Celery chain: srm.ingest -> srm.infer. The ingest step writes the aligned
tensor to the shared volume and returns its path; the chain hands that dict to the GPU
worker, which lives in the other image and is addressed by task name only.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from celery import Celery, chain

from config import get_settings
from schemas import SRMResponse

log = logging.getLogger(__name__)
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

# In-memory job mirror. The authoritative record lives in PostGIS (`srm_jobs`); this
# keeps status polling cheap during a demo.
_JOBS: Dict[str, SRMResponse] = {}
# Our job_id is a readable label, not a Celery task id — keep the mapping to the chain's
# terminal task so status polling can find the result.
_TASK_IDS: Dict[str, str] = {}
# bbox recorded at /imagery/fetch time, so /srm/process can run from a granule_id alone.
_GRANULE_BBOX: Dict[str, List[float]] = {}


def remember_granule_bbox(granule_id: str, bbox: List[float]) -> None:
    _GRANULE_BBOX[granule_id] = bbox


def known_bbox(granule_id: str) -> Optional[List[float]]:
    return _GRANULE_BBOX.get(granule_id)


@celery_app.task(name="srm.ingest")
def ingest_task(
    job_id: str,
    granule_id: str,
    bbox: List[float],
    scale_factor: int = 4,
    apply_mrf_smoothing: bool = True,
    max_cloud_cover: Optional[float] = None,
    offline: bool = False,
) -> Dict:
    """Fetch bands, align SWIR to the 10 m grid, mask clouds, stage the tensor.

    Returns the payload the chain feeds straight into `srm.infer`.
    """
    # Imported lazily: these pull in the heavy GDAL stack, which the API process
    # should never load.
    from services import offline_cache, preprocessor, stac_fetcher, tensor_exchange

    stac_fetcher.validate_aoi_bbox(bbox)

    band_source = None
    if not offline:
        try:
            scene = stac_fetcher.search_best_scene(
                bbox=bbox, max_cloud=max_cloud_cover or settings.max_cloud_cover
            )
            band_source = scene["band_urls"]
            granule_id = scene["scene_id"]
        except Exception as exc:  # noqa: BLE001 — any network/STAC failure falls back
            log.warning("[%s] STAC ingest failed (%s); trying local cache", job_id, exc)

    if band_source is None:
        cached = offline_cache.nearest_cached_scene(bbox)
        if cached is None:
            raise RuntimeError("No live granule and no cached scene covers this AOI.")
        band_source = offline_cache.band_sources(cached)
        granule_id = cached["scene_id"]
        bbox = cached.get("bbox", bbox)

    prepared = preprocessor.build_input_tensor(band_source, bbox)
    tensor_path = tensor_exchange.save(
        job_id=job_id,
        tensor=prepared["tensor"],
        valid_mask=prepared["valid_mask"],
        transform=prepared["transform"],
        crs=prepared["crs"],
        bbox=bbox,
    )
    log.info(
        "[%s] staged %s tensor at %s (%.1f%% valid)",
        job_id,
        prepared["tensor"].shape,
        tensor_path,
        100.0 * prepared["valid_fraction"],
    )

    return {
        "job_id": job_id,
        "granule_id": granule_id,
        "tensor_path": tensor_path,
        "scale_factor": scale_factor,
        "apply_mrf_smoothing": apply_mrf_smoothing,
        "crs": prepared["crs"],
        "valid_fraction": prepared["valid_fraction"],
    }


def dispatch_srm_job(
    granule_id: str,
    bbox: List[float],
    scale_factor: int,
    target_classes: List[str],
    apply_mrf_smoothing: bool,
    max_cloud_cover: Optional[float] = None,
) -> str:
    """Queue ingest -> infer and return the job id to poll."""
    job_id = f"job_srm_{uuid.uuid4().hex[:12]}"

    workflow = chain(
        celery_app.signature(
            "srm.ingest",
            kwargs={
                "job_id": job_id,
                "granule_id": granule_id,
                "bbox": bbox,
                "scale_factor": scale_factor,
                "apply_mrf_smoothing": apply_mrf_smoothing,
                "max_cloud_cover": max_cloud_cover,
                "offline": settings.offline_mode,
            },
            queue="ingest",
        ),
        # Defined in the ml_engine image; reachable by name over the shared broker.
        celery_app.signature("srm.infer", queue="inference"),
    )
    async_result = workflow.apply_async()

    _TASK_IDS[job_id] = async_result.id
    _JOBS[job_id] = SRMResponse(
        job_id=job_id, status="PENDING", created_at=datetime.now(timezone.utc)
    )
    return job_id


def get_job_status(job_id: str) -> Optional[SRMResponse]:
    job = _JOBS.get(job_id)
    if job is None:
        return None
    if job.status in ("COMPLETED", "FAILED"):
        return job

    res = celery_app.AsyncResult(_TASK_IDS[job_id])
    if res.successful():
        payload = res.result or {}
        job.status = "COMPLETED"
        job.execution_time_seconds = payload.get("execution_time_seconds")
        job.class_distribution_percent = payload.get("class_distribution_percent")
        job.class_area_sqm = payload.get("class_area_sqm")
        job.scale_factor = payload.get("scale_factor")
        job.miou_score = payload.get("miou_score")
        job.inference_mode = payload.get("inference_mode")
        job.confidence_mean_percent = payload.get("confidence_mean_percent")
        job.high_uncertainty_percent = payload.get("high_uncertainty_percent")
        job.cog_output_url = f"/api/v1/jobs/{job_id}/export.tif"
        job.tile_url_template = (
            f"{settings.titiler_base_url}/cog/tiles/WebMercatorQuad/"
            f"{{z}}/{{x}}/{{y}}.png?url=/data/cogs/{job_id}.tif"
        )
        return job

    # Traverse chain tasks (srm.infer -> srm.ingest) to catch upstream failures/running states
    curr = res
    while curr is not None:
        if curr.failed():
            job.status = "FAILED"
            err_msg = str(curr.result) if curr.result else "Job failed during processing."
            if "WorkerLostError" in err_msg or "SIGKILL" in err_msg or "signal 9" in err_msg:
                err_msg = "Job worker memory limit exceeded (OOM). Please select or draw a smaller Area of Interest (AOI)."
            job.error = err_msg
            log.error("[%s] job failed: %s", job_id, err_msg)
            return job
        if curr.state == "STARTED":
            job.status = "RUNNING"
        curr = curr.parent

    return job
