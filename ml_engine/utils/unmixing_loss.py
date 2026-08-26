"""Loss terms for the SRM pipeline.

L_total = w_abund * L_abundance      (fractions match the reference land cover)
        + w_recon * L_reconstruct    (linear mixing model rebuilds observed spectra)
        + w_alloc * L_allocation     (sub-pixel cross-entropy against fine labels)
        + w_energy * L_spatial       (spatial autocorrelation / smoothness prior)
"""
from typing import Dict

import torch
import torch.nn as nn
import torch.nn.functional as F


def abundance_loss(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    """Per-pixel fractional agreement. Both tensors are (B, C, H, W) and sum to 1."""
    return F.l1_loss(pred, target)


def reconstruction_loss(observed: torch.Tensor, rebuilt: torch.Tensor) -> torch.Tensor:
    """Linear mixing model fidelity: || X - E @ A ||."""
    return F.mse_loss(rebuilt, observed)


def allocation_loss(logits: torch.Tensor, fine_labels: torch.Tensor) -> torch.Tensor:
    """Cross-entropy of sub-pixel logits against the downsampled VHR reference."""
    return F.cross_entropy(logits, fine_labels)


def spatial_energy(logits: torch.Tensor) -> torch.Tensor:
    """Differentiable surrogate for the 8-neighbourhood spatial energy functional.

    The discrete objective maximises sum over neighbour pairs of
    w_ab * delta(class_a, class_b) with w_ab an inverse-distance weight. Using the
    softmax probabilities, delta becomes the dot product of the class distributions,
    and the inverse-distance weights are 1 for the 4-neighbours and 1/sqrt(2) for the
    diagonals. We return the negated attraction, so minimising the loss maximises
    spatial autocorrelation.
    """
    p = torch.softmax(logits, dim=1)
    diag_w = 1.0 / (2.0 ** 0.5)

    attraction = (
        (p[:, :, :-1, :] * p[:, :, 1:, :]).sum(1).mean()          # vertical
        + (p[:, :, :, :-1] * p[:, :, :, 1:]).sum(1).mean()        # horizontal
        + diag_w * (p[:, :, :-1, :-1] * p[:, :, 1:, 1:]).sum(1).mean()
        + diag_w * (p[:, :, :-1, 1:] * p[:, :, 1:, :-1]).sum(1).mean()
    )
    return -attraction


def mass_conservation_error(abundances: torch.Tensor) -> torch.Tensor:
    """max |sum_c A - 1|. Acceptance benchmark requires this below 1e-3."""
    return (abundances.sum(dim=1) - 1.0).abs().max()


class SRMLoss(nn.Module):
    def __init__(
        self,
        w_abund: float = 1.0,
        w_recon: float = 0.5,
        w_alloc: float = 1.0,
        w_energy: float = 0.1,
    ):
        super().__init__()
        self.w_abund, self.w_recon = w_abund, w_recon
        self.w_alloc, self.w_energy = w_alloc, w_energy

    def forward(
        self,
        abundances: torch.Tensor,
        logits: torch.Tensor,
        spectra: torch.Tensor,
        rebuilt: torch.Tensor,
        target_abundance: torch.Tensor,
        fine_labels: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        l_abund = abundance_loss(abundances, target_abundance)
        l_recon = reconstruction_loss(spectra, rebuilt)
        l_alloc = allocation_loss(logits, fine_labels)
        l_energy = spatial_energy(logits)

        total = (
            self.w_abund * l_abund
            + self.w_recon * l_recon
            + self.w_alloc * l_alloc
            + self.w_energy * l_energy
        )
        return {
            "total": total,
            "abundance": l_abund.detach(),
            "reconstruction": l_recon.detach(),
            "allocation": l_alloc.detach(),
            "spatial_energy": l_energy.detach(),
            "mass_error": mass_conservation_error(abundances).detach(),
        }
