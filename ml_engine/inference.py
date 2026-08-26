"""SRM inference: sliding-window tiling, D-SUN -> SwinIR -> MRF, COG-ready output."""
import logging
import os
import time
from typing import Dict, Optional, Tuple

import numpy as np
import torch

from models.d_sun import DeepSpectralUnmixingNetwork
from models.swin_srm import SubPixelAllocationNetwork, SuperResolutionMapper, allocate_subpixels
from utils.mrf_smooth import mrf_smooth

log = logging.getLogger(__name__)

from taxonomy import CLASSES  # noqa: E402  single source of truth


def build_model(
    num_classes: int = len(CLASSES),
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
    model = build_model(scale_factor=scale_factor)
    model.weights_loaded = False
    if weights_path and os.path.exists(weights_path):
        state = torch.load(weights_path, map_location=dev)
        incompatible = model.load_state_dict(state.get("model", state), strict=False)
        # strict=False tolerates a mismatched checkpoint silently, which is
        # indistinguishable from random initialisation at inference time. Treat a load
        # that populated nothing as no load at all.
        loaded = len(list(model.state_dict())) - len(incompatible.missing_keys)
        model.weights_loaded = loaded > 0
        log.info("Loaded %d tensors of SRM weights from %s", loaded, weights_path)
        if incompatible.missing_keys:
            log.warning("%d parameters were NOT in the checkpoint and stay random",
                        len(incompatible.missing_keys))
    else:
        log.warning(
            "No weights at %s. The learned path would emit noise, so inference will "
            "fall back to the classical SRM solver unless overridden.", weights_path)
    return model.to(dev).eval(), dev


@torch.no_grad()
def run_srm(
    tensor: np.ndarray,
    model: SuperResolutionMapper,
    device: torch.device,
    scale_factor: int = 4,
    patch: int = 256,
    overlap: int = 32,
    apply_mrf: bool = True,
    method: str = "auto",
) -> Dict:
    """Super-resolve a (B=6, H, W) array to an (H*S, W*S) class map.

    Large AOIs are cropped into overlapping patches before entering the network; this is
    what keeps VRAM under the 8 GB budget and is the automatic mitigation for OOM during
    a live demo. Overlapping margins are trimmed on write-back so seams do not appear.
    """
    # "auto" is the honest default: an untrained network produces a uniform class
    # split that ignores the imagery entirely, so fall back to the classical solver
    # rather than present noise as a result.
    if method == "auto":
        method = "learned" if getattr(model, "weights_loaded", False) else "classical"
    if method == "classical":
        return _run_classical(tensor, scale_factor, device)

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
            abundances = model.unmixer(x)
            logits = model.allocator(x, abundances)
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
        "method": "learned",
    }


@torch.no_grad()
def _run_classical(tensor: np.ndarray, scale_factor: int, device) -> Dict:
    """Constrained unmixing plus pixel swapping. No weights, no training."""
    from models.classical_srm import super_resolve

    started = time.perf_counter()
    x = torch.from_numpy(tensor).to(device)
    abundances, classes = super_resolve(x, scale_factor=scale_factor)

    abundance_np = abundances.cpu().numpy()
    elapsed = time.perf_counter() - started
    mass_error = float(np.abs(abundance_np.sum(axis=0) - 1.0).max())
    log.info("Classical SRM complete in %.2fs (mass error %.2e)", elapsed, mass_error)

    return {
        "classes": classes.cpu().numpy().astype(np.uint8),
        "abundances": abundance_np,
        "execution_time_seconds": round(elapsed, 3),
        "mass_conservation_error": mass_error,
        "method": "classical",
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
