# GeoSRM Engine — Deep Learning Based Super-Resolution Mapping

**SIH26142** · Sponsoring agency: National Technical Research Organisation (NTRO) · Theme: Space Technology / Software

Super-Resolution Mapping (SRM) of Copernicus Sentinel-2 Level-2A imagery: coarse 10 m mixed
pixels are **spectrally unmixed** into fractional land-cover abundances and those abundances are
**allocated onto a 4× finer sub-pixel grid**, yielding **2.5 m effective thematic land-cover maps**.

This is not perceptual upscaling. The pipeline enforces physical mass conservation — the output
downsamples back to the original sensor abundances — so nothing is hallucinated.

## Target classes (C = 5)

| Class | Description |
|---|---|
| `built_up` | Concrete structures, buildings, tarmac, paved roads |
| `water` | Rivers, lakes, reservoirs, coastal margins |
| `vegetation` | Tree canopy, forest, dense green cover |
| `cropland` | Cultivated fields, seasonal pasture, farmland |
| `bare_soil` | Unpaved earth, rock, cleared land |

## Physical constraints

For every coarse pixel `(i, j)` and class `c`, the Deep Spectral Unmixing Network (D-SUN) predicts
an abundance tensor `A ∈ R^{H×W×C}` satisfying

```
A[i,j,c] >= 0            (non-negativity, ANC)
Σ_c A[i,j,c] = 1         (sum-to-one, ASC)
```

Each coarse pixel is subdivided into `S² = 16` sub-pixels; the count assigned to class `c` is

```
N[i,j,c] = round(A[i,j,c] · S²),    Σ_c N[i,j,c] = S²
```

The Swin Transformer allocation head chooses the sub-pixel *layout* by minimising a spatial
energy functional over the 8-neighbourhood (maximising spatial autocorrelation), followed by an
MRF smoothing pass that removes salt-and-pepper noise while preserving linear boundaries.

## Architecture

```
[React + MapLibre dual canvas]
        │  REST                                   ▲ XYZ/WMTS tiles
        ▼                                         │
[FastAPI gateway] ──Celery/Redis──► [Ingestion worker]  [TiTiler container]
        │                            GDAL/Rasterio/PySTAC        ▲
        ▼                                   │                    │
   [PostGIS]                                ▼            shared COG volume
                                  [PyTorch SRM worker] ──────────┘
                                   D-SUN → SwinIR → MRF
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for components, sequence, class model and
deployment topology.

## Running

### 1. Model only, no infrastructure

The fastest way to see the pipeline work. Needs only `torch` and `numpy`.

```bash
python scripts/benchmark.py --size 64 --runs 2
```

Prints per-run latency and the mass-conservation error. Anything under `1e-3` means the
abundance constraints held.

```bash
cd ml_engine && python -m pytest tests -q
```

### 2. Sync mode — the whole pipeline, one process

No Redis, no Celery, no Docker, no GPU. The API runs ingestion and inference inline, and
serves the map overlays itself, so the full flow works on a laptop.

```bash
pip install -r requirements-sync.txt
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

Then two terminals:

```bash
SYNC_MODE=true DEVICE=cpu COG_STORAGE_DIR=../storage/cogs python -m uvicorn main:app --port 8000 --app-dir backend
```

```bash
npm run dev --prefix frontend
```

Open http://localhost:3000, pick a region or draw a box, and press Execute. A real
Sentinel-2 granule is fetched from the Planetary Computer STAC API, unmixed, allocated to
a 2.5 m sub-pixel grid, and returned as a georeferenced COG plus map overlays. Expect
roughly 40-55 s per job on a laptop CPU, most of it STAC search and band reads.

The AOI is capped at 192x192 coarse pixels in this mode (`MAX_COARSE_PX` in
`backend/services/pipeline.py`); larger boxes are cropped to their centre.

Sync mode calls the same ingestion, inference and export functions as the workers, so a
bug found here is a real bug. What it does not exercise is the queueing, the container
split or the tile server.

### 3. Full platform, GPU

Prerequisites: Docker Engine 24+, Compose 2.20+, NVIDIA Container Toolkit, and an NVIDIA
GPU with 8 GB VRAM or more (RTX 3080/3090/4090, T4, A10G). An RTX 3080 is `sm_86` and is
fully covered by the CUDA 12.1 wheels the image pins -- no changes needed.

