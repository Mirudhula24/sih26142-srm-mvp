# Three-minute evaluation script

| Time | Action | Screen | Talking point |
|---|---|---|---|
| 0:00–0:35 | Select the cached Delhi NCR region | Raw 10 m Sentinel-2 scene | 10 m imagery creates mixed pixels that hide access roads and facility boundaries; commercial VHR resolves this but costs a fortune and takes days to task. |
| 0:35–1:15 | Click **Execute super-resolution mapping** | 2.5 m thematic map renders in < 5 s | The model unmixes the coarse spectral signal under a hard abundance sum-to-one constraint — it cannot hallucinate features. |
| 1:15–2:00 | Drag the curtain slider; zoom into linear features | Split view, crisp 2.5 m boundaries | Sub-pixel road networks and water edges resolve at 2.5 m, directly usable for site analysis. |
| 2:00–2:30 | Open the analytics drawer | Donut chart + area table | Per-class surface area in m² and hectares across all five classes. |
| 2:30–3:00 | Click **Export GeoTIFF**, open in QGIS | File opens with correct CRS | Standard Cloud-Optimized GeoTIFF with preserved projection — drops straight into desktop GIS. |

## Fallback matrix

| Failure | Likelihood | Mitigation |
|---|---|---|
| Venue internet / STAC latency | High | STAC call has a 3 s timeout, then loads `data_cache/` automatically. Flip **Offline demo mode** to skip the network entirely. |
| GPU out-of-memory | Medium | `run_srm` tiles the AOI into overlapping 256×256 patches before the network; results stitch seamlessly. |
| Heavy cloud cover in the AOI | Medium | SCL mask is checked before inference; the nearest cloud-free granule from the past 15 days is used. |
| "Isn't this just generative AI making things up?" | Low | Show the mass-conservation check: `mass_conservation_error < 1e-3`. The output downsamples exactly back to the observed sensor abundances. |

## Rubric alignment

| Criterion | How this scores |
|---|---|
| Innovation | Physical spectral unmixing + transformer spatial allocation, not interpolation |
| Problem relevance | Software-upgrades free Sentinel-2 to VHR-like detail for NTRO's constraint |
| Technical implementation | Modular microservices, Docker, PyTorch 2.2, FastAPI, TiTiler COG streaming |
| Working prototype | Live inference over arbitrary user bounding boxes |
| UI/UX | GPU-accelerated MapLibre split-screen at ≥ 45 FPS |
