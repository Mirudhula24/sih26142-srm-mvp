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

## Quickstart

Prerequisites: Docker Engine 24+, Docker Compose 2.20+, NVIDIA Container Toolkit, an NVIDIA GPU
with ≥ 8 GB VRAM (RTX 3080/3090/4090 or T4/A10G). CPU-only runs work but miss the latency target.

```bash
cp .env.example .env
docker compose up --build -d
```

| Service | URL |
|---|---|
| Web application | http://localhost:3000 |
| REST API docs | http://localhost:8000/docs |
| TiTiler tile server | http://localhost:8001/docs |

Local development without Docker:

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
cd frontend && npm install && npm run dev
```

## Repository layout

```
backend/      FastAPI gateway, STAC ingestion, preprocessing, COG export, PostGIS models
ml_engine/    PyTorch D-SUN + SwinIR inference, unmixing losses, MRF smoothing
frontend/     React 18 + Vite, MapLibre GL dual canvas, analytics drawer
data_cache/   Pre-cached offline demo granules (Delhi NCR, Kerala coastal, Rajasthan arid)
storage/cogs/     Generated Cloud-Optimized GeoTIFFs, shared with the TiTiler container
storage/tensors/  Aligned tensors handed from the ingest worker to the GPU worker
docs/         PRD, MVP spec, architecture, datasets, tech-clash mitigations, demo script
scripts/      Weight download, offline cache builder, benchmarks
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
- [`docs/TECH_CLASHES.md`](docs/TECH_CLASHES.md) — four known integration conflicts and their fixes
- [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) — 3-minute evaluation script and fallback matrix
- [`docs/TEAM.md`](docs/TEAM.md) — six-member role allocation
