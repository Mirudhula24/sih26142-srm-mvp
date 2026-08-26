"""SRM inference: sliding-window tiling, D-SUN -> SwinIR -> MRF, COG-ready output."""
import logging
import math
import os
import time
from typing import Dict, Optional, Tuple

import numpy as np
import rasterio
import torch
import torch.nn.functional as F
from rasterio.enums import Resampling
from rasterio.windows import from_bounds

from models.d_sun import DeepSpectralUnmixingNetwork
from models.swin_srm import SubPixelAllocationNetwork, SuperResolutionMapper, allocate_subpixels
from utils.mrf_smooth import mrf_smooth

log = logging.getLogger(__name__)

CLASSES = ["built_up", "water", "vegetation", "cropland", "bare_soil"]
WORLDCOVER_URL = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
    "ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
)

# ESA WorldCover v200 class codes remapped to this product's five classes.
_WORLDCOVER_CLASS_MAP = {
    10: 2, 20: 2, 30: 2, 40: 3, 50: 0, 60: 4, 70: 4, 80: 1,
    90: 2, 95: 2, 100: 2,
}


def build_model(
    num_classes: int = 5,
    in_channels: int = 6,
    scale_factor: int = 4,
) -> SuperResolutionMapper:
    unmixer = DeepSpectralUnmixingNetwork(in_channels, num_classes)
    allocator = SubPixelAllocationNetwork(
        num_classes=num_classes, in_channels=in_channels, scale_factor=scale_factor
    )
    return SuperResolutionMapper(unmixer, allocator)


def load_model(
    weights_path: Optional[str] = None,
    device: str = "cuda",
    scale_factor: int = 4,
) -> Tuple[SuperResolutionMapper, torch.device]:
    dev = torch.device(device if torch.cuda.is_available() else "cpu")
    if dev.type == "cpu":
        threads = int(os.environ.get("TORCH_NUM_THREADS", "4"))
        torch.set_num_threads(threads)
        log.info("Configured PyTorch CPU threads: %d", threads)
    model = build_model(scale_factor=scale_factor)
    has_trained_weights = False
    if weights_path and os.path.exists(weights_path):
        raw_state = torch.load(weights_path, map_location=dev)
        state = raw_state.get("model", raw_state.get("state_dict", raw_state))
        expected = model.state_dict()
        compatible = {
            key: value for key, value in state.items()
            if key in expected and expected[key].shape == value.shape
        }
        # A differently-shaped image-SR checkpoint must never be mistaken for this
        # mapper: `strict=False` otherwise leaves most of the network random.
        if len(compatible) >= int(0.95 * len(expected)):
            model.load_state_dict(compatible, strict=False)
            has_trained_weights = True
            log.info("Loaded compatible SRM weights from %s", weights_path)
        else:
            log.warning("Checkpoint %s is incompatible with GeoSRM (%d/%d tensors match); using spectral baseline.",
                        weights_path, len(compatible), len(expected))
    if not has_trained_weights:
        # Never use random network parameters for a map.  The spectral baseline in
        # run_srm is deterministic and is deliberately used until a compatible SRM
        # checkpoint has been supplied.
        log.warning("No trained SRM weights at %s — using spectral baseline.", weights_path)
    model.has_trained_weights = has_trained_weights
    return model.to(dev).eval(), dev


def spectral_abundances(x: torch.Tensor) -> torch.Tensor:
    """Deterministic Sentinel-2 land-cover baseline for an untrained deployment.

    It is not a replacement for a calibrated model, but it is vastly safer than
    reporting a random neural prediction as land cover.  The bare-soil score uses
    *dryness* (SWIR relative to NIR), rather than raw SWIR brightness; this prevents
    the previous all-barren failure over bright impervious urban surfaces.
    """
    b02, b03, b04, b08, b11, b12 = (x[:, i : i + 1] for i in range(6))
    ndvi = (b08 - b04) / (b08 + b04 + 1e-6)
    ndwi = (b03 - b08) / (b03 + b08 + 1e-6)
    mndwi = (b03 - b11) / (b03 + b11 + 1e-6)
    ndbi = (b11 - b08) / (b11 + b08 + 1e-6)
    dryness = (b12 - b08) / (b12 + b08 + 1e-6)

    # The scores intentionally favour built-up in the ambiguous low-vegetation
    # region unless there is strong SWIR dryness evidence for exposed soil.
    built = 5.0 * ndbi + 1.5 * b04 - 2.0 * ndvi - 1.0 * dryness
    water = 8.0 * ndwi + 5.0 * mndwi - 2.0 * b08 - 2.0 * b11
    vegetation = 8.0 * (ndvi - 0.22) - 2.0 * ndbi
    cropland = 6.0 * (ndvi - 0.10) - 3.0 * (ndvi - 0.55).relu() - 1.0 * ndbi
    soil = 7.0 * (dryness - 0.12) + 2.0 * (b12 - b04) - 2.0 * ndvi
    return torch.softmax(torch.cat([built, water, vegetation, cropland, soil], dim=1) * 3.0, dim=1)


