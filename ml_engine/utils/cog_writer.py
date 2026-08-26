"""Write the sub-pixel class raster as a Cloud-Optimized GeoTIFF.

Lives on the GPU worker because that is where the class map is produced; the backend
only ever reads these files back (see backend/services/exporter.py).
"""
import os
from typing import Dict

import numpy as np
import rasterio
from rasterio.transform import Affine
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles

CLASSES = ["built_up", "water", "vegetation", "cropland", "bare_soil"]

# Display palette. Must match LAND_COVER_CLASSES in frontend/src/lib/constants.js.
CLASS_COLORS = {
    0: (214, 96, 77),    # built_up
    1: (33, 102, 172),   # water
    2: (27, 120, 55),    # vegetation
    3: (166, 219, 108),  # cropland
    4: (191, 165, 122),  # bare_soil
}

NODATA = 255


def write_cog(
    classes: np.ndarray,
    transform: Affine,
    crs: str,
    job_id: str,
    out_dir: str,
    scale_factor: int = 4,
) -> str:
    """Write `classes` as a COG, returning the output path.

    The allocation shrinks the ground sample distance by `scale_factor`, so the affine
    must be scaled to match. Skip this and the raster opens in QGIS at 4x its true
    extent -- the single most common way these outputs end up silently wrong.
    """
    os.makedirs(out_dir, exist_ok=True)
    fine_transform = transform * Affine.scale(1 / scale_factor, 1 / scale_factor)

    tmp = os.path.join(out_dir, f".{job_id}.tmp.tif")
    out = os.path.join(out_dir, f"{job_id}.tif")

    profile = {
        "driver": "GTiff",
        "dtype": "uint8",
        "count": 1,
        "height": classes.shape[0],
        "width": classes.shape[1],
        "crs": crs,
        "transform": fine_transform,
        "nodata": NODATA,
    }
    with rasterio.open(tmp, "w", **profile) as dst:
        dst.write(classes.astype(np.uint8), 1)
        dst.write_colormap(1, {k: (*v, 255) for k, v in CLASS_COLORS.items()})

    # Nearest-neighbour overviews: averaging categorical class ids would invent classes
    # that the model never predicted.
    cog_translate(
        tmp, out, cog_profiles.get("deflate"), overview_resampling="nearest", quiet=True
    )
    os.remove(tmp)
    return out


def class_areas(classes: np.ndarray, pixel_size_m: float) -> Dict[str, Dict[str, float]]:
    """Sub-pixel counts -> area in m2 and hectares, plus percentage distribution."""
    cell_area = pixel_size_m**2
    total = int(np.count_nonzero(classes != NODATA))
    out: Dict[str, Dict[str, float]] = {}
    for idx, name in enumerate(CLASSES):
        count = int(np.count_nonzero(classes == idx))
        out[name] = {
            "sub_pixels": count,
            "area_sqm": round(count * cell_area, 2),
            "area_hectares": round(count * cell_area / 10_000.0, 4),
            "percent": round(100.0 * count / total, 2) if total else 0.0,
        }
    return out
