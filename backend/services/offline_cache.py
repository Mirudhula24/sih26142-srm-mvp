"""Offline demo fallback — pre-cached granules for three representative biomes.

Used when the STAC query times out (venue Wi-Fi failure) or when OFFLINE_MODE=true.
Populate with `python scripts/build_offline_cache.py` before the event.
"""
import json
import os
from typing import Dict, List, Optional

from config import get_settings

CACHED_REGIONS = {
    "delhi_ncr": {"label": "Delhi NCR — urban / industrial", "bbox": [76.84, 28.40, 77.35, 28.88]},
    "kerala_coastal": {"label": "Kerala — coastal / water", "bbox": [75.75, 9.90, 76.40, 10.45]},
    "rajasthan_arid": {"label": "Rajasthan — arid / bare soil", "bbox": [72.80, 26.10, 73.40, 26.60]},
    # The other three regions all fall in UTM 43N. Chennai sits in 44N, so it is the
    # only cached scene that exercises a second CRS end to end -- reprojection bugs are
    # invisible until a granule crosses zones.
    "chennai_coastal": {"label": "Chennai — coastal / port / urban", "bbox": [80.15, 12.90, 80.35, 13.15]},
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
        region_dir = os.path.join(settings.data_cache_dir, key)
        manifest = os.path.join(region_dir, "manifest.json")
        if os.path.exists(manifest):
            with open(manifest, encoding="utf-8") as fh:
                data = json.load(fh)
            data.setdefault("cloud_cover", 0.0)
            data["region"] = key
            data["region_dir"] = region_dir
            return data
    return None


def band_sources(cached: Dict) -> Dict[str, str]:
    """Resolve a cached manifest to something rasterio can open.

    Prefers `band_files` — GeoTIFFs on local disk, which is what makes offline mode
    genuinely offline. Falls back to the remote `band_urls` recorded in the manifest,
    which still saves the STAC round-trip but needs the network.
    """
    files = cached.get("band_files")
    if files:
        region_dir = cached.get("region_dir", "")
        resolved = {
            band: path if os.path.isabs(path) else os.path.join(region_dir, path)
            for band, path in files.items()
        }
        if all(os.path.exists(p) for p in resolved.values()):
            return resolved

    urls = cached.get("band_urls")
    if not urls:
        raise RuntimeError(
            f"Cache for {cached.get('region')} has neither local band files nor band "
            f"URLs. Re-run scripts/build_offline_cache.py."
        )
    return urls
