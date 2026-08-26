# Known integration clashes and their mitigations

Four conflicts in this stack that reliably break builds or the demo. Each is already
mitigated in the committed configuration — this file records *why*, so nobody
"simplifies" the fix away at 3 a.m.

## 1. GDAL / OpenCV / PyTorch thread-pool over-subscription

**Symptom.** Ingestion workers freeze at random; CPU pegged at 100% across all cores
with no forward progress. Secondary risk: `libgdal` / libstdc++ ABI mismatches when
GDAL and CUDA PyTorch are installed into the same image.

**Cause.** GDAL (via rasterio), OpenCV and PyTorch each ship an independent OpenMP or
POSIX thread pool. Co-located, they each claim every core.

**Mitigation (both applied).**
- Every Dockerfile pins `OMP_NUM_THREADS=1`, `OPENBLAS_NUM_THREADS=1`,
  `MKL_NUM_THREADS=1`, `NUMEXPR_NUM_THREADS=1`, leaving PyTorch to manage its own
  intra-op threading.
- The ingestion worker (`ingest_worker`, GDAL image) and the inference worker
  (`ml_worker`, CUDA image) are separate containers on separate Celery queues, sharing
  only a mounted volume.

## 2. `pydensecrf` will not build on Python 3.10+

**Symptom.** `pip install pydensecrf` fails during Cython/C++ compilation inside any
modern PyTorch 2.2 image.

**Cause.** Unmaintained Cython wrapper around Krähenbühl's C++ dense-CRF; incompatible
with GCC 11+ and current Cython.

**Mitigation.** No CRF dependency at all. `ml_engine/utils/mrf_smooth.py` implements the
same 8-neighbourhood Potts energy as an ICM pass in pure PyTorch — it runs on GPU,
differentiates, and has no build step. `enforce_quota()` restores exact abundance
conservation if smoothing perturbs the counts.

## 3. TiTiler and PyTorch contending for GPU memory and the event loop

**Symptom.** Map tiles stall or the canvas drops well below 45 FPS whenever inference
runs; occasional CUDA OOM.

**Cause.** TiTiler is an async FastAPI service. In-process with PyTorch, large CUDA
allocations block the asyncio event loop and compete for VRAM.

**Mitigation.** TiTiler runs as the official pre-built container
`ghcr.io/developmentseed/titiler`, touching neither PyTorch nor the GPU. The inference
worker writes a COG to the shared `storage/cogs` volume; TiTiler reads that static file.

## 4. MapLibre GL JS v4 vs Deck.gl WebGL state

**Symptom.** WebGL context loss, z-order flicker, or layers vanishing during fast pans.

**Cause.** MapLibre v4 changed its internal WebGL renderer and camera matrices; Deck.gl
v8.9's `MapboxOverlay` context sharing was written against v3.

**Mitigation.** `maplibre-gl` is pinned to `^3.6.2` (LTS) in `frontend/package.json`,
which shares a WebGL context cleanly with Deck.gl v8.9. If you must move to MapLibre v4,
drop Deck.gl and use native `map.addSource` / `map.addLayer` raster layers instead.

## Summary

| Area | Naive choice | What this repo does |
|---|---|---|
| Edge smoothing | `pydensecrf` | Native PyTorch ICM/Potts MRF |
| Tile engine | In-process TiTiler | Isolated TiTiler container |
| Frontend renderer | MapLibre v4 + Deck.gl | MapLibre v3.6 LTS + Deck.gl v8.9 |
| GIS/ML threading | Library defaults | `*_NUM_THREADS=1` + split containers |
