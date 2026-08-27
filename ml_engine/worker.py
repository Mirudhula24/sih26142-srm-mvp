"""Celery GPU worker. Holds the model resident in VRAM across jobs.

Consumes the aligned tensor the ingest worker left on the shared volume, runs the SRM
pipeline, writes a georeferenced COG, and returns the metrics the UI displays.
"""
import logging
import math
import os
from typing import Dict

import numpy as np
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
# Tile size fed to the network. Lower it to fit a smaller VRAM or RAM budget; the
# patch loop stitches the results back together either way.
MAX_PATCH_SIZE = int(os.environ.get("MAX_PATCH_SIZE", "256"))

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
    reference_abundances = None
    if not getattr(model, "has_trained_weights", False):
        reference_abundances = inference.worldcover_abundances(
            bundle["bbox"], bundle["tensor"].shape[1], bundle["tensor"].shape[2], device
        )
    inference_mode = (
        "trained_srm" if getattr(model, "has_trained_weights", False)
        else "worldcover_reference" if reference_abundances is not None
        else "spectral_baseline"
    )

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
        patch=MAX_PATCH_SIZE,
        apply_mrf=apply_mrf,
        reference_abundances=reference_abundances,
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

    fine_pixel_size = cog_writer.ground_sample_distance_m(
        bundle["transform"], bundle["crs"]
    ) / scale_factor
    areas = cog_writer.class_areas(classes, fine_pixel_size)
    confidence = _abundance_confidence(result["abundances"], bundle["valid_mask"])
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
        # An mIoU is only meaningful against labelled validation data.  Do not
        # fabricate a confidence/accuracy score for a production AOI.
        "miou_score": None,
        "inference_mode": inference_mode,
        "class_distribution_percent": {k: v["percent"] for k, v in areas.items()},
        "class_area_sqm": {k: v["area_sqm"] for k, v in areas.items()},
        "confidence_mean_percent": confidence["confidence_mean_percent"],
        "high_uncertainty_percent": confidence["high_uncertainty_percent"],
    }


def _abundance_confidence(abundances: np.ndarray, valid_mask: np.ndarray) -> Dict[str, float]:
    """Reduce the (C, H, W) abundance stack to two headline confidence numbers.

    Confidence = 1 - normalized Shannon entropy of the per-pixel class distribution.
    A pure one-hot pixel scores 100%; a uniform distribution scores 0%. Cloud-masked
    coarse pixels are excluded so they don't dilute the average.
    """
    if abundances.size == 0:
        return {"confidence_mean_percent": 0.0, "high_uncertainty_percent": 0.0}
    probs = np.clip(abundances, 1e-6, 1.0)
    entropy = -(probs * np.log(probs)).sum(axis=0)
    norm = entropy / math.log(abundances.shape[0])
    if valid_mask is not None and valid_mask.shape == norm.shape:
        norm = norm[valid_mask]
    if norm.size == 0:
        return {"confidence_mean_percent": 0.0, "high_uncertainty_percent": 0.0}
    confidence = 1.0 - float(norm.mean())
    high_uncertain = float((norm > 0.75).mean())
    return {
        "confidence_mean_percent": round(100.0 * confidence, 1),
        "high_uncertainty_percent": round(100.0 * high_uncertain, 1),
    }
