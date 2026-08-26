# Architecture

## Stack

| Layer | Technology | Notes |
|---|---|---|
| Presentation | React 18 + Vite, MapLibre GL **3.6 LTS**, Deck.gl 8.9, Zustand, Tailwind, Recharts | v3.6 pin is deliberate — see TECH_CLASHES.md |
| API gateway | FastAPI + Uvicorn, Pydantic v2 | Async REST, OpenAPI at `/docs` |
| Orchestration | Celery + Redis 7 | Two queues: `ingest` (CPU) and `inference` (GPU) |
| Geospatial | GDAL 3.8, Rasterio, PySTAC, Shapely, GeoPandas | Band alignment, masking, affine preservation |
| DL engine | PyTorch 2.2 + CUDA 12, timm | D-SUN + SwinIR allocation head |
| Tile serving | TiTiler (isolated container), rio-cogeo | Windowed COG streaming |
| Persistence | PostgreSQL 16 + PostGIS 3.4, GiST indexes | AOIs, jobs, exports, metrics |
| Deployment | Docker Compose, NVIDIA Container Toolkit | Single `docker compose up --build` |

## Components

| Component | Provides | Requires |
|---|---|---|
| Web client (React/MapLibre) | `IUserInterface`, `IDualCanvasView`, `IAnalyticsDisplay` | `IAPIGateway`, `ITileStream` |
| API gateway (FastAPI) | `IAPIGateway`, `IJobManagement` | `IIngestionService`, `IMLEngine`, `IDatabaseAccess` |
| Ingestion engine (GDAL/PySTAC) | `IIngestionService` | `ISTACExternalAPI` |
| SRM worker (PyTorch) | `IMLEngine` | `IGPUAcceleration` |
| Tile server (TiTiler) | `ITileStream` | `ICOGStorageAccess` |
| Persistence (PostGIS/Redis) | `IDatabaseAccess`, `ICacheStore` | — |

## Request sequence

```
User ──► Web UI            select AOI, click Execute
Web UI ──► API             POST /api/v1/srm/process
API ──► PostGIS            INSERT srm_jobs (status PENDING)
API ──► Redis/Celery       enqueue on `ingest`
Ingest ──► STAC            query Sentinel-2 L2A, cloud < threshold
Ingest ──► Ingest          resample SWIR 20m→10m, apply SCL mask, normalise → X (6,H,W)
Ingest ──► ML worker       hand off aligned tensor via shared volume
ML ──► GPU                 D-SUN unmixing → SwinIR allocation → MRF smoothing
ML ──► storage/cogs        write COG with scaled affine + colormap
API ──► PostGIS            UPDATE srm_jobs (status COMPLETED, metrics)
Web UI ──► API             GET /api/v1/jobs/{id}  (poll)
Web UI ──► TiTiler         GET /cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png
```

## Data model

```
[UserAOI] 1 ──── 0..* [SRMJob] 0..* ──── 1 [SatelliteGranule]
                        │  │
              1 ────────┘  └──────── 1
              ▼                      ▼
        [COGExport]            [ClassMetrics]
```

| Parent | Child | Cardinality | On delete |
|---|---|---|---|
| UserAOI | SRMJob | 1 : 0..* | CASCADE |
| SatelliteGranule | SRMJob | 1 : 0..* | RESTRICT |
| SRMJob | COGExport | 1 : 1 | CASCADE |
| SRMJob | ClassMetrics | 1 : 1 | CASCADE |

## Deployment topology

| Node | Container | Resources | Ports |
|---|---|---|---|
| Client | Browser (WebGL) | client GPU | 443 → proxy |
| Proxy | Nginx | 1 vCPU, 1 GB | 80 / 443 |
| Application | FastAPI gateway | 2 vCPU, 4 GB | 8000 |
| GPU | PyTorch CUDA worker | 4 vCPU, 16 GB, 8 GB VRAM | volume IPC |
| Tile | TiTiler | 2 vCPU, 4 GB | 8001 |
| Data | PostGIS + Redis | 2 vCPU, 8 GB, NVMe | 5432 / 6379 |

## Pipeline stages and latency budget

| Stage | Input | Output | Budget |
|---|---|---|---|
| AOI ingestion | GeoJSON / bbox | WGS84 polygon | < 100 ms |
| STAC fetch | bbox | 6 band COG hrefs + SCL | < 5 s |
| Band alignment | 10 m + 20 m bands | X ∈ R^(6×H×W) | < 2 s |
| Inference | X | class map (H·4 × W·4) | < 8 s |
| COG write | class raster | COG + overviews | < 2 s |
| Tile serving | tile request | PNG | < 300 ms |
