"""Measure classification accuracy against ESA WorldCover 10 m.

Until this exists, every accuracy figure in the PRD is an assertion. This turns it into
a measurement:

    python scripts/validate.py --bbox 80.26 13.02 80.30 13.06
    python scripts/validate.py --preset chennai_coast marina inland_urban

What is being compared, and what that is worth
----------------------------------------------
WorldCover is itself a model output at 10 m, not survey truth, and its legend does not
match ours. Two consequences that must be stated with any number this prints:

  * It has no road class. Roads are folded into built-up on both sides before scoring,
    so this measures built-up-including-roads, and says nothing about how well road is
    separated from building.
  * It has no sand class; beach and dune fall under its bare/sparse vegetation. Sand is
    likewise folded into bare_soil.
  * Grassland and shrubland have no clean counterpart in our legend. They are mapped to
    cropland and vegetation respectively, which is a judgement call, not a fact.

So this is agreement with an independent 10 m product over five merged classes. It is not
sub-pixel validation: proving the 2.5 m detail is correct needs sub-metre reference
imagery, which is the next piece of work.

Measured results, Chennai, five AOIs, classical solver (2026-08-27)
-------------------------------------------------------------------
    open sea        overall 90.5%   mIoU 0.393   water IoU 0.972
    marina          overall 22.8%   mIoU 0.089
    inland urban    overall 29.3%   mIoU 0.138
    mean            overall 47.5%   mIoU 0.206

Against the PRD target of mIoU >= 0.70, that target is NOT met and must not be quoted as
if it were. Two things are known about why, and a third is not:

  * The validator itself was wrong first time. WorldCover is EPSG:4326 and the imagery is
    UTM; reading the same bounding box into the same array shape is not alignment. Fixing
    it to a real reprojection roughly doubled every score. Any accuracy claim is only as
    trustworthy as the harness producing it.
  * Urban is where it fails. Bare soil is heavily over-predicted where WorldCover says
    built-up, which is the known concrete-versus-soil confusion: their spectra differ by
    less than the within-class variation of either.
  * What is NOT established: in these dry-season scenes, pixels WorldCover labels tree
    cover show NDVI ~0.22 against built-up at ~0.23 -- no separation at all, while water
    separates cleanly at -0.14. That is consistent with genuine spectral overlap in a dry
    urban landscape, and also with a residual sub-pixel misregistration that this check
    could not isolate. Until that is settled, treat the urban numbers as a lower bound
    rather than a measurement.

What is safe to state: water is recovered at IoU 0.97 on open sea, mass conservation
holds at ~1e-7, and the coastal results are visually correct. Everything else is an open
question, which is a normal state for a 48-hour build and a better position than an
unbacked 0.70.
"""
import argparse
import os
import sys

import numpy as np
import planetary_computer as pc
import rasterio
import torch
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import from_bounds

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ml_engine"))

from models.classical_srm import super_resolve  # noqa: E402
from services.preprocessor import build_input_tensor  # noqa: E402
from services.stac_fetcher import search_best_scene  # noqa: E402
from taxonomy import CLASSES  # noqa: E402

# Merged legend used for scoring, since neither product can express the other exactly.
MERGED = ["built_up", "water", "vegetation", "cropland", "bare_soil"]

# Ours -> merged.
OURS_TO_MERGED = {
    "built_up": "built_up",
    "road": "built_up",      # WorldCover has no road class
    "water": "water",
    "vegetation": "vegetation",
    "cropland": "cropland",
    "bare_soil": "bare_soil",
    "sand": "bare_soil",     # WorldCover has no sand class
}

# ESA WorldCover code -> merged. Judgement calls are flagged in the docstring.
WORLDCOVER_TO_MERGED = {
    10: "vegetation",   # tree cover
    20: "vegetation",   # shrubland
    30: "cropland",     # grassland
    40: "cropland",     # cropland
    50: "built_up",     # built-up
    60: "bare_soil",    # bare / sparse vegetation
    70: None,           # snow and ice
    80: "water",        # permanent water
    90: "water",        # herbaceous wetland
    95: "vegetation",   # mangroves
    100: "cropland",    # moss and lichen
}

PRESETS = {
    "chennai_coast": [80.26, 13.04, 80.30, 13.08],
    "marina": [80.26, 13.03, 80.29, 13.06],
    "inland_urban": [80.20, 12.98, 80.23, 13.01],
    "arterial": [80.15, 13.03, 80.19, 13.07],
    "open_sea": [80.28, 13.02, 80.32, 13.06],
}


