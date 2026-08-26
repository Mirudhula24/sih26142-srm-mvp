"""Pre-cache Sentinel-2 granules for the three demo regions.

Run this before the event. Without it, a dead venue network kills the demo.

By default it downloads the actual band windows to local GeoTIFFs, which is what makes
offline mode genuinely offline. Pass --manifest-only to record STAC hrefs without
downloading (faster, but still needs the network at demo time).

    python scripts/build_offline_cache.py
    python scripts/build_offline_cache.py --regions delhi_ncr --demo-size 0.05
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import rasterio  # noqa: E402
from rasterio.warp import transform_bounds  # noqa: E402
from rasterio.windows import from_bounds  # noqa: E402

from services.offline_cache import CACHED_REGIONS  # noqa: E402
from services.stac_fetcher import search_best_scene  # noqa: E402


def demo_bbox(bbox, size_deg):
    """Shrink a region bbox to a demo-sized window at its centre.

    A whole Sentinel-2 region is gigabytes; the demo only ever looks at a few km.
    """
    cx = (bbox[0] + bbox[2]) / 2
    cy = (bbox[1] + bbox[3]) / 2
    h = size_deg / 2
    return [cx - h, cy - h, cx + h, cy + h]


def download_band(href, out_path, bbox_wgs84):
    """Copy just the AOI window of one band to a local GeoTIFF."""
    with rasterio.open(href) as src:
        left, bottom, right, top = transform_bounds("EPSG:4326", src.crs, *bbox_wgs84)
        window = from_bounds(left, bottom, right, top, src.transform)
        data = src.read(1, window=window)
        profile = src.profile.copy()
        profile.update(
            height=data.shape[0],
            width=data.shape[1],
            transform=src.window_transform(window),
            driver="GTiff",
            compress="deflate",
        )
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(data, 1)
    return os.path.getsize(out_path)


def cache_region(key, out_root, date_range, max_cloud, size_deg, manifest_only):
    region = CACHED_REGIONS[key]
    out_dir = os.path.join(out_root, key)
    os.makedirs(out_dir, exist_ok=True)

    window_bbox = demo_bbox(region["bbox"], size_deg)
    print(f"[{key}] querying STAC for {region['label']}...")
    scene = search_best_scene(window_bbox, date_range=date_range, max_cloud=max_cloud)

    manifest = {
        "scene_id": scene["scene_id"],
        "cloud_cover": scene["cloud_cover"],
        "boa_offset": scene["boa_offset"],
        "processing_baseline": scene["processing_baseline"],
        "acquired": scene["acquired"],
        "bbox": window_bbox,
        "region_bbox": region["bbox"],
        "band_urls": scene["band_urls"],
        "preview_url": scene["preview_url"],
        "meta": scene["meta"],
    }

    if not manifest_only:
        band_files, total = {}, 0
        for band, href in scene["band_urls"].items():
            filename = f"{band}.tif"
            size = download_band(href, os.path.join(out_dir, filename), window_bbox)
            band_files[band] = filename
            total += size
            print(f"    {band}: {size / 1e6:.1f} MB")
        manifest["band_files"] = band_files
        print(f"[{key}] {total / 1e6:.1f} MB on disk")

    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    print(f"[{key}] cached {scene['scene_id']} ({scene['cloud_cover']:.1f}% cloud)\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regions", nargs="*", default=list(CACHED_REGIONS))
    parser.add_argument("--out", default="data_cache")
    parser.add_argument("--date-range", default="2025-10-01/2026-03-01")
    parser.add_argument("--max-cloud", type=float, default=5.0)
    parser.add_argument("--demo-size", type=float, default=0.05,
                        help="Side length in degrees of the cached window (~5 km).")
    parser.add_argument("--manifest-only", action="store_true",
                        help="Record STAC hrefs without downloading the bands.")
    args = parser.parse_args()

    for key in args.regions:
        if key not in CACHED_REGIONS:
            print(f"Unknown region '{key}'; known: {list(CACHED_REGIONS)}", file=sys.stderr)
            return 1
        cache_region(key, args.out, args.date_range, args.max_cloud,
                     args.demo_size, args.manifest_only)

    print("Cache ready. Set OFFLINE_MODE=true to force the demo through it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
