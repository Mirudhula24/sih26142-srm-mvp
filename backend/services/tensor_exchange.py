"""Hand-off of aligned multispectral tensors between the ingest and GPU workers.

Write side. The read side lives in `ml_engine/utils/tensor_exchange.py`; the two must
agree on the archive keys below (tensor, valid_mask, transform, crs, bbox).

The two workers are separate containers (see docs/TECH_CLASHES.md, Clash 1), so the
aligned tensor cannot simply be passed in memory, and it is far too large to put through
the Redis broker. It goes to a shared volume as a compressed .npz and the Celery message
carries only the path.

The affine transform and CRS travel with the array: without them the GPU worker cannot
georeference its output and the exported GeoTIFF opens in the wrong place in QGIS.
"""
import os
from typing import List

import numpy as np
from affine import Affine  # rasterio's own Affine type, without the GDAL import

from config import get_settings


def _path_for(job_id: str) -> str:
    settings = get_settings()
    os.makedirs(settings.tensor_exchange_dir, exist_ok=True)
    return os.path.join(settings.tensor_exchange_dir, f"{job_id}.npz")


def save(
    job_id: str,
    tensor: np.ndarray,
    valid_mask: np.ndarray,
    transform: Affine,
    crs: str,
    bbox: List[float],
) -> str:
    """Write the (6, H, W) tensor plus its georeferencing. Returns the file path."""
    path = _path_for(job_id)
    np.savez_compressed(
        path,
        tensor=tensor.astype(np.float32),
        valid_mask=valid_mask.astype(bool),
        transform=np.asarray(transform[:6], dtype=np.float64),
        crs=np.array(crs),
        bbox=np.asarray(bbox, dtype=np.float64),
    )
    return path
