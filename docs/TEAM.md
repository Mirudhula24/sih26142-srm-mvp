# Roles and work allocation

SIH caps participation at six. The split below is organised around what the repo is
still *missing*, not generic job titles — the scaffold already stands, so dividing by
"frontend / backend / ML" would leave the actual blocking work unowned.

## Where the project stands

**Built and verified:** D-SUN unmixing, Swin allocation head, mass-conserving sub-pixel
assignment, MRF smoothing, tiled inference (256×256 in 4.8 s on CPU), STAC ingestion,
band alignment, SCL masking, ingest→GPU tensor hand-off, COG/GeoJSON/CSV export, FastAPI
routes, PostGIS schema, dual-canvas UI shell, Compose for GPU and CPU, 7 passing tests.

**Still missing:**

1. **No trained weights and no training pipeline** — no `train.py`, no dataset loader.
2. **No ground-truth labels** — WorldCover → 5 classes → abundance targets is unwritten.
3. "Draw bounding box" is a dead button; `mapbox-gl-draw` is installed but never imported.
4. The left canvas receives a preview PNG where an XYZ tile template is expected.
5. Job state lives in in-process dicts; the `srm_jobs` table is never written.
6. mIoU is never computed — no evaluation script.
7. `data_cache/` is empty; the Docker images have never been built.

Items 1 and 2 block every visual result. Everything else runs in parallel.

## The six roles

Each role owns specific paths, so two people never edit the same module.

### Deep Learning Engineer — *critical path*

Owns `ml_engine/models/`, `ml_engine/utils/unmixing_loss.py`, `ml_engine/train.py`,
`ml_engine/weights/`.

- Write `train.py` and the dataset loader; neither exists yet.
- Start from SEN2SRLite as the spatial backbone rather than training from scratch — only
  the allocation head needs to learn. See [DATASETS.md](DATASETS.md).
- Tune the four `SRMLoss` weights; keep `mass_error` under 1e-3.
- Export a checkpoint every hour, however undertrained. Everyone downstream is blocked
  until a loadable file exists.

**Done when:** `sih26142_srm_v1.pth` loads without shape errors and produces a map that
visibly beats the 10 m input.

### Geospatial Data Engineer — *critical path*

Owns `backend/services/stac_fetcher.py`, `backend/services/preprocessor.py`,
`scripts/build_offline_cache.py`, `scripts/build_labels.py`.

- Build the label pipeline first: ESA WorldCover 11 classes → our 5 → aggregate to
  abundance fractions. **Training cannot start without this.**
- Pair it with downsampled high-resolution reference for sub-pixel supervision.
- Run `build_offline_cache.py` for all three regions; verify with the network unplugged.
- Sanity-check band registration — no offset between 10 m and resampled 20 m channels.

**Done when:** the DL engineer has paired `(X, abundance, fine_labels)` tensors on disk
and `data_cache/` holds three real regions.

### Backend & Spatial DB Lead — *parallel*

Owns `backend/routers/`, `backend/services/tasks.py`, `backend/database/`,
`backend/services/exporter.py`.

- Wire the job lifecycle to PostGIS — `_JOBS`, `_TASK_IDS` and `_GRANULE_BBOX` are
  in-process dicts that a restart wipes.
- Persist `ClassMetrics` and `COGExport` rows.
- Write the mIoU evaluation path so the accuracy figure is measured, not asserted.
- Verify the QGIS round-trip personally; the affine scaling is a silent failure mode.

**Done when:** a job survives an API restart and the exported GeoTIFF opens in QGIS in
the right place on Earth.

### Frontend Web GIS Developer — *parallel*

Owns `frontend/src/components/`, `frontend/src/store/`, `frontend/src/lib/`.

- Fix the left canvas: it receives `granule.preview_url` (a rendered PNG) where an XYZ
  template is expected, so input imagery never draws. Point it at TiTiler.
- Wire the dead "Draw bounding box" button; `mapbox-gl-draw` is already a dependency.
- Add real loading and error states.
- Profile the curtain drag; confirm the camera lock's re-entrancy guard holds under fast
  panning.

**Done when:** a judge draws a box, hits Execute, and watches a real 2.5 m map slide in
under the curtain at 45 FPS.

### Integration & QA Lead — *parallel*

Owns `docker-compose*.yml`, `ml_engine/tests/`, `backend/tests/`, `data_cache/`.

- Build the Docker images on the 3080 **today**. They have never been built.
- Run `scripts/check_gpu.py` inside the container; record peak VRAM, tune `MAX_PATCH_SIZE`.
- Own the end-to-end drill: cold clone → compose up → draw AOI → export → open in QGIS.
- Rehearse failures deliberately: pull the network, force an OOM, pick a cloudy scene.

**Done when:** a clean clone reaches a working demo on the 3080 with one command, timed
three times.

### Team Lead & Presenter — *integration owner*

Owns `docs/DEMO_SCRIPT.md`, `docs/PRD.md`, `README.md`, the pitch deck.

- Guard scope. Every P2 idea appearing at hour 30 is a threat, not an opportunity.
- Own the mass-conservation defence: when asked whether this is generative invention,
  show that the output downsamples back to the observed sensor abundances.
- Never present a random-weight output as a result.
- Merge and integrate; nobody else should be resolving conflicts.

**Done when:** the three-minute run is rehearsed end to end and you can answer the
hallucination question without opening an editor.

## Sequencing

| Hours | What happens |
|---|---|
| H0–H2 | Everyone clones, runs the CPU stack, sees the UI. QA starts the GPU image build — longest pole, most likely to break. |
| H2–H10 | Data and DL engineers **pair** on the label pipeline. Two people here is not redundant; it is the whole schedule. Backend and frontend work their own fixes. |
| H10–H24 | Training runs, checkpointing hourly. First checkpoint unblocks frontend and QA testing against real output. Backend finishes persistence and mIoU. |
| H24–H36 | Integration. Real weights meet the real UI; budget for bugs neither half showed alone. Cache offline regions, verify with the network off. |
| H36–H44 | Freeze. No new features. Time the three-minute script on the actual demo machine. |
| H44–H48 | Buffer. Writing code here means something upstream slipped. |

## Hand-off contracts

Agree these in the first hour.

| From | To | Contract |
|---|---|---|
| Data eng. | DL eng. | `X (6,H,W) float32`, `abundance (5,H,W)` summing to 1, `fine_labels (H·4,W·4) int64`. Band order B02 B03 B04 B08 B11 B12. |
| DL eng. | Backend | Weights path and `state_dict` keys. `load_model` uses `strict=False`, so mismatched keys fail **silently** as random weights — verify a load populated the model. |
| Backend | Frontend | `SRMResponse` in `backend/schemas.py` is the contract; the UI polls `/api/v1/jobs/{id}`. Do not rename fields without telling frontend. |
| Ingest | GPU worker | Fixed and documented in [PIPELINE_HANDOFF.md](PIPELINE_HANDOFF.md). The `.npz` keys must stay in step across two images. |
| Everyone | Team lead | Branch per role, small commits, no direct pushes to `main` during integration hours. |

## The one thing to get right

Two of six people are on the critical path and their work is the least visible. There is
a real pull toward putting four people on the UI because progress there is easy to see.
Resist it — a beautiful interface rendering noise loses to a plain one rendering a
correct map, and the physical constraints are the entire argument of this project.
