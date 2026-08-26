"""POST /api/v1/srm/process — queue a super-resolution mapping job."""
from fastapi import APIRouter

from schemas import SRMRequest, SRMResponse
from services import tasks

router = APIRouter()


@router.post("/process", response_model=SRMResponse, status_code=202)
def process(req: SRMRequest) -> SRMResponse:
    """Dispatch ingestion + inference asynchronously; poll /api/v1/jobs/{job_id}."""
    job_id = tasks.dispatch_srm_job(
        granule_id=req.granule_id,
        scale_factor=req.scale_factor,
        target_classes=req.target_classes,
        apply_mrf_smoothing=req.apply_mrf_smoothing,
    )
    return SRMResponse(job_id=job_id, status="PENDING")
