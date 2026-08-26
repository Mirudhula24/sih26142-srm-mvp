"""Offline demo fallback — pre-cached granules for three representative biomes.

Used when the STAC query times out (venue Wi-Fi failure) or when OFFLINE_MODE=true.
"""
import json
import os
from typing import Dict, List, Optional

from config import get_settings

CACHED_REGIONS = {
    "delhi_ncr": {"label": "Delhi NCR — urban / industrial", "bbox": [76.84, 28.40, 77.35, 28.88]},
    "kerala_coastal": {"label": "Kerala — coastal / water", "bbox": [75.75, 9.90, 76.40, 10.45]},
    "rajasthan_arid": {"label": "Rajasthan — arid / bare soil", "bbox": [72.80, 26.10, 73.40, 26.60]},
}


def _bbox_intersects(a: List[float], b: List[float]) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def list_regions() -> List[Dict]:
    return [{"key": k, **v} for k, v in CACHED_REGIONS.items()]


def nearest_cached_scene(bbox: List[float]) -> Optional[Dict]:
    """Pick the cached region covering `bbox`, else the first available cache."""
    settings = get_settings()
    candidates = [k for k, v in CACHED_REGIONS.items() if _bbox_intersects(bbox, v["bbox"])]
    candidates += [k for k in CACHED_REGIONS if k not in candidates]

    for key in candidates:
        manifest = os.path.join(settings.data_cache_dir, key, "manifest.json")
        if os.path.exists(manifest):
            with open(manifest, encoding="utf-8") as fh:
                data = json.load(fh)
            data.setdefault("cloud_cover", 0.0)
            data["region"] = key
            return data
    return None
