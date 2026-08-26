# Product Requirements Document — GeoSRM Engine

| | |
|---|---|
| Problem statement | SIH26142 — Deep Learning Based Super-Resolution Mapping from Medium-Resolution Satellite Imagery |
| Sponsoring agency | National Technical Research Organisation (NTRO) |
| Theme | Space Technology / Software |
| Team size | 6 (SIH cap) |
| Target output | 4x sub-pixel thematic land-cover maps — 2.5 m from 10 m Sentinel-2 |
| Version | 1.0 |

## 1. Executive summary

Sentinel-2 gives broad coverage and a fast revisit cycle, but at 10–20 m each pixel
blends several surface types. Commercial sub-metre VHR resolves that, at significant
cost and with narrow swaths.

This platform does Super-Resolution Mapping, not perceptual upscaling. It unmixes the
coarse multispectral signal into fractional class abundances and allocates discrete
thematic classes onto a finer sub-pixel grid, delivering 2.5 m thematic maps to defence
intelligence analysts and geospatial researchers from free imagery.

## 2. Problem framing

- **Problem.** Coarse mixed pixels obscure narrow linear structures (access roads,
  fencing) and small assets (coastal facilities, isolated buildings).
- **Root cause.** Optical sensors integrate radiance over a large ground sampling
  distance, blending distinct spectral signatures into one composite response.
- **Solution.** A dual-stage pipeline: a spectral unmixing network followed by a
  transformer-based spatial allocation network, at a 4x scaling factor.

### Mathematical constraints

For input `X` of shape `(H, W, B)` and output `Y` of shape `(H*S, W*S)` over `C` classes:

```
Abundance:   A[i,j,c] >= 0,   sum_c A[i,j,c] = 1
Allocation:  N[i,j,c] = round(A[i,j,c] * S^2),   sum_c N[i,j,c] = S^2
Energy:      minimise  E = -sum_a sum_{b in N8(a)} w_ab * delta(L_a, L_b),  w_ab = 1/d(a,b)
```

## 3. Personas

**Defence GEOINT analyst (NTRO).** Monitors strategic sites, extracts building
footprints, spots road-network changes from routine public passes. Blocked today by
error-prone interpretation of 10 m pixels and multi-day VHR tasking approvals. Needs
inference in under 10 s, side-by-side comparison, reliable feature extraction.

**Remote sensing scientist / GIS developer.** Runs land-cover change analytics, exports
sub-pixel rasters into QGIS/ArcGIS. Blocked by non-georeferenced model outputs and
generative models that invent features. Needs georeferenced COG downloads and verifiable
area metrics.

## 4. End-to-end flow

1. Log in, define an AOI by bounding box or GeoJSON upload.
2. System queries STAC APIs for the latest cloud-free Sentinel-2 L2A granules.
3. Resample 20 m SWIR to the 10 m grid, apply cloud masks, normalise reflectance.
4. Run 4x SRM inference — unmix, then allocate sub-pixel classes.
5. Compare in a synchronised dual canvas with a swipe slider.
6. Export GeoTIFF / GeoJSON plus a CSV land-cover report.

## 5. Functional requirements

| ID | Priority | Feature | Acceptance |
|---|---|---|---|
| FR-01 | P0 | STAC satellite ingestion | Fetch completes < 5 s for AOIs up to 10x10 km |
| FR-02 | P0 | Band alignment & masking | Zero spatial offset across channels |
| FR-03 | P0 | 4x deep learning SRM | < 8 s GPU per tile; mIoU >= 0.70 |
| FR-04 | P0 | Synchronised dual canvas | >= 45 FPS on standard client browsers |
| FR-05 | P0 | GeoTIFF export | Opens in QGIS with valid affine transform |
| FR-06 | P0 | Class abundance analytics | Class areas sum to 100% of the AOI |
| FR-07 | P1 | Offline fallback | One-click switch from live API to local disk |
| FR-08 | P1 | Vector boundary extraction | GeoJSON polygons in < 3 s for the canvas view |
| FR-09 | P2 | 8x upscaling mode | Enabled only if VRAM permits |
| FR-10 | P2 | Temporal change detection | Deferred post-hackathon |

## 6. Non-functional requirements

- **Latency.** 256x256 coarse tile in < 8 s on a T4 or RTX 3090. Tile serving < 300 ms.
- **Accuracy.** mIoU >= 0.70 across the five classes; overall sub-pixel accuracy measured
  against ESA WorldCover / downsampled VHR. Mass conservation error below 1e-3.
- **Hardware.** 8 GB VRAM or less, so the engine stays edge-deployable.
- **Deployment.** Whole platform launches with one `docker compose up --build`.

## 7. API contracts

### POST /api/v1/imagery/fetch

Request:

```json
{
  "aoi_geojson": {
    "type": "Polygon",
    "coordinates": [[[77.102, 28.704], [77.115, 28.704], [77.115, 28.715], [77.102, 28.715], [77.102, 28.704]]]
  },
  "max_cloud_cover": 10.0,
  "date_range": {"start": "2026-01-01", "end": "2026-03-01"}
}
```

Response:

```json
{
  "status": "SUCCESS",
  "granule_id": "S2A_MSIL2A_20260215_T43REQ",
  "cloud_cover": 3.1,
  "bands_available": ["B02", "B03", "B04", "B08", "B11", "B12"],
  "preview_url": "https://.../preview.png"
}
```

### POST /api/v1/srm/process

Request:

```json
{
  "granule_id": "S2A_MSIL2A_20260215_T43REQ",
  "scale_factor": 4,
  "target_classes": ["built_up", "water", "vegetation", "cropland", "bare_soil"],
  "apply_mrf_smoothing": true
}
```

Returns `202` with `{"job_id": "job_srm_884920", "status": "PENDING"}`. Poll
`GET /api/v1/jobs/{job_id}` for `execution_time_seconds`, `cog_output_url`,
`tile_url_template` and `class_distribution_percent`.

### Exports

`GET /api/v1/jobs/{id}/export.tif` · `export.geojson` · `report.csv`

## 8. UI layout

- **Top bar.** Title, granule metadata, cloud-cover badge, status, export menu.
- **Left sidebar.** AOI selector (draw / upload), date range and cloud threshold, model
  config (scale factor, MRF smoothing), primary action button.
- **Centre.** Dual-map visualiser, synchronised navigation, curtain slider between 10 m
  input (left) and 2.5 m thematic output (right).
- **Right drawer.** Class distribution donut, surface area table (m² and hectares),
  download buttons.
