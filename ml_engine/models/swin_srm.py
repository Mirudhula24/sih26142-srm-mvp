"""Swin Transformer sub-pixel spatial allocation head.

Takes the coarse abundance tensor A (B, C, H, W) plus multispectral context and
produces sub-pixel class logits at (B, C, H*S, W*S). The transformer supplies the
spatial prior; the hard sum-to-one allocation is enforced afterwards by
`allocate_subpixels`, which guarantees exactly round(A * S^2) sub-pixels per class.
"""
from typing import Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F


def window_partition(x: torch.Tensor, window: int) -> torch.Tensor:
    b, h, w, c = x.shape
    x = x.view(b, h // window, window, w // window, window, c)
    return x.permute(0, 1, 3, 2, 4, 5).contiguous().view(-1, window * window, c)


def window_reverse(windows: torch.Tensor, window: int, h: int, w: int) -> torch.Tensor:
    b = windows.shape[0] // (h * w // window // window)
    x = windows.view(b, h // window, w // window, window, window, -1)
    return x.permute(0, 1, 3, 2, 4, 5).contiguous().view(b, h, w, -1)


class WindowAttentionBlock(nn.Module):
    """Swin-style block: windowed MSA + MLP, with optional cyclic shift."""

    def __init__(self, dim: int, num_heads: int = 4, window: int = 8, shift: int = 0):
        super().__init__()
        self.dim, self.window, self.shift = dim, window, shift
        self.norm1 = nn.LayerNorm(dim)
        self.attn = nn.MultiheadAttention(dim, num_heads, batch_first=True)
        self.norm2 = nn.LayerNorm(dim)
        self.mlp = nn.Sequential(
            nn.Linear(dim, dim * 2), nn.GELU(), nn.Linear(dim * 2, dim)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (B, H, W, C) channels-last."""
        b, h, w, c = x.shape
        pad_h = (self.window - h % self.window) % self.window
        pad_w = (self.window - w % self.window) % self.window
        if pad_h or pad_w:
            x = F.pad(x.permute(0, 3, 1, 2), (0, pad_w, 0, pad_h)).permute(0, 2, 3, 1)
        _, hp, wp, _ = x.shape

        shortcut = x
        x = self.norm1(x)
        if self.shift:
            x = torch.roll(x, shifts=(-self.shift, -self.shift), dims=(1, 2))

        windows = window_partition(x, self.window)
        attended, _ = self.attn(windows, windows, windows, need_weights=False)
        x = window_reverse(attended, self.window, hp, wp)

        if self.shift:
            x = torch.roll(x, shifts=(self.shift, self.shift), dims=(1, 2))
        x = shortcut + x
        x = x + self.mlp(self.norm2(x))
        return x[:, :h, :w, :]


class SubPixelAllocationNetwork(nn.Module):
    """SwinIR-style backbone with a PixelShuffle upsampler to the fine grid."""

    def __init__(
        self,
        num_classes: int = 5,
        in_channels: int = 6,
        dim: int = 96,
        depth: int = 6,
        num_heads: int = 4,
        window: int = 8,
        scale_factor: int = 4,
    ):
        super().__init__()
        self.scale_factor = scale_factor
        self.num_classes = num_classes

        self.embed = nn.Conv2d(in_channels + num_classes, dim, 3, padding=1)
        self.blocks = nn.ModuleList(
            [
                WindowAttentionBlock(dim, num_heads, window, shift=0 if i % 2 == 0 else window // 2)
                for i in range(depth)
            ]
        )
        self.fuse = nn.Conv2d(dim, dim, 3, padding=1)
        self.upsample = nn.Sequential(
            nn.Conv2d(dim, num_classes * scale_factor**2, 3, padding=1),
            nn.PixelShuffle(scale_factor),
        )

    def forward(self, spectra: torch.Tensor, abundances: torch.Tensor) -> torch.Tensor:
        """-> sub-pixel class logits (B, C, H*S, W*S)."""
        x = self.embed(torch.cat([spectra, abundances], dim=1))
        residual = x
        h = x.permute(0, 2, 3, 1)
        for block in self.blocks:
            h = block(h)
        x = self.fuse(h.permute(0, 3, 1, 2)) + residual
        return self.upsample(x)


def allocate_subpixels(
    logits: torch.Tensor, abundances: torch.Tensor, scale_factor: int = 4
) -> torch.Tensor:
    """Hard, mass-conserving allocation of sub-pixels to classes.

    For every coarse pixel, exactly round(A[c] * S^2) of its S^2 sub-pixels are assigned
    to class c (with the rounding remainder given to the largest fractional parts, so the
    counts always sum to S^2). Within that quota the sub-pixel *positions* are the ones
    the transformer scored highest — that is where spatial autocorrelation comes from.

    Args:
        logits:     (B, C, H*S, W*S) sub-pixel scores from the allocation network.
        abundances: (B, C, H, W) coarse fractions summing to 1 along dim=1.

    Returns:
        (B, H*S, W*S) int64 class map.
    """
    b, c, fh, fw = logits.shape
    s = scale_factor
    h, w = fh // s, fw // s
    n_sub = s * s

    # Integer quotas per coarse pixel, largest-remainder method.
    exact = abundances * n_sub                                  # (B, C, H, W)
    quota = torch.floor(exact).long()
    remainder = n_sub - quota.sum(dim=1)                        # (B, H, W)
    frac_rank = torch.argsort(exact - quota.float(), dim=1, descending=True)
    rank_pos = torch.argsort(frac_rank, dim=1)                  # rank of each class
    quota = quota + (rank_pos < remainder.unsqueeze(1)).long()

    # Score every sub-pixel within its coarse cell: (B, C, H, W, S*S)
    scores = (
        logits.view(b, c, h, s, w, s)
        .permute(0, 1, 2, 4, 3, 5)
        .reshape(b, c, h, w, n_sub)
    )

    # Greedy assignment by descending score, respecting each class quota.
    flat_scores = scores.permute(0, 2, 3, 4, 1).reshape(-1, n_sub, c)   # (BHW, S^2, C)
    flat_quota = quota.permute(0, 2, 3, 1).reshape(-1, c).clone()        # (BHW, C)
    assignment = torch.full((flat_scores.shape[0], n_sub), -1, dtype=torch.long,
                            device=logits.device)

    order = flat_scores.max(dim=2).values.argsort(dim=1, descending=True)
    for step in range(n_sub):
        idx = order[:, step]                                             # (BHW,)
        cell = flat_scores.gather(1, idx.view(-1, 1, 1).expand(-1, 1, c)).squeeze(1)
        cell = cell.masked_fill(flat_quota <= 0, float("-inf"))
        chosen = cell.argmax(dim=1)
        assignment.scatter_(1, idx.unsqueeze(1), chosen.unsqueeze(1))
        flat_quota.scatter_add_(1, chosen.unsqueeze(1),
                                torch.full_like(chosen.unsqueeze(1), -1))

    return (
        assignment.view(b, h, w, s, s)
        .permute(0, 1, 3, 2, 4)
        .reshape(b, fh, fw)
    )


class SuperResolutionMapper(nn.Module):
    """End-to-end SRM: D-SUN unmixing -> SwinIR allocation -> hard sub-pixel assignment."""

    def __init__(self, unmixer: nn.Module, allocator: SubPixelAllocationNetwork):
        super().__init__()
        self.unmixer = unmixer
        self.allocator = allocator

    def forward(self, spectra: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        abundances = self.unmixer(spectra)
        logits = self.allocator(spectra, abundances)
        classes = allocate_subpixels(logits, abundances, self.allocator.scale_factor)
        return abundances, logits, classes
