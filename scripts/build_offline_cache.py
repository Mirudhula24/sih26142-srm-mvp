"""Pre-cache Sentinel-2 granules for the three demo regions.

Run this before the event. Without it, a dead venue network kills the demo.

    python scripts/build_offline_cache.py --regions delhi_ncr kerala_coastal rajasthan_arid
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from services.offline_cache import CACHED_REGIONS  # noqa: E402
from services.stac_fetcher import search_best_scene  # noqa: E402


def cache_region(key: str, out_root: str, date_range: str, max_cloud: float) -> None:
    region = CACHED_REGIONS[key]
    out_dir = os.path.join(out_root, key)
    os.makedirs(out_dir, exist_ok=True)

    print(f"[{key}] querying STAC for {region['label']}…")
    scene = search_best_scene(region["bbox"], date_range=date_range, max_cloud=max_cloud)

    manifest = {
        "scene_id": scene["scene_id"],
        "cloud_cover": scene["cloud_cover"],
        "acquired": scene["acquired"],
        "bbox": region["bbox"],
        "band_urls": scene["band_urls"],
        "preview_url": scene["preview_url"],
        "meta": scene["meta"],
    }
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    print(f"[{key}] cached {scene['scene_id']} ({scene['cloud_cover']:.1f}% cloud)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regions", nargs="*", default=list(CACHED_REGIONS))
    parser.add_argument("--out", default="data_cache")
    parser.add_argument("--date-range", default="2025-10-01/2026-03-01")
    parser.add_argument("--max-cloud", type=float, default=5.0)
    args = parser.parse_args()

    for key in args.regions:
        if key not in CACHED_REGIONS:
            print(f"Unknown region '{key}'; known: {list(CACHED_REGIONS)}", file=sys.stderr)
            return 1
        cache_region(key, args.out, args.date_range, args.max_cloud)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
