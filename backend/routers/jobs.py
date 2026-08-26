"""Job status, exports and analytics."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from schemas import SRMResponse
from services import exporter, tasks

router = APIRouter()


@router.get("/{job_id}", response_model=SRMResponse)
def get_job(job_id: str) -> SRMResponse:
    job = tasks.get_job_status(job_id)
    if job is None:
        raise HTTPException(404, f"Unknown job {job_id}")
    return job


@router.get("/{job_id}/export.tif")
def export_geotiff(job_id: str) -> FileResponse:
    """Cloud-Optimized GeoTIFF with CRS tags preserved (EPSG:4326 / EPSG:32643)."""
    path = exporter.cog_path_for_job(job_id)
    if path is None:
        raise HTTPException(404, f"No COG available for job {job_id}")
    return FileResponse(path, media_type="image/tiff", filename=f"{job_id}_srm_2p5m.tif")


@router.get("/{job_id}/export.geojson")
def export_geojson(job_id: str) -> dict:
    """Vectorised sub-pixel class boundaries as a simplified FeatureCollection."""
    fc = exporter.vectorise_job(job_id)
    if fc is None:
        raise HTTPException(404, f"No raster available for job {job_id}")
    return fc


@router.get("/{job_id}/report.csv")
def export_csv(job_id: str) -> FileResponse:
    path = exporter.class_metrics_csv(job_id)
    if path is None:
        raise HTTPException(404, f"No metrics available for job {job_id}")
    return FileResponse(path, media_type="text/csv", filename=f"{job_id}_landcover.csv")
