"""Band alignment, cloud masking and normalisation.

Produces the aligned multispectral tensor X of shape (B=6, H, W) on the 10 m grid,
which is the sole input contract of the inference engine.
"""
from typing import Dict, List, Tuple

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

from config import INPUT_BANDS

# Sentinel-2 Scene Classification Layer codes that must never reach the network.
SCL_INVALID = {0, 1, 3, 8, 9, 10, 11}  # nodata, saturated, shadow, cloud med/high, cirrus, snow
REFLECTANCE_SCALE = 10_000.0


def _read_window(
    href: str,
    bbox_wgs84: List[float],
    out_shape: Tuple[int, int] = None,
    resampling: Resampling = Resampling.bilinear,
):
    with rasterio.open(href) as src:
        left, bottom, right, top = transform_bounds("EPSG:4326", src.crs, *bbox_wgs84)
        window = from_bounds(left, bottom, right, top, src.transform)
        shape = out_shape or (int(window.height), int(window.width))
        data = src.read(
            1,
            window=window,
            out_shape=shape,
            # Bilinear for continuous reflectance -- a rasterio-native stand-in for the
            # guided-filter upsampling of the 20 m SWIR channels, which keeps band
            # registration exact. Categorical rasters MUST override this; see the SCL
            # read in build_input_tensor.
            resampling=resampling,
        )
        return data, src.window_transform(window), src.crs


def build_input_tensor(band_urls: Dict[str, str], bbox_wgs84: List[float]) -> Dict:
    """Read every band over the AOI, align to the 10 m grid, mask clouds, normalise."""
    ref, transform, crs = _read_window(band_urls["B04"], bbox_wgs84)
    height, width = ref.shape

    stack = []
    for band in INPUT_BANDS:
        data, _, _ = _read_window(band_urls[band], bbox_wgs84, out_shape=(height, width))
        stack.append(data.astype(np.float32) / REFLECTANCE_SCALE)
    x = np.stack(stack, axis=0)

    valid = np.ones((height, width), dtype=bool)
    if "SCL" in band_urls:
        # Nearest, never bilinear: SCL holds categorical class codes, and interpolating
        # them invents values that exist in no class. Cloud (9) beside vegetation (4)
        # would average to 6 -- read as "water", and the cloud silently escapes the mask.
        scl, _, _ = _read_window(
            band_urls["SCL"],
            bbox_wgs84,
            out_shape=(height, width),
            resampling=Resampling.nearest,
        )
        valid = ~np.isin(scl.astype(np.uint8), list(SCL_INVALID))

    x = np.clip(x, 0.0, 1.0)
    x[:, ~valid] = 0.0

    return {
        "tensor": x,                       # (6, H, W) float32 in [0, 1]
        "valid_mask": valid,               # (H, W) bool
        "transform": transform,
        "crs": crs.to_string(),
        "valid_fraction": float(valid.mean()),
    }
