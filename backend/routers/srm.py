"""POST /api/v1/srm/process — queue a super-resolution mapping job."""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from config import get_settings
from schemas import SRMRequest, SRMResponse
from services import previews, stac_fetcher, tasks

log = logging.getLogger(__name__)

router = APIRouter()


@router.post("/process", response_model=SRMResponse, status_code=202)
def process(req: SRMRequest) -> SRMResponse:
    """Dispatch ingest -> inference asynchronously; poll /api/v1/jobs/{job_id}."""
    # The ingest step needs a bbox. Take it from the request when the client sends one,
    # otherwise reuse whatever /imagery/fetch recorded for this granule.
    if req.aoi_geojson is not None:
        bbox = stac_fetcher.bbox_from_polygon(req.aoi_geojson.model_dump())
    else:
        bbox = tasks.known_bbox(req.granule_id)

    if bbox is None:
        raise HTTPException(
            400,
            f"No AOI for granule {req.granule_id}. Send aoi_geojson, or call "
            f"/api/v1/imagery/fetch first so the bounding box is on record.",
        )

    settings = get_settings()
    if settings.sync_mode:
        return _run_inline(req, bbox)

    job_id = tasks.dispatch_srm_job(
        granule_id=req.granule_id,
        bbox=bbox,
        scale_factor=req.scale_factor,
        target_classes=req.target_classes,
        apply_mrf_smoothing=req.apply_mrf_smoothing,
        max_cloud_cover=req.max_cloud_cover,
    )
    return SRMResponse(job_id=job_id, status="PENDING")


def _run_inline(req: SRMRequest, bbox) -> SRMResponse:
    """Ingest and infer in this process, returning a finished job.

    The endpoint still answers 202 with a job id, so the client's polling loop is
    unchanged between sync and distributed modes -- the first poll simply already
    finds the job COMPLETED.
    """
    from services import pipeline  # heavy imports stay out of module load

    job_id = f"job_srm_{uuid.uuid4().hex[:12]}"
    try:
        out = pipeline.run_sync(
            job_id=job_id,
            bbox=bbox,
            scale_factor=req.scale_factor,
            apply_mrf=req.apply_mrf_smoothing,
            max_cloud=req.max_cloud_cover,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI rather than a 500
        log.exception("[%s] sync job failed", job_id)
        failed = SRMResponse(
            job_id=job_id, status="FAILED", error=str(exc),
            created_at=datetime.now(timezone.utc),
        )
        tasks.record_job(failed)
        return failed

    job = SRMResponse(
        job_id=job_id,
        status="COMPLETED",
        data_source=out["data_source"],
        granule_id=out["granule_id"],
        cloud_cover=out["cloud_cover"],
        execution_time_seconds=out["execution_time_seconds"],
        mass_conservation_error=out["mass_conservation_error"],
        fine_pixel_size_m=out["fine_pixel_size_m"],
        bounds=out["bounds"],
        class_distribution_percent=out["class_distribution_percent"],
        class_area_sqm=out["class_area_sqm"],
        cog_output_url=f"/api/v1/jobs/{job_id}/export.tif",
        created_at=datetime.now(timezone.utc),
        **previews.urls_for(job_id),
    )
    tasks.record_job(job)
    return job
