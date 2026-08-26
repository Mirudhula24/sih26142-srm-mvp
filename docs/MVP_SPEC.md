# MVP scope — 48-hour build

## In scope

- Fixed 4x scale factor: each 10 m pixel becomes 16 sub-pixels at 2.5 m.
- Seven classes: `built_up`, `road`, `water`, `vegetation`, `cropland`, `bare_soil`,
  `sand`. Roads were split out of built-up after review: a road network is a distinct
  intelligence product. Seven is the resolvable ceiling for six bands plus sum-to-one.
- STAC ingestion of Sentinel-2 L2A surface reflectance granules.
- D-SUN spectral unmixing + SwinIR spatial allocation in PyTorch.
- Dual-canvas web GIS with a synchronised curtain slider.
- COG export with CRS tags preserved (EPSG:4326 / EPSG:32643).
- Offline cache for Delhi NCR, Kerala coastal, Rajasthan arid.

## Out of scope (deferred)

- 8x / 16x ultra-resolution modes.
- Land-cover taxonomies beyond five classes.
- Native mobile applications.
- Multi-year automated change-detection engines.

## Modules

**1. Ingestion & preprocessing.** STAC fetcher with date range and cloud threshold;
guided-filter resampling of B11/B12 onto the 10 m grid; SCL masking of cloud, cirrus,
shadow and saturation. Output: aligned tensor of shape (6, H, W).

**2. SRM inference.** D-SUN predicts fractional abundances under the sum-to-one and
non-negativity constraints via a softmax head; SwinIR allocates 16 sub-pixels per coarse
cell while maximising spatial autocorrelation; an MRF pass removes salt-and-pepper noise
while keeping linear boundaries intact.

**3. Dual-canvas visualiser.** AOI drawing/upload; two MapLibre instances with locked
camera state; curtain slider clipping the right canvas in real time.

**4. Analytics.** Percentage distribution chart, area in m² and hectares, job metadata
inspector (acquisition time, cloud cover, scale factor, execution time, mIoU).

**5. Export.** One-click COG download; raster-to-vector GeoJSON boundary extraction.

**6. Demo resilience.** Pre-cached regional granules and a one-click offline toggle that
bypasses all network calls.

## Priorities

| Feature | Priority | Target |
|---|---|---|
| Deep learning SRM engine | P0 | < 8 s per tile |
| Synchronised dual canvas | P0 | >= 45 FPS |
| Abundance unmixing constraints | P0 | mass error < 1e-3 |
| GeoTIFF export | P0 | Valid CRS tags in QGIS |
| Sub-pixel area analytics | P0 | Donut chart + area table |
| STAC auto-fetcher | P1 | Resolves < 5 s |
| Offline cache fallback | P1 | 3 regions cached |
| GeoJSON vector extractor | P1 | One-click download |
| 8x ultra-resolution | P2 | Only if VRAM allows |
| Temporal change analytics | P2 | Post-hackathon |

## Acceptance benchmarks

- 256x256 coarse tile end-to-end in < 8 s.
- mIoU >= 0.70 against reference high-resolution test grids.
- Abundance deviation below 1e-3 per coarse pixel.
- Canvas at 45 FPS or better while panning, zooming and dragging the slider.
- Entire platform launches with a single `docker compose up --build`.
