"""Derive endmember spectra from imagery instead of literature values.

Hand-picked spectra are defensible but generic: they describe concrete and soil in
general, not the concrete and soil of this sensor, this atmosphere, this region. This
fits each endmember to the median spectrum of pixels that ESA WorldCover labels as that
class, using only pixels whose 3x3 neighbourhood is homogeneous -- a mixed pixel would
drag the endmember toward its neighbours, which is exactly what an endmember must not be.

Fit on one region, validate on another. Fitting and scoring on the same area would be
circular and the resulting number meaningless.

    python scripts/fit_endmembers.py --fit-bbox 80.15 13.03 80.25 13.13
"""
import argparse
import os
import sys

import numpy as np
import rasterio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ml_engine"))

from services.preprocessor import build_input_tensor  # noqa: E402
from services.stac_fetcher import search_best_scene  # noqa: E402
from validate import WORLDCOVER_TO_MERGED, fetch_worldcover  # noqa: E402

# WorldCover code -> our class, for the classes it can actually speak to. Road and sand
# have no counterpart, so they keep their literature spectra.
WC_TO_OURS = {
    50: "built_up",
    80: "water",
    10: "vegetation",
    40: "cropland",
    60: "bare_soil",
}


def homogeneous(mask, min_neighbours=8):
    """True where a pixel and essentially all of its 8 neighbours share the label."""
    from scipy.ndimage import uniform_filter

    frac = uniform_filter(mask.astype(np.float32), size=3, mode="nearest")
    return mask & (frac >= min_neighbours / 9.0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fit-bbox", nargs=4, type=float, required=True)
    ap.add_argument("--max-px", type=int, default=400)
    args = ap.parse_args()

    bbox = args.fit_bbox
    scene = search_best_scene(bbox, max_cloud=15)
    prep = build_input_tensor(scene["band_urls"], bbox, boa_offset=scene["boa_offset"])
    x = prep["tensor"][:, : args.max_px, : args.max_px]
    valid = prep["valid_mask"][: args.max_px, : args.max_px]
    h, w = x.shape[1], x.shape[2]

    ref = fetch_worldcover(bbox, (h, w), prep["crs"], prep["transform"])
    print(f"fit scene {scene['scene_id']}   tile {h}x{w}\n")

    for code, name in WC_TO_OURS.items():
        mask = (ref == code) & valid
        pure = homogeneous(mask)
        n = int(pure.sum())
        if n < 40:
            print(f"  {name:12s} only {n} pure pixels - keeping literature spectrum")
            continue
        med = np.median(x[:, pure], axis=1)
        print(f'    ("{name} (fitted)", [' +
              ", ".join(f"{v:.3f}" for v in med) + f'], "{name}"),   # n={n}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
