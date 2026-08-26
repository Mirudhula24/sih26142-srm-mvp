"""SpatioTemporal Asset Catalog ingestion for Sentinel-2 Level-2A granules.

Reads COG assets over HTTP range requests, so only the AOI window is transferred —
full granules are never downloaded.
"""
from typing import Dict, List, Optional

import planetary_computer as pc
import rasterio
from pystac_client import Client

from config import INPUT_BANDS, get_settings

_ASSET_KEYS = INPUT_BANDS + ["SCL"]


MAX_AOI_DEGREES = 0.5  # ~50 km x 50 km (5000 x 5000 pixels at 10 m resolution)


def validate_aoi_bbox(bbox: List[float]) -> None:
    """Ensure the AOI bounding box is within safe memory limits (~50 km x 50 km)."""
    min_lon, min_lat, max_lon, max_lat = bbox
    width_deg = abs(max_lon - min_lon)
    height_deg = abs(max_lat - min_lat)
    if width_deg > MAX_AOI_DEGREES or height_deg > MAX_AOI_DEGREES:
        raise ValueError(
            f"Area of Interest (AOI) bounding box is too large ({width_deg:.2f}° × {height_deg:.2f}°). "
            f"Maximum allowed size is {MAX_AOI_DEGREES}° × {MAX_AOI_DEGREES}° (~50 km × 50 km). "
            f"Please select or draw a smaller region."
        )


def bbox_from_polygon(geojson: Dict) -> List[float]:
    """[min_lon, min_lat, max_lon, max_lat] from a GeoJSON Polygon."""
    ring = geojson["coordinates"][0]
    lons = [pt[0] for pt in ring]
    lats = [pt[1] for pt in ring]
    bbox = [min(lons), min(lats), max(lons), max(lats)]
    validate_aoi_bbox(bbox)
    return bbox


def search_best_scene(
    bbox: List[float],
    date_range: str = "2025-01-01/2026-03-01",
    max_cloud: Optional[float] = None,
) -> Dict:
    """Return the least-cloudy L2A scene intersecting `bbox` with its COG asset hrefs."""
    settings = get_settings()
    max_cloud = settings.max_cloud_cover if max_cloud is None else max_cloud

    catalog = Client.open(settings.stac_endpoint, modifier=pc.sign_inplace)
    search = catalog.search(
        collections=[settings.stac_collection],
        bbox=bbox,
        datetime=date_range,
        query={"eo:cloud_cover": {"lt": max_cloud}},
    )

    items = list(search.item_collection())
    if not items:
        raise ValueError("No matching satellite granules for the given AOI and filters.")

    best = min(items, key=lambda item: item.properties["eo:cloud_cover"])
    band_urls = {key: best.assets[key].href for key in _ASSET_KEYS if key in best.assets}

    # Affine/CRS metadata comes from a native 10 m band; everything is resampled onto it.
    with rasterio.open(band_urls["B04"]) as src:
        meta = {
            "crs": src.crs.to_string(),
            "transform": list(src.transform),
            "height": src.height,
            "width": src.width,
        }

    return {
        "scene_id": best.id,
        "cloud_cover": float(best.properties["eo:cloud_cover"]),
        "acquired": best.properties.get("datetime"),
        "band_urls": band_urls,
        "preview_url": best.assets["rendered_preview"].href
        if "rendered_preview" in best.assets
        else None,
        "meta": meta,
        "bbox": bbox,
    }
