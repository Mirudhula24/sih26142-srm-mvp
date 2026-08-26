# Data sources and pre-trained checkpoints

Everything here is free for public and scientific use. Nothing in the pipeline requires
a paid imagery subscription.

## Input imagery

| Source | Access | Why |
|---|---|---|
| **Microsoft Planetary Computer STAC** (primary) | Open REST API, no key for public reads | COG assets support HTTP range requests, so only the AOI window transfers |
| AWS Open Data Registry (`sentinel-s2-l2a`) | Open S3 bucket | Direct array streaming via GDAL `/vsis3/` |
| Copernicus Data Space Ecosystem | OData / Process APIs | Complete `.SAFE` L2A archive for offline validation |

Bands used: `B02` `B03` `B04` `B08` at 10 m, `B11` `B12` at 20 m (resampled to 10 m),
plus `SCL` for cloud/shadow masking. Six channels reach the network.

## Training and reference data

| Dataset | Resolution | Role |
|---|---|---|
| **Sen2Venµs** | Paired Sentinel-2 / VENµS | Pre-train the super-resolution backbone on real paired data |
| **ESA WorldCover 10m v200** | 10 m, 11 classes | Ground-truth fractions — remap to the 5 target classes, then aggregate to get abundance targets |
| **NAIP aerial** | sub-metre | Downsample to 2.5 m for the sub-pixel allocation supervision signal |
| **SEN12MS** | 180k+ patches | Additional multi-spectral pre-training |

## Pre-trained checkpoints worth starting from

Training from scratch inside a 48-hour window is not realistic. These are drop-in.

- **SEN2SR / SEN2SRLite** (ESAOpenSR / Taco Foundation) — *recommended*. Purpose-built
  for Sentinel-2 → 2.5 m at 4×, matching our `S = 4` target. `pip install sen2sr mlstac`;
  weights on Hugging Face `tacofoundation/SEN2SR`. Inference is under 5 s per tile.
- **DSen2** — CNN that super-resolves 20 m and 60 m bands to 10 m. Useful as a stronger
  replacement for the bilinear SWIR resampling in `preprocessor.py`.
- **DiffFuSR** (Norsk Regnesentral) — diffusion + learned fusion across all 12 bands to
  2.5 m GSD. Best spectral fidelity, heaviest to run.
- **Satlas Super-Resolution** (AllenAI) — ESRGAN/Swin at 4×, trained on 44M Sentinel-2 /
  NAIP pairs.
- **TorchGeo backbones** — `torchgeo.models.resnet50(weights="ResNet50_Weights.SENTINEL2_ALL_10M")`
  and Swin variants, usable as the D-SUN encoder.

Note the distinction: SEN2SR and friends do *image* super-resolution. This project needs
super-resolution **mapping** — thematic class allocation under abundance constraints. Use
their weights as the spatial backbone, then train our allocation head on top.

`scripts/download_weights.py` fetches the SEN2SRLite checkpoint into `ml_engine/weights/`.

## Pre-event protocol

1. **Before the event.** Download Sen2Venµs or SEN12MS, train offline, export
   `ml_engine/weights/sih26142_srm_v1.pth`.
2. **During the build.** Live STAC ingestion over arbitrary user bounding boxes.
3. **Before the demo.** Run `scripts/build_offline_cache.py` for Delhi NCR, Kerala
   coastal and Rajasthan arid so the demo survives a dead venue network.
