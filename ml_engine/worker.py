"""Celery GPU worker. Holds the model resident in VRAM across jobs."""
import logging
import os
from typing import Dict, List

from celery import Celery

import inference

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

celery_app = Celery(
    "srm_ml",
    broker=os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/1"),
    backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/2"),
)

_MODEL = None
_DEVICE = None


def _get_model(scale_factor: int):
    """Lazy singleton — loading weights per task would blow the latency budget."""
    global _MODEL, _DEVICE
    if _MODEL is None:
        _MODEL, _DEVICE = inference.load_model(
            weights_path=os.environ.get("MODEL_WEIGHTS_PATH", "weights/sih26142_srm_v1.pth"),
            device=os.environ.get("DEVICE", "cuda"),
            scale_factor=scale_factor,
        )
    return _MODEL, _DEVICE


@celery_app.task(name="srm.infer")
def infer(
    job_id: str,
    granule_id: str,
    scale_factor: int = 4,
    target_classes: List[str] = None,
    apply_mrf_smoothing: bool = True,
) -> Dict:
    import numpy as np

    model, device = _get_model(scale_factor)

    # TODO(ingestion): replace with the aligned tensor handed over by the ingest worker
    # through the shared volume. Placeholder keeps the queue end-to-end testable.
    tensor = np.zeros((6, 256, 256), dtype=np.float32)

    result = inference.run_srm(
        tensor, model, device, scale_factor=scale_factor, apply_mrf=apply_mrf_smoothing
    )
    return {
        "job_id": job_id,
        "granule_id": granule_id,
        "execution_time_seconds": result["execution_time_seconds"],
        "mass_conservation_error": result["mass_conservation_error"],
        "class_distribution_percent": inference.class_distribution(result["classes"]),
    }
