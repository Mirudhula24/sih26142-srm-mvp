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
import os
import sys
from typing import Optional

import torch
import torch.nn.functional as F

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from taxonomy import CLASSES, ENDMEMBER_CLASS, ENDMEMBER_SPECTRA  # noqa: E402

ENDMEMBERS = torch.tensor(ENDMEMBER_SPECTRA, dtype=torch.float32).T  # (bands, endmembers)


def collapse_to_classes(endmember_abundances: torch.Tensor) -> torch.Tensor:
    """Sum endmember abundances into their output classes.

    Summing preserves sum-to-one exactly: the endmember abundances already sum to 1 and
    each endmember belongs to exactly one class.
    """
    _, h, w = endmember_abundances.shape
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
    sparsity: float = 0.006,
) -> torch.Tensor:
    """Fully constrained least squares unmixing.

    Minimises ||E a - x||^2 - sparsity * sum(a log a) over the simplex, by projected
    gradient descent. Note the sign: sum(a log a) is largest at the simplex vertices and
    smallest at the uniform point, so it is *maximised* to encourage purity. The step size is 1/L with L the largest eigenvalue of E^T E, the
    standard choice that guarantees monotone descent on the quadratic part.

    The entropy term is not cosmetic. Grey materials are spectrally flat, so concrete and
    asphalt can be reproduced almost exactly by mixing dark water with bright sand -- the
    residual is near zero either way and plain least squares has no reason to prefer the
    physically correct answer. A pure asphalt probe unmixed to 39% water before this term
    was added. Penalising entropy pushes the solution toward a single dominant endmember,
    which is what a genuinely pure pixel should look like. Keep the weight small: too
    large and true mixed pixels get forced to a vertex, destroying the sub-pixel
    fractions that are the entire point.

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
        if sparsity:
            grad = grad - sparsity * (torch.log(a.clamp(min=1e-8)) + 1.0)
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