def fetch_worldcover(bbox, shape, dst_crs, dst_transform):
    """Read WorldCover and reproject it onto our exact grid.

    WorldCover is stored in EPSG:4326; our tensor is in the granule's UTM zone. Reading
    the same bounding box and squeezing it to the same array shape is NOT alignment --
    the two grids are differently projected, so pixels do not correspond and every score
    comes out spuriously low. The comparison has to go through a real reprojection.
    """
    cat = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1",
                      modifier=pc.sign_inplace)
    items = list(cat.search(collections=["esa-worldcover"], bbox=bbox).item_collection())
    if not items:
        raise RuntimeError("No WorldCover tile covers this AOI.")
    href = max(items, key=lambda i: i.properties["start_datetime"]).assets["map"].href

    out = np.zeros(shape, dtype=np.uint8)
    with rasterio.open(href) as src:
        left, bottom, right, top = transform_bounds("EPSG:4326", src.crs, *bbox)
        window = from_bounds(left, bottom, right, top, src.transform)
        # Pad the read so reprojection has data at the edges.
        window = window.round_offsets().round_lengths()
        data = src.read(1, window=window, boundless=True, fill_value=0)
        reproject(
            source=data,
            destination=out,
            src_transform=src.window_transform(window),
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            # Nearest: these are class codes, and interpolating them invents classes.
            resampling=Resampling.nearest,
        )
    return out


def score(pred, truth, labels):
    """Confusion matrix, per-class IoU, mIoU and overall accuracy."""
    n = len(labels)
    valid = (pred >= 0) & (truth >= 0)
    p, t = pred[valid], truth[valid]
    cm = np.zeros((n, n), dtype=np.int64)
    np.add.at(cm, (t, p), 1)

    ious, present = [], []
    for i in range(n):
        inter = cm[i, i]
        union = cm[i, :].sum() + cm[:, i].sum() - inter
        if cm[i, :].sum() > 0:          # class present in the reference
            ious.append(inter / union if union else 0.0)
            present.append(labels[i])
    overall = np.trace(cm) / cm.sum() if cm.sum() else 0.0
    return cm, dict(zip(present, ious)), float(np.mean(ious)) if ious else 0.0, overall


def evaluate(bbox, scale_factor=4, max_px=192):
    scene = search_best_scene(bbox, max_cloud=20)
    prep = build_input_tensor(scene["band_urls"], bbox, boa_offset=scene["boa_offset"])
    tensor = prep["tensor"][:, :max_px, :max_px]
    valid = prep["valid_mask"][:max_px, :max_px]

    _, fine = super_resolve(torch.from_numpy(tensor), scale_factor=scale_factor)
    fine = fine.cpu().numpy()

    # Aggregate our sub-pixel map back to the 10 m grid by majority vote, so the
    # comparison happens at the resolution the reference actually has.
    h, w = tensor.shape[1], tensor.shape[2]
    s = scale_factor
    blocks = fine.reshape(h, s, w, s).transpose(0, 2, 1, 3).reshape(h, w, s * s)
    counts = np.zeros((h, w, len(CLASSES)), dtype=np.int16)
    for c in range(len(CLASSES)):
        counts[:, :, c] = (blocks == c).sum(axis=2)
    coarse = counts.argmax(axis=2)

    ref = fetch_worldcover(bbox, (h, w), prep["crs"], prep["transform"])

    ours = np.full((h, w), -1, dtype=np.int8)
    truth = np.full((h, w), -1, dtype=np.int8)
    for i, name in enumerate(CLASSES):
        ours[coarse == i] = MERGED.index(OURS_TO_MERGED[name])
    for code, name in WORLDCOVER_TO_MERGED.items():
        if name is not None:
            truth[ref == code] = MERGED.index(name)
    ours[~valid] = -1
    truth[~valid] = -1

    return score(ours, truth, MERGED) + (scene["scene_id"],)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bbox", nargs=4, type=float, metavar=("W", "S", "E", "N"))
    ap.add_argument("--preset", nargs="*", default=None, choices=list(PRESETS))
    ap.add_argument("--scale", type=int, default=4)
    args = ap.parse_args()

    targets = {}
    if args.bbox:
        targets["custom"] = args.bbox
    for name in args.preset or ([] if args.bbox else list(PRESETS)):
        targets[name] = PRESETS[name]

    mious, accs = [], []
    for name, bbox in targets.items():
        try:
            cm, ious, miou, overall, scene = evaluate(bbox, args.scale)
        except Exception as exc:  # noqa: BLE001
            print(f"\n{name}: FAILED — {exc}")
            continue
        mious.append(miou)
        accs.append(overall)
        print(f"\n=== {name}  {bbox}")
        print(f"    granule {scene}")
        print(f"    overall accuracy {overall * 100:5.1f}%     mIoU {miou:.3f}")
        for cls, iou in sorted(ious.items(), key=lambda kv: -kv[1]):
            print(f"      {cls:12s} IoU {iou:.3f}")

    if mious:
        print(f"\n--- across {len(mious)} AOIs: mean mIoU {np.mean(mious):.3f}, "
              f"mean overall accuracy {np.mean(accs) * 100:.1f}%")
        print("Reference: ESA WorldCover 10 m, five merged classes. "
              "Road and sand are folded in; see the module docstring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
