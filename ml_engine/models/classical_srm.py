"""Classical super-resolution mapping: constrained unmixing + pixel swapping.

Super-resolution mapping predates deep learning, and the classical formulation needs no
training at all. Two stages, matching the two stages of the learned pipeline:

  1. Fully Constrained Least Squares (FCLS) unmixing against known endmember spectra,
     solved by projected gradient onto the probability simplex. The simplex projection
     enforces both physical constraints exactly, by construction:
         A[c] >= 0   and   sum_c A[c] = 1

  2. Iterated spatial allocation (Atkinson's pixel swapping). Sub-pixel class counts are
     fixed by the abundances; only their *arrangement* is optimised, by repeatedly
     scoring each sub-pixel on how much like-class neighbourhood it would gain. This is
     a direct minimisation of the spatial energy functional in the PRD.

Its value is not just that it works untrained. Every output is traceable to measured
spectra and an explicit objective, so nothing can be hallucinated — which is exactly the
property the project claims. The learned model is the accuracy upgrade on top.
"""
from typing import Optional

import torch
import torch.nn.functional as F

CLASSES = ["built_up", "water", "vegetation", "cropland", "bare_soil"]

# Representative Sentinel-2 L2A surface reflectance endmembers, band order
# B02 (490 nm), B03 (560), B04 (665), B08 (842), B11 (1610), B12 (2190).
#
# Several classes need more than one endmember, because a single spectrum cannot cover
# the range of materials inside them -- the standard MESMA argument. The two that matter
# most for Indian scenes:
#
#   * Built-up splits into bright concrete and dark asphalt. They sit at opposite ends of
#     the reflectance range, and a concrete-only endmember misses roads entirely, which
#     is precisely the "narrow linear structures" case the problem statement is about.
#   * Water splits into clear and sediment-laden. Turbid water is the norm in Indian
#     rivers, tanks and coastal margins, and reads far brighter in red than clear water.
#
# Each row is one endmember; ENDMEMBER_CLASS maps it back to an output class, and the
# abundances of endmembers sharing a class are summed after unmixing.
_ENDMEMBER_TABLE = [
    #  name                  B02    B03    B04    B08    B11    B12     class
    ("concrete / roofing", [0.140, 0.155, 0.175, 0.200, 0.250, 0.230], "built_up"),
    ("asphalt / tarmac",   [0.075, 0.085, 0.095, 0.105, 0.115, 0.100], "built_up"),
    # Building shadow. Without it, dense urban blocks classify as water: both are dark
    # in the visible. Shadow is not black: it is lit by blue-rich diffuse skylight and
    # by bounce from nearby surfaces, so it keeps several times the NIR and SWIR of clear
    # water, which is what separates them. Set it darker than this and it starts stealing
    # from genuine water -- at [0.035, 0.040, 0.035, 0.045, 0.030, 0.022] a pure-water
    # pixel unmixes to only 69% water. It belongs to built_up, being cast by it.
    ("building shadow",    [0.085, 0.090, 0.088, 0.115, 0.100, 0.080], "built_up"),
    ("clear water",        [0.035, 0.045, 0.030, 0.012, 0.006, 0.004], "water"),
    ("turbid water",       [0.060, 0.085, 0.075, 0.040, 0.018, 0.012], "water"),
    ("dense vegetation",   [0.028, 0.055, 0.032, 0.400, 0.180, 0.075], "vegetation"),
    ("cropland",           [0.045, 0.075, 0.070, 0.300, 0.230, 0.130], "cropland"),
    ("bright sand",        [0.150, 0.200, 0.260, 0.330, 0.400, 0.360], "bare_soil"),
    ("dark soil",          [0.080, 0.105, 0.140, 0.190, 0.260, 0.230], "bare_soil"),
]

ENDMEMBER_NAMES = [row[0] for row in _ENDMEMBER_TABLE]
ENDMEMBER_CLASS = [CLASSES.index(row[2]) for row in _ENDMEMBER_TABLE]
ENDMEMBERS = torch.tensor([row[1] for row in _ENDMEMBER_TABLE], dtype=torch.float32).T


def collapse_to_classes(endmember_abundances: torch.Tensor) -> torch.Tensor:
    """Sum endmember abundances into their output classes.

    Summing preserves the sum-to-one property exactly: the endmember abundances already
    sum to 1, and every endmember belongs to exactly one class.
    """
    e, h, w = endmember_abundances.shape
    out = torch.zeros(len(CLASSES), h, w, dtype=endmember_abundances.dtype,
                      device=endmember_abundances.device)
    index = torch.tensor(ENDMEMBER_CLASS, device=endmember_abundances.device)
    out.index_add_(0, index, endmember_abundances)
    return out


_DIAG = 1.0 / (2.0**0.5)
NEIGHBOUR_KERNEL = torch.tensor(
    [[_DIAG, 1.0, _DIAG],
     [1.0,   0.0, 1.0],
     [_DIAG, 1.0, _DIAG]],
    dtype=torch.float32,
)


