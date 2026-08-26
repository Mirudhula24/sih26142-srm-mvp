"""Celery GPU worker. Holds the model resident in VRAM across jobs.

Consumes the aligned tensor the ingest worker left on the shared volume, runs the SRM
pipeline, writes a georeferenced COG, and returns the metrics the UI displays.
"""
import logging
import os
from typing import Dict

from celery import Celery

import inference
from utils import cog_writer, tensor_exchange

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

celery_app = Celery(
    "srm_ml",
    broker=os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/1"),
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/2"),
)

COG_DIR = os.environ.get("COG_STORAGE_DIR", "/data/cogs")

_MODEL = None
_DEVICE = None
_MODEL_SCALE = None


def _get_model(scale_factor: int):
    """Lazy singleton — reloading weights per task would blow the latency budget.

    The upsampler is built around a fixed scale factor, so switching between 4x and the
    experimental 8x mode requires rebuilding rather than reusing the cached model.
    """
    global _MODEL, _DEVICE, _MODEL_SCALE
    if _MODEL is None or _MODEL_SCALE != scale_factor:
        _MODEL, _DEVICE = inference.load_model(
            weights_path=os.environ.get("MODEL_WEIGHTS_PATH", "weights/sih26142_srm_v1.pth"),
            device=os.environ.get("DEVICE", "cuda"),
            scale_factor=scale_factor,
        )
        _MODEL_SCALE = scale_factor
    return _MODEL, _DEVICE


@celery_app.task(name="srm.infer")
def infer(payload: Dict) -> Dict:
    """Run SRM on the tensor the ingest worker prepared.

    `payload` is the return value of `srm.ingest`, delivered by the Celery chain:
        job_id, granule_id, tensor_path, scale_factor, apply_mrf_smoothing
    """
    job_id = payload["job_id"]
    tensor_path = payload["tensor_path"]
    scale_factor = int(payload.get("scale_factor", 4))
    apply_mrf = bool(payload.get("apply_mrf_smoothing", True))

    bundle = tensor_exchange.load(tensor_path)
    model, device = _get_model(scale_factor)

    log.info(
        "[%s] inferring on %s tile (valid %.1f%%)",
        job_id,
        "x".join(str(d) for d in bundle["tensor"].shape[1:]),
        100.0 * float(bundle["valid_mask"].mean()),
    )

    result = inference.run_srm(
        bundle["tensor"],
        model,
        device,
        scale_factor=scale_factor,
        apply_mrf=apply_mrf,
    )
    classes = result["classes"]

    # Cloud-masked coarse pixels must not be reported as land cover — propagate the
    # mask to every sub-pixel it covers so the area metrics stay honest.
    invalid = ~bundle["valid_mask"]
    if invalid.any():
        fine_invalid = invalid.repeat(scale_factor, axis=0).repeat(scale_factor, axis=1)
        classes[fine_invalid[: classes.shape[0], : classes.shape[1]]] = cog_writer.NODATA

    cog_path = cog_writer.write_cog(
        classes,
        transform=bundle["transform"],
        crs=bundle["crs"],
        job_id=job_id,
        out_dir=COG_DIR,
        scale_factor=scale_factor,
    )

    fine_pixel_size = abs(bundle["transform"].a) / scale_factor
    areas = cog_writer.class_areas(classes, fine_pixel_size)
    tensor_exchange.cleanup(tensor_path)

    log.info(
        "[%s] done in %.2fs -> %s (mass err %.2e)",
        job_id,
        result["execution_time_seconds"],
        cog_path,
        result["mass_conservation_error"],
    )

    return {
        "job_id": job_id,
        "granule_id": payload.get("granule_id"),
        "cog_path": cog_path,
        "scale_factor": scale_factor,
        "fine_pixel_size_m": fine_pixel_size,
        "execution_time_seconds": result["execution_time_seconds"],
        "mass_conservation_error": result["mass_conservation_error"],
        "class_distribution_percent": {k: v["percent"] for k, v in areas.items()},
        "class_area_sqm": {k: v["area_sqm"] for k, v in areas.items()},
    }
