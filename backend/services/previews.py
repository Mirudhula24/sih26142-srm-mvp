"""PNG overlays for the map canvases, used when TiTiler is not running.

In the full stack TiTiler streams XYZ tiles straight from the COG. Sync mode has no tile
server, so each job also writes two small PNGs which MapLibre places as `image` sources
positioned by their four corner coordinates. Same picture, no tile infrastructure.
"""
import os
from typing import Dict, List

import numpy as np
from PIL import Image
from rasterio.warp import transform as warp_transform

from config import get_settings

NODATA = 255

# Must match ml_engine/utils/cog_writer.py and frontend/src/lib/constants.js.
CLASS_COLORS = {
    0: (214, 96, 77),    # built_up
    1: (33, 102, 172),   # water
    2: (27, 120, 55),    # vegetation
    3: (166, 219, 108),  # cropland
    4: (191, 165, 122),  # bare_soil
}


def preview_dir() -> str:
    d = os.path.join(get_settings().cog_storage_dir, "previews")
    os.makedirs(d, exist_ok=True)
    return d


def path_for(job_id: str, kind: str) -> str:
    return os.path.join(preview_dir(), f"{job_id}_{kind}.png")


def wgs84_corners(transform, height: int, width: int, crs: str) -> List[List[float]]:
    """Corner coordinates in the order MapLibre's image source expects.

    Top-left, top-right, bottom-right, bottom-left — in lon/lat, reprojected from the
    granule's UTM zone.
    """
    corners_px = [(0, 0), (width, 0), (width, height), (0, height)]
    xs, ys = zip(*[transform * (c, r) for c, r in corners_px])
    lons, lats = warp_transform(crs, "EPSG:4326", list(xs), list(ys))
    return [[lon, lat] for lon, lat in zip(lons, lats)]


def _stretch(band: np.ndarray, low: float = 2.0, high: float = 98.0) -> np.ndarray:
    """Percentile contrast stretch. Raw reflectance renders almost black otherwise."""
    finite = band[np.isfinite(band) & (band > 0)]
    if finite.size == 0:
        return np.zeros_like(band, dtype=np.uint8)
    lo, hi = np.percentile(finite, [low, high])
    if hi <= lo:
        hi = lo + 1e-6
    return (np.clip((band - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)


def write_rgb(tensor: np.ndarray, job_id: str) -> str:
    """True-colour preview of the input: B04 (red), B03 (green), B02 (blue)."""
    rgb = np.dstack([_stretch(tensor[2]), _stretch(tensor[1]), _stretch(tensor[0])])
    path = path_for(job_id, "input")
    Image.fromarray(rgb, mode="RGB").save(path, optimize=True)
    return path


def write_classes(classes: np.ndarray, job_id: str) -> str:
    """Thematic map coloured by class, with nodata left fully transparent."""
    h, w = classes.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    for idx, colour in CLASS_COLORS.items():
        hit = classes == idx
        rgba[hit, :3] = colour
        rgba[hit, 3] = 255
    path = path_for(job_id, "output")
    Image.fromarray(rgba, mode="RGBA").save(path, optimize=True)
    return path


def urls_for(job_id: str) -> Dict[str, str]:
    return {
        "input_preview_url": f"/api/v1/jobs/{job_id}/preview/input.png",
        "output_preview_url": f"/api/v1/jobs/{job_id}/preview/output.png",
    }