```bash
cp .env.example .env
docker compose up --build -d
```

Confirm the container actually sees the card, and that the model fits its VRAM:

```bash
docker compose run --rm ml_worker python scripts/check_gpu.py
```

If that fails, [`docs/GPU_SETUP.md`](docs/GPU_SETUP.md) walks the three verification
steps and the usual causes.

### 4. Full platform, CPU

For machines with no NVIDIA runtime registered, or a GPU below the 8 GB target. Builds
on slim Python with CPU torch wheels instead of the ~6 GB CUDA image, and drops the GPU
device reservation that would otherwise fail the whole stack.

```bash
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up --build
```

Inference will miss the < 8 s budget by a wide margin. That is expected — this mode
exercises the pipeline, it does not measure it. Benchmark on the target GPU.

| Service | URL |
|---|---|
| Web application | http://localhost:3000 |
| REST API docs | http://localhost:8000/docs |
| TiTiler tile server | http://localhost:8001/docs |

Tail a worker with `docker compose logs -f ml_worker` (or `ingest_worker`), and stop
everything with `docker compose down`.

### Before the output means anything

`ml_engine/weights/` is empty in a fresh clone, so the model runs with **randomly
initialised parameters** — the pipeline is exercised end to end and the physical
constraints still hold, but the class map is noise. Get real weights first:

```bash
pip install sen2sr mlstac
python scripts/download_weights.py
```

See [`docs/DATASETS.md`](docs/DATASETS.md) for what to fine-tune on top of them.

### Offline demo mode

Cache real imagery before the event, so a dead venue network cannot break the demo:

```bash
python scripts/build_offline_cache.py --demo-size 0.05
```

Then set `OFFLINE_MODE=true` in `.env`, or use the toggle in the UI header.

### Local development without Docker

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv/Scripts/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
cd frontend && npm install && npm run dev
```

The API still needs Redis and PostGIS reachable; the simplest split is
`docker compose up -d postgis redis titiler` alongside a locally run gateway.

## Repository layout

```
backend/      FastAPI gateway, STAC ingestion, preprocessing, COG export, PostGIS models
ml_engine/    PyTorch D-SUN + SwinIR inference, unmixing losses, MRF smoothing
frontend/     React 18 + Vite, MapLibre GL dual canvas, analytics drawer
data_cache/   Pre-cached offline demo granules (Delhi NCR, Kerala coastal, Rajasthan arid)
storage/cogs/     Generated Cloud-Optimized GeoTIFFs, shared with the TiTiler container
storage/tensors/  Aligned tensors handed from the ingest worker to the GPU worker
docs/         PRD, MVP spec, architecture, datasets, tech-clash mitigations, demo script
scripts/      Weight download, offline cache builder, GPU check, benchmarks
```

## Acceptance benchmarks

| Metric | Target |
|---|---|
| Inference, 256×256 coarse tile | < 8 s (T4), < 5 s (RTX 3090) |
| Tile serving latency | < 300 ms |
| Client canvas frame rate | ≥ 45 FPS while panning / dragging the slider |
| mIoU across 5 classes | ≥ 0.70 |
| Abundance mass conservation | \|Σ_c A - 1\| < 1e-3 per pixel |
| GPU memory footprint | ≤ 8 GB VRAM |

## Documentation

- [`docs/PRD.md`](docs/PRD.md) — product requirements, personas, FR matrix, API contracts
- [`docs/MVP_SPEC.md`](docs/MVP_SPEC.md) — 48-hour scope boundaries and P0/P1/P2 priorities
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — tech stack, UML component/sequence/class/deployment
- [`docs/DATASETS.md`](docs/DATASETS.md) — free data sources and pre-trained checkpoints
- [`docs/PIPELINE_HANDOFF.md`](docs/PIPELINE_HANDOFF.md) — how the aligned tensor crosses from the ingest worker to the GPU worker
- [`docs/GPU_SETUP.md`](docs/GPU_SETUP.md) — target cards, container GPU passthrough, troubleshooting
- [`docs/TECH_CLASHES.md`](docs/TECH_CLASHES.md) — four known integration conflicts and their fixes
- [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) — 3-minute evaluation script and fallback matrix
- [`docs/TEAM.md`](docs/TEAM.md) — six-member role allocation
