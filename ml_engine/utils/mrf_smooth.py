"""Markov Random Field boundary smoothing — pure PyTorch/SciPy, no pydensecrf.

pydensecrf is an unmaintained Cython wrapper that fails to compile on Python 3.10 /
GCC 11, so the CRF step is replaced by an ICM (iterated conditional modes) pass over
the same 8-neighbourhood Potts energy. See docs/TECH_CLASHES.md (Clash 2).

Energy minimised:
    E(L) = sum_i unary_i(L_i) - beta * sum_{j in N8(i)} w_ij * delta(L_i, L_j)

The pass is mass-preserving *approximately*, not exactly. Run `enforce_quota` after it
if strict per-coarse-pixel abundance conservation must survive smoothing.
"""
import torch
import torch.nn.functional as F

# 8-neighbourhood inverse-distance kernel: 1 for edge neighbours, 1/sqrt(2) diagonals.
_DIAG = 1.0 / (2.0**0.5)
_NEIGHBOUR_KERNEL = torch.tensor(
    [[_DIAG, 1.0, _DIAG],
     [1.0,   0.0, 1.0],
     [_DIAG, 1.0, _DIAG]],
    dtype=torch.float32,
)


def mrf_smooth(
    logits: torch.Tensor,
    beta: float = 1.5,
    iterations: int = 5,
) -> torch.Tensor:
    """Refine sub-pixel class logits with an 8-neighbour Potts prior.

    Args:
        logits: (B, C, H, W) unary scores from the allocation network.
        beta:   smoothness weight. Higher removes more salt-and-pepper noise but
                starts eroding one-sub-pixel-wide features such as narrow roads.
        iterations: ICM sweeps. 5 is enough at S=4; more costs latency for no gain.

    Returns:
        (B, C, H, W) refined logits — argmax them for the class map.
    """
    b, c, h, w = logits.shape
    kernel = _NEIGHBOUR_KERNEL.to(logits.device).view(1, 1, 3, 3).repeat(c, 1, 1, 1)

    unary = logits
    current = logits
    for _ in range(iterations):
        probs = torch.softmax(current, dim=1)
        # Per-class neighbour support; grouped conv applies the kernel channel-wise.
        support = F.conv2d(probs, kernel, padding=1, groups=c)
        current = unary + beta * support
    return current


def enforce_quota(
    class_map: torch.Tensor, abundances: torch.Tensor, scale_factor: int = 4
) -> torch.Tensor:
    """Re-impose exact sub-pixel counts after smoothing may have perturbed them."""
    from models.swin_srm import allocate_subpixels

    b, h, w = class_map.shape
    c = abundances.shape[1]
    onehot = (
        F.one_hot(class_map.clamp(min=0), num_classes=c)
        .permute(0, 3, 1, 2)
        .float()
    )
    return allocate_subpixels(onehot, abundances, scale_factor)
