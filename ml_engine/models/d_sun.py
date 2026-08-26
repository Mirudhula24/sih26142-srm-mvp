"""Deep Spectral Unmixing Network (D-SUN).

Predicts a fractional abundance tensor A of shape (B, C, H, W) from a multispectral
input X of shape (B, 6, H, W), at the *coarse* 10 m resolution.

The final softmax makes the two physical constraints structural rather than learned:

    A[b, c, i, j] >= 0          (non-negativity, ANC)
    sum_c A[b, c, i, j] == 1    (sum-to-one, ASC)

so no amount of training can produce a mass-violating output.
"""
import torch
import torch.nn as nn


class ResidualBlock(nn.Module):
    def __init__(self, channels: int):
        super().__init__()
        self.body = nn.Sequential(
            nn.Conv2d(channels, channels, 3, padding=1),
            nn.BatchNorm2d(channels),
            nn.GELU(),
            nn.Conv2d(channels, channels, 3, padding=1),
            nn.BatchNorm2d(channels),
        )
        self.act = nn.GELU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.act(x + self.body(x))


class DeepSpectralUnmixingNetwork(nn.Module):
    def __init__(
        self,
        in_channels: int = 6,
        num_classes: int = 7,
        width: int = 64,
        depth: int = 4,
    ):
        super().__init__()
        self.num_classes = num_classes

        self.stem = nn.Sequential(
            nn.Conv2d(in_channels, width, 3, padding=1),
            nn.GELU(),
        )
        self.trunk = nn.Sequential(*[ResidualBlock(width) for _ in range(depth)])

        # 1x1 head: abundances are a per-pixel spectral property, so the head must not
        # mix neighbouring pixels — that job belongs to the allocation network.
        self.head = nn.Conv2d(width, num_classes, 1)

        # Endmember matrix used by the reconstruction term of the unmixing loss:
        # X_hat = E @ A must return the observed coarse reflectance.
        self.endmembers = nn.Parameter(torch.rand(in_channels, num_classes))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """(B, 6, H, W) -> (B, C, H, W) abundances summing to 1 along dim=1."""
        feats = self.trunk(self.stem(x))
        return torch.softmax(self.head(feats), dim=1)

    def reconstruct(self, abundances: torch.Tensor) -> torch.Tensor:
        """Linear mixing model: rebuild the coarse spectra from the abundances."""
        b, c, h, w = abundances.shape
        flat = abundances.reshape(b, c, h * w)
        mixed = torch.matmul(self.endmembers.clamp(min=0.0), flat)
        return mixed.reshape(b, -1, h, w)
