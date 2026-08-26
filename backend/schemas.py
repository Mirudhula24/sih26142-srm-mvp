"""Pydantic request/response contracts for the REST API."""
from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from config import LAND_COVER_CLASSES


class DateRange(BaseModel):
    start: str = Field(..., examples=["2026-01-01"])
    end: str = Field(..., examples=["2026-03-01"])


class GeoJSONPolygon(BaseModel):
    type: Literal["Polygon"] = "Polygon"
    coordinates: List[List[List[float]]]


class FetchRequest(BaseModel):
    aoi_geojson: GeoJSONPolygon
    max_cloud_cover: float = Field(10.0, ge=0.0, le=100.0)
    date_range: DateRange


class FetchResponse(BaseModel):
    status: Literal["SUCCESS", "FALLBACK_CACHE"]
    granule_id: str
    cloud_cover: float
    bands_available: List[str]
    preview_url: Optional[str] = None


class SRMRequest(BaseModel):
    granule_id: str
    # Optional: the gateway falls back to the bbox recorded during /imagery/fetch.
    aoi_geojson: Optional[GeoJSONPolygon] = None
    max_cloud_cover: Optional[float] = Field(None, ge=0.0, le=100.0)
    scale_factor: Literal[4, 8] = 4
    target_classes: List[str] = Field(default_factory=lambda: list(LAND_COVER_CLASSES))
    apply_mrf_smoothing: bool = True


class SRMResponse(BaseModel):
    job_id: str
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED"]
    # Where the imagery came from: a live STAC query or the local demo cache. Surfaced so
    # the UI can never present cached imagery as a fresh acquisition.
    data_source: Optional[Literal["stac", "cache"]] = None
    granule_id: Optional[str] = None
    cloud_cover: Optional[float] = None
    error: Optional[str] = None
    mass_conservation_error: Optional[float] = None
    fine_pixel_size_m: Optional[float] = None
    # Corner coordinates (tl, tr, br, bl) for the map overlays used without TiTiler.
    bounds: Optional[List[List[float]]] = None
    input_preview_url: Optional[str] = None
    output_preview_url: Optional[str] = None
    execution_time_seconds: Optional[float] = None
    cog_output_url: Optional[str] = None
    tile_url_template: Optional[str] = None
    class_distribution_percent: Optional[Dict[str, float]] = None
    class_area_sqm: Optional[Dict[str, float]] = None
    miou_score: Optional[float] = None
    created_at: Optional[datetime] = None
