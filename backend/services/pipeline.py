"""Synchronous single-process pipeline: ingest, infer, export, all in the API process.

The production path splits ingestion and inference across two containers behind a Celery
broker (see docs/PIPELINE_HANDOFF.md). That is the right architecture and the wrong thing
to require on a laptop during development, so this module runs the same stages inline —
no Redis, no Celery, no Docker, no GPU.

Enable with SYNC_MODE=true. The stages are the same functions the workers call, so a bug
found here is a real bug, not an artefact of the shortcut.
"""
import logging
import os
import sys
import time
from typing import Dict, List, Optional

import numpy as np

from config import LAND_COVER_CLASSES, get_settings

log = logging.getLogger(__name__)

# The inference code lives in the ml_engine image. In sync mode we import it directly.
_ML_ENGINE = os.path.join(os.path.dirname(__file__), "..", "..", "ml_engine")
if _ML_ENGINE not in sys.path:
    sys.path.insert(0, os.path.abspath(_ML_ENGINE))

# A whole Sentinel-2 granule would take minutes on a CPU. Sync mode is for seeing the
# pipeline work, so the AOI is capped and the rest of the request is honoured as drawn.
MAX_COARSE_PX = 192

_MODEL = None
_DEVICE = None
_MODEL_SCALE = None


def _load_model(scale_factor: int):
    global _MODEL, _DEVICE, _MODEL_SCALE
    if _MODEL is None or _MODEL_SCALE != scale_factor:
        import inference

        _MODEL, _DEVICE = inference.load_model(
            weights_path=os.environ.get("MODEL_WEIGHTS_PATH"),
            device=os.environ.get("DEVICE", "cpu"),
            scale_factor=scale_factor,
        )
        _MODEL_SCALE = scale_factor
    return _MODEL, _DEVICE


def _clamp(tensor: np.ndarray, mask: np.ndarray, transform):
    """Crop to MAX_COARSE_PX around the centre, keeping the affine consistent."""
    _, h, w = tensor.shape
    if h <= MAX_COARSE_PX and w <= MAX_COARSE_PX:
        return tensor, mask, transform
    top = max(0, (h - MAX_COARSE_PX) // 2)
    left = max(0, (w - MAX_COARSE_PX) // 2)
    bottom, right = top + min(h, MAX_COARSE_PX), left + min(w, MAX_COARSE_PX)
    log.info("Cropping %dx%d AOI to %dx%d for sync inference", h, w, bottom - top, right - left)
    return (
        tensor[:, top:bottom, left:right],
        mask[top:bottom, left:right],
        transform * transform.translation(left, top),
    )


def resolve_bands(bbox: List[float], max_cloud: Optional[float]) -> Dict:
    """Live STAC first, then the local cache. Raises if neither can supply the AOI."""
    from services import offline_cache, stac_fetcher

    settings = get_settings()
    if not settings.offline_mode:
        try:
            scene = stac_fetcher.search_best_scene(
                bbox=bbox, max_cloud=max_cloud or settings.max_cloud_cover
            )
            return {
                "band_urls": scene["band_urls"],
                "granule_id": scene["scene_id"],
                "cloud_cover": scene["cloud_cover"],
                "source": "stac",
            }
        except Exception as exc:  # noqa: BLE001
            log.warning("STAC unavailable (%s); trying the local cache", exc)

    cached = offline_cache.nearest_cached_scene(bbox)
    if cached is None:
        raise RuntimeError(
            "No imagery available: the STAC query failed and data_cache/ is empty. "
            "Run scripts/build_offline_cache.py, or check the network."
        )
    return {
        "band_urls": offline_cache.band_sources(cached),
        "granule_id": cached["scene_id"],
        "cloud_cover": cached.get("cloud_cover", 0.0),
        "source": "cache",
    }


def run_sync(
    job_id: str,
    bbox: List[float],
    scale_factor: int = 4,
    apply_mrf: bool = True,
    max_cloud: Optional[float] = None,
) -> Dict:
    """Run the whole pipeline inline and return everything the UI needs."""
    from services import previews, preprocessor
    import inference
    from utils import cog_writer

    settings = get_settings()
    started = time.perf_counter()

    resolved = resolve_bands(bbox, max_cloud)
    prepared = preprocessor.build_input_tensor(resolved["band_urls"], bbox)
    tensor, valid, transform = _clamp(
        prepared["tensor"], prepared["valid_mask"], prepared["transform"]
    )

    model, device = _load_model(scale_factor)
    result = inference.run_srm(
        tensor, model, device, scale_factor=scale_factor, patch=MAX_COARSE_PX,
        apply_mrf=apply_mrf,
    )
    classes = result["classes"]

    # Cloud-masked coarse pixels must not be reported as land cover.
    invalid = ~valid
    if invalid.any():
        fine = invalid.repeat(scale_factor, axis=0).repeat(scale_factor, axis=1)
        classes[fine[: classes.shape[0], : classes.shape[1]]] = cog_writer.NODATA

    cog_path = cog_writer.write_cog(
        classes, transform=transform, crs=prepared["crs"], job_id=job_id,
        out_dir=settings.cog_storage_dir, scale_factor=scale_factor,
    )

    fine_pixel = abs(transform.a) / scale_factor
    areas = cog_writer.class_areas(classes, fine_pixel)

    # TiTiler is not running in sync mode, so the maps are fed plain PNG overlays
    # positioned by their corner coordinates instead of XYZ tiles.
    bounds = previews.wgs84_corners(transform, tensor.shape[1], tensor.shape[2], prepared["crs"])
    previews.write_rgb(tensor, job_id)
    previews.write_classes(classes, job_id)

    elapsed = time.perf_counter() - started
    log.info("[%s] sync job done in %.2fs (%s)", job_id, elapsed, resolved["source"])

    return {
        "job_id": job_id,
        "granule_id": resolved["granule_id"],
        "data_source": resolved["source"],
        "cloud_cover": resolved["cloud_cover"],
        "cog_path": cog_path,
        "execution_time_seconds": round(elapsed, 2),
        "inference_time_seconds": result["execution_time_seconds"],
        "mass_conservation_error": result["mass_conservation_error"],
        "coarse_shape": [int(tensor.shape[1]), int(tensor.shape[2])],
        "fine_shape": [int(classes.shape[0]), int(classes.shape[1])],
        "fine_pixel_size_m": round(fine_pixel, 3),
        "bounds": bounds,
        "class_distribution_percent": {k: v["percent"] for k, v in areas.items()},
        "class_area_sqm": {k: v["area_sqm"] for k, v in areas.items()},
        "classes": LAND_COVER_CLASSES,
    }