def project_to_simplex(v: torch.Tensor) -> torch.Tensor:
    """Euclidean projection of each row onto the probability simplex.

    Duchi et al. (2008). This is what makes the sum-to-one and non-negativity
    constraints exact rather than merely encouraged.

    Args:
        v: (N, C) unconstrained scores.
    Returns:
        (N, C) rows that are non-negative and sum to exactly 1.
    """
    n, c = v.shape
    u, _ = torch.sort(v, dim=1, descending=True)
    cumulative = u.cumsum(dim=1) - 1.0
    index = torch.arange(1, c + 1, device=v.device, dtype=v.dtype).unsqueeze(0)
    condition = (u - cumulative / index) > 0
    # Number of active components per row (at least one by construction).
    rho = condition.to(v.dtype).sum(dim=1).clamp(min=1).long()
    theta = cumulative.gather(1, (rho - 1).unsqueeze(1)) / rho.unsqueeze(1).to(v.dtype)
    return (v - theta).clamp(min=0.0)


def unmix_fcls(
    spectra: torch.Tensor,
    endmembers: Optional[torch.Tensor] = None,
    iterations: int = 200,
) -> torch.Tensor:
    """Fully constrained least squares unmixing.

    Minimises ||E a - x||^2 over the simplex, by projected gradient descent. The step
    size is 1/L with L the largest eigenvalue of E^T E, which is the standard choice
    that guarantees monotone descent.

    Args:
        spectra: (B, H, W) surface reflectance.
        endmembers: (B, C) matrix; defaults to ENDMEMBERS.
    Returns:
        (C, H, W) per-class abundances, non-negative and summing to 1 per pixel.
        Endmembers sharing a class are summed after solving, so a road pixel that is
        part concrete and part asphalt still reports as built-up.
    """
    e = (ENDMEMBERS if endmembers is None else endmembers).to(spectra.device)
    b, h, w = spectra.shape
    x = spectra.reshape(b, h * w).T                      # (N, B)

    gram = e.T @ e                                       # (C, C)
    step = 1.0 / torch.linalg.eigvalsh(gram).max().clamp(min=1e-8)

    c = e.shape[1]
    a = torch.full((h * w, c), 1.0 / c, device=spectra.device, dtype=spectra.dtype)
    xe = x @ e                                           # (N, C)

    for _ in range(iterations):
        grad = a @ gram - xe
        a = project_to_simplex(a - step * grad)

    return collapse_to_classes(a.T.reshape(c, h, w))


def allocate_by_swapping(
    abundances: torch.Tensor,
    scale_factor: int = 4,
    iterations: int = 8,
) -> torch.Tensor:
    """Arrange sub-pixels to maximise spatial autocorrelation, quotas held fixed.

    Atkinson's pixel swapping, expressed as iterated allocation: score every sub-pixel by
    the like-class support of its 8-neighbourhood, then re-allocate under the same
    integer quotas. Repeating this drives the spatial energy down while the class
    proportions stay exactly what the unmixing predicted.

    Args:
        abundances: (C, H, W) summing to 1 along dim 0.
        scale_factor: S; each coarse pixel becomes S*S sub-pixels.
    Returns:
        (H*S, W*S) int64 class map.
    """
    from .swin_srm import allocate_subpixels

    c, h, w = abundances.shape
    a = abundances.unsqueeze(0)                          # (1, C, H, W)
    s = scale_factor

    # Start from the abundances themselves, upsampled: the best guess before any
    # spatial reasoning, and a smooth prior that keeps the first allocation sane.
    logits = F.interpolate(a, scale_factor=s, mode="bilinear", align_corners=False)
    kernel = NEIGHBOUR_KERNEL.to(a.device).view(1, 1, 3, 3).repeat(c, 1, 1, 1)
    prior = logits.clone()

    classes = allocate_subpixels(logits, a, s)
    for _ in range(iterations):
        onehot = F.one_hot(classes, num_classes=c).permute(0, 3, 1, 2).to(a.dtype)
        support = F.conv2d(onehot, kernel, padding=1, groups=c)
        # The prior keeps a sub-pixel from drifting to a class its own spectrum rules
        # out just because the neighbours are numerous.
        logits = support + 0.5 * prior
        classes = allocate_subpixels(logits, a, s)

    return classes


def super_resolve(
    spectra: torch.Tensor,
    scale_factor: int = 4,
    unmix_iterations: int = 200,
    swap_iterations: int = 8,
):
    """Full classical pipeline: (B, H, W) reflectance -> abundances and sub-pixel map."""
    abundances = unmix_fcls(spectra, iterations=unmix_iterations)
    classes = allocate_by_swapping(abundances, scale_factor, swap_iterations)
    return abundances, classes[0]
