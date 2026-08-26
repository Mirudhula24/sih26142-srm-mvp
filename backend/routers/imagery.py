"""POST /api/v1/imagery/fetch — resolve an AOI to a Sentinel-2 L2A granule."""
import logging

from fastapi import APIRouter, HTTPException

from config import INPUT_BANDS, get_settings
from schemas import FetchRequest, FetchResponse
from services import offline_cache, stac_fetcher, tasks

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/fetch", response_model=FetchResponse)
def fetch_granule(req: FetchRequest) -> FetchResponse:
    settings = get_settings()
    try:
        bbox = stac_fetcher.bbox_from_polygon(req.aoi_geojson.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if not settings.offline_mode:
        try:
            scene = stac_fetcher.search_best_scene(
                bbox=bbox,
                date_range=f"{req.date_range.start}/{req.date_range.end}",
                max_cloud=req.max_cloud_cover,
            )
            tasks.remember_granule_bbox(scene["scene_id"], bbox)
            return FetchResponse(
                status="SUCCESS",
                granule_id=scene["scene_id"],
                cloud_cover=scene["cloud_cover"],
                bands_available=INPUT_BANDS,
                preview_url=scene.get("preview_url"),
            )
        except Exception as exc:  # noqa: BLE001 — any network/STAC failure falls back
            log.warning("STAC fetch failed (%s); falling back to local cache", exc)

    scene = offline_cache.nearest_cached_scene(bbox)
    if scene is None:
        raise HTTPException(404, "No live granule and no cached scene covers this AOI.")
    tasks.remember_granule_bbox(scene["scene_id"], scene.get("bbox", bbox))
    return FetchResponse(
        status="FALLBACK_CACHE",
        granule_id=scene["scene_id"],
        cloud_cover=scene["cloud_cover"],
        bands_available=INPUT_BANDS,
        preview_url=scene.get("preview_url"),
    )
