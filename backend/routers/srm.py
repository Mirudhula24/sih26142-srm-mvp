"""POST /api/v1/srm/process — queue a super-resolution mapping job."""
from fastapi import APIRouter, HTTPException

from schemas import SRMRequest, SRMResponse
from services import stac_fetcher, tasks

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

    job_id = tasks.dispatch_srm_job(
        granule_id=req.granule_id,
        bbox=bbox,
        scale_factor=req.scale_factor,
        target_classes=req.target_classes,
        apply_mrf_smoothing=req.apply_mrf_smoothing,
        max_cloud_cover=req.max_cloud_cover,
    )
    return SRMResponse(job_id=job_id, status="PENDING")
