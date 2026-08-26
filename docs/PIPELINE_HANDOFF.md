# Ingest → GPU worker hand-off

The two workers are separate containers on purpose (GDAL and PyTorch fight over thread
pools — see [TECH_CLASHES.md](TECH_CLASHES.md), Clash 1). That means the aligned tensor
has to cross a process boundary, and it is far too large to travel through the Redis
broker. It goes to a shared volume; the Celery message carries only a path.

## The chain

```
POST /api/v1/srm/process
   └─ chain( srm.ingest  → queue "ingest"     [backend image, CPU]
           , srm.infer   → queue "inference"  [ml_engine image, GPU] )
```

`srm.infer` is defined in the `ml_engine` image and is never imported by the API. It is
addressed by task name over the shared broker, which is why both services must point at
the same Redis instance and agree on the queue names.

The chain passes `srm.ingest`'s return value as the first positional argument of
`srm.infer`, so every parameter the GPU worker needs is carried in that dict:

```python
{
  "job_id": "job_srm_a1b2c3d4e5f6",
  "granule_id": "S2A_MSIL2A_...",
  "tensor_path": "/data/tensors/job_srm_a1b2c3d4e5f6.npz",
  "scale_factor": 4,
  "apply_mrf_smoothing": True,
  "crs": "EPSG:32643",
  "valid_fraction": 0.97
}
```

## The archive format

`TENSOR_EXCHANGE_DIR/{job_id}.npz`, written by
`backend/services/tensor_exchange.save` and read by
`ml_engine/utils/tensor_exchange.load`. Both sides must agree on these keys:

| Key | Shape / type | Meaning |
|---|---|---|
| `tensor` | `(6, H, W)` float32 | Aligned reflectance in `[0, 1]`, band order B02 B03 B04 B08 B11 B12 |
| `valid_mask` | `(H, W)` bool | `False` where the SCL layer flagged cloud, cirrus, shadow or saturation |
| `transform` | 6 float64 | Affine of the **coarse** 10 m grid |
| `crs` | string | Usually a UTM zone, e.g. `EPSG:32643` |
| `bbox` | 4 float64 | Original WGS84 request bounds |

The affine and CRS travel with the array deliberately. Without them the GPU worker
cannot georeference its output, and the exported GeoTIFF opens in the wrong place in
QGIS — with no error to warn you.

## What the GPU worker does with it

1. `tensor_exchange.load` → tensor, mask, affine, CRS.
2. `inference.run_srm` → overlapping-patch tiling, D-SUN, SwinIR, MRF, hard allocation.
3. Cloud-masked coarse pixels are propagated to all `S²` of their sub-pixels as nodata,
   so masked ground never shows up in the area metrics as real land cover.
4. `cog_writer.write_cog` → COG, with the affine scaled by `1/S` for the finer grid.
5. `tensor_exchange.cleanup` → delete the intermediate; nothing else collects the volume.
6. Return class distribution, per-class area, execution time and mass-conservation error.

## Volumes

Both workers must mount the same exchange directory, and it must be writable by both:

```yaml
ingest_worker:
  volumes:
    - ./storage/tensors:/data/tensors
ml_worker:
  volumes:
    - ./storage/tensors:/data/tensors
```

If the GPU worker raises `FileNotFoundError` naming `TENSOR_EXCHANGE_DIR`, this mount is
the first thing to check — it means the two containers are looking at different disks.

## Where the bbox comes from

`srm.ingest` needs a bounding box, but `POST /srm/process` is keyed on a granule id. Two
paths, in order:

1. The client sends `aoi_geojson` on the request (what the React app does).
2. Otherwise the gateway reuses the bbox recorded during `POST /imagery/fetch`.

If neither is available the endpoint returns `400` rather than guessing.

## Known limits

- The job mirror (`_JOBS`, `_TASK_IDS`, `_GRANULE_BBOX` in `services/tasks.py`) is
  in-process. It is fine for a single API replica during a demo, but a restart loses
  job history and a second replica will not see the first one's jobs. The PostGIS
  `srm_jobs` table is the durable record and is not yet wired to these paths.
- `miou_score` is only populated when a job runs against reference labels; live
  inference over an arbitrary AOI has nothing to score against and returns `null`.
