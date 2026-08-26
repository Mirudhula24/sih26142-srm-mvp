"""Read-side export helpers: vectorisation, class-area analytics, CSV reports.

COGs are written by the GPU worker (ml_engine/utils/cog_writer.py) -- that is where the
class map is produced. This module only reads them back.
"""
import csv
import os
from typing import Dict, List, Optional

import numpy as np
import rasterio
from rasterio.features import shapes
from shapely.geometry import mapping, shape

from config import LAND_COVER_CLASSES, get_settings

def cog_path_for_job(job_id: str) -> Optional[str]:
    path = os.path.join(get_settings().cog_storage_dir, f"{job_id}.tif")
    return path if os.path.exists(path) else None


def class_metrics(classes: np.ndarray, pixel_size_m: float) -> Dict[str, Dict[str, float]]:
    """Sub-pixel counts -> area in m2/hectares and percentage distribution."""
    cell_area = pixel_size_m ** 2
    total = int(np.count_nonzero(classes != 255))
    out: Dict[str, Dict[str, float]] = {}
    for idx, name in enumerate(LAND_COVER_CLASSES):
        count = int(np.count_nonzero(classes == idx))
        out[name] = {
            "sub_pixels": count,
            "area_sqm": count * cell_area,
            "area_hectares": count * cell_area / 10_000.0,
            "percent": round(100.0 * count / total, 2) if total else 0.0,
        }
    return out


def vectorise_job(job_id: str, simplify_tolerance: float = 2.0) -> Optional[Dict]:
    """Raster -> simplified GeoJSON FeatureCollection of class boundary polygons."""
    path = cog_path_for_job(job_id)
    if path is None:
        return None

    features: List[Dict] = []
    with rasterio.open(path) as src:
        band = src.read(1)
        for geom, value in shapes(band, mask=(band != 255), transform=src.transform):
            if int(value) >= len(LAND_COVER_CLASSES):
                continue
            poly = shape(geom).simplify(simplify_tolerance, preserve_topology=True)
            if poly.is_empty:
                continue
            features.append(
                {
                    "type": "Feature",
                    "geometry": mapping(poly),
                    "properties": {
                        "class_id": int(value),
                        "class_name": LAND_COVER_CLASSES[int(value)],
                    },
                }
            )
        crs = src.crs.to_string()

    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": crs}},
        "features": features,
    }


def class_metrics_csv(job_id: str) -> Optional[str]:
    path = cog_path_for_job(job_id)
    if path is None:
        return None
    with rasterio.open(path) as src:
        classes = src.read(1)
        pixel_size = abs(src.transform.a)
    metrics = class_metrics(classes, pixel_size)

    csv_path = os.path.join(get_settings().cog_storage_dir, f"{job_id}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["class", "sub_pixels", "area_sqm", "area_hectares", "percent"])
        for name, m in metrics.items():
            writer.writerow(
                [name, m["sub_pixels"], m["area_sqm"], m["area_hectares"], m["percent"]]
            )
    return csv_path