def worldcover_abundances(
    bbox: list[float], height: int, width: int, device: torch.device
) -> Optional[torch.Tensor]:
    """Read ESA WorldCover v200 for a single 3° tile and return one-hot abundances.

    WorldCover is an independently validated 10 m Sentinel-1/Sentinel-2 product. It
    is used only when this project has no compatible trained GeoSRM checkpoint. This
    avoids presenting random or heuristic class labels as a land-cover analysis.
    """
    west, south, east, north = bbox
    lon_tile = math.floor(west / 3.0) * 3
    lat_tile = math.floor(south / 3.0) * 3
    if east > lon_tile + 3.0 or north > lat_tile + 3.0:
        log.warning("AOI crosses an ESA WorldCover tile boundary; skipping reference fallback.")
        return None

    tile = f"{'N' if lat_tile >= 0 else 'S'}{abs(lat_tile):02d}{'E' if lon_tile >= 0 else 'W'}{abs(lon_tile):03d}"
    url = WORLDCOVER_URL.format(tile=tile)
    try:
        with rasterio.open(url) as src:
            window = from_bounds(west, south, east, north, src.transform)
            labels = src.read(
                1, window=window, out_shape=(height, width), resampling=Resampling.nearest
            )
    except Exception as exc:  # Network/reference data are optional at runtime.
        log.warning("Could not read ESA WorldCover tile %s: %s", tile, exc)
        return None

    classes = np.full(labels.shape, 4, dtype=np.int64)
    for source, target in _WORLDCOVER_CLASS_MAP.items():
        classes[labels == source] = target
    one_hot = F.one_hot(torch.from_numpy(classes), num_classes=len(CLASSES))
    return one_hot.permute(2, 0, 1).unsqueeze(0).float().to(device)


@torch.no_grad()
def run_srm(
    tensor: np.ndarray,
    model: SuperResolutionMapper,
    device: torch.device,
    scale_factor: int = 4,
    patch: int = 256,
    overlap: int = 32,
    apply_mrf: bool = True,
    reference_abundances: Optional[torch.Tensor] = None,
) -> Dict:
    """Super-resolve a (B=6, H, W) array to an (H*S, W*S) class map.

    Large AOIs are cropped into overlapping patches before entering the network; this is
    what keeps VRAM under the 8 GB budget and is the automatic mitigation for OOM during
    a live demo. Overlapping margins are trimmed on write-back so seams do not appear.
    """
    started = time.perf_counter()
    _, height, width = tensor.shape
    s = scale_factor
    stride = patch - overlap

    classes = np.full((height * s, width * s), 255, dtype=np.uint8)
    abundance_sum = np.zeros((len(CLASSES), height, width), dtype=np.float32)

    for top in range(0, height, stride):
        for left in range(0, width, stride):
            bottom = min(top + patch, height)
            right = min(left + patch, width)
            chunk = tensor[:, top:bottom, left:right]
            if chunk.shape[1] < 8 or chunk.shape[2] < 8:
                continue

            x = torch.from_numpy(chunk).unsqueeze(0).to(device)
            if reference_abundances is not None:
                abundances = reference_abundances[:, :, top:bottom, left:right]
                logits = F.interpolate(torch.log(abundances + 1e-6), scale_factor=s, mode="nearest")
            elif getattr(model, "has_trained_weights", False):
                abundances = model.unmixer(x)
                logits = model.allocator(x, abundances)
            else:
                abundances = spectral_abundances(x)
                # Repeating the coarse abundance as the unary score preserves the
                # physically constrained allocation without inventing fine detail.
                logits = F.interpolate(torch.log(abundances + 1e-6), scale_factor=s, mode="nearest")
            if apply_mrf:
                logits = mrf_smooth(logits)
            cls = allocate_subpixels(logits, abundances, s)[0].cpu().numpy().astype(np.uint8)

            # Trim the overlap margin except at the array edges.
            trim_t = 0 if top == 0 else overlap // 2
            trim_l = 0 if left == 0 else overlap // 2
            classes[
                (top + trim_t) * s : bottom * s,
                (left + trim_l) * s : right * s,
            ] = cls[trim_t * s :, trim_l * s :]
            abundance_sum[:, top:bottom, left:right] = abundances[0].cpu().numpy()

    elapsed = time.perf_counter() - started
    mass_error = float(np.abs(abundance_sum.sum(axis=0) - 1.0).max())
    log.info("SRM complete in %.2fs (mass error %.2e)", elapsed, mass_error)

    return {
        "classes": classes,
        "abundances": abundance_sum,
        "execution_time_seconds": round(elapsed, 3),
        "mass_conservation_error": mass_error,
    }


def class_distribution(classes: np.ndarray) -> Dict[str, float]:
    valid = classes != 255
    total = int(valid.sum())
    if total == 0:
        return {name: 0.0 for name in CLASSES}
    return {
        name: round(100.0 * float((classes == idx).sum()) / total, 2)
        for idx, name in enumerate(CLASSES)
    }
