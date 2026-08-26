"""Read side of the ingest -> GPU worker hand-off.

Must stay in step with `backend/services/tensor_exchange.py`, which writes these
archives. Archive keys: tensor, valid_mask, transform, crs, bbox.
"""
import os
from typing import Dict

import numpy as np
from affine import Affine  # rasterio's own Affine type, without the GDAL import


def load(path: str) -> Dict:
    """Read an aligned tensor bundle written by the ingest worker."""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No tensor bundle at {path}. The ingest worker and the GPU worker must "
            f"both mount the same TENSOR_EXCHANGE_DIR volume."
        )
    with np.load(path, allow_pickle=False) as data:
        return {
            "tensor": data["tensor"],              # (6, H, W) float32 in [0, 1]
            "valid_mask": data["valid_mask"],      # (H, W) bool, False where cloud-masked
            "transform": Affine(*data["transform"].tolist()),
            "crs": str(data["crs"]),
            "bbox": data["bbox"].tolist(),
        }


def cleanup(path: str) -> None:
    """Drop the intermediate once inference has consumed it.

    A 256x256x6 float32 tile is only ~1.5 MB compressed, but a demo session churns
    through plenty of them and nothing else garbage-collects the volume.
    """
    try:
        os.remove(path)
    except OSError:
        pass
