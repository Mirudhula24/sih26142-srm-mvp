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


def physical_unmix(x: torch.Tensor) -> torch.Tensor:
    """Physics-based spectral unmixing prior for Sentinel-2 6-band input.

    Channels: B02(0), B03(1), B04(2), B08(3), B11(4), B12(5)
    Classes: 0: built_up, 1: water, 2: vegetation, 3: cropland, 4: bare_soil
    """
    b02 = x[:, 0:1, :, :]
    b03 = x[:, 1:2, :, :]
    b04 = x[:, 2:3, :, :]
    b08 = x[:, 3:4, :, :]
    b11 = x[:, 4:5, :, :]
    b12 = x[:, 5:6, :, :]

    ndvi = (b08 - b04) / (b08 + b04 + 1e-6)
    ndwi = (b03 - b08) / (b03 + b08 + 1e-6)
    ndbi = (b11 - b08) / (b11 + b08 + 1e-6)
    mndwi = (b03 - b11) / (b03 + b11 + 1e-6)

    s_built = 3.5 * ndbi + 2.0 * b11 + 1.5 * b04 - 2.0 * ndvi
    s_water = 3.5 * ndwi + 2.0 * mndwi - 3.0 * b08 - 2.0 * b11
    s_veg = 4.0 * ndvi - 2.0 * ndbi - 1.0 * b11
    s_crop = 2.0 * (ndvi - 0.2).clamp(min=-0.5, max=0.5) + 1.0 * b03 - 1.0 * ndbi
    s_soil = 3.0 * b12 + 2.0 * b11 + 1.5 * b04 - 2.0 * ndvi - 2.0 * ndwi

    logits = torch.cat([s_built, s_water, s_veg, s_crop, s_soil], dim=1)
    return torch.softmax(logits * 3.0, dim=1)


class DeepSpectralUnmixingNetwork(nn.Module):
    def __init__(
        self,
        in_channels: int = 6,
        num_classes: int = 5,
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
        phys = physical_unmix(x)
        feats = self.trunk(self.stem(x))
        # Combine physical spectral unmixing prior with neural network residual head
        return torch.softmax(torch.log(phys + 1e-6) + self.head(feats), dim=1)

    def reconstruct(self, abundances: torch.Tensor) -> torch.Tensor:
        """Linear mixing model: rebuild the coarse spectra from the abundances."""
        b, c, h, w = abundances.shape
        flat = abundances.reshape(b, c, h * w)
        mixed = torch.matmul(self.endmembers.clamp(min=0.0), flat)
        return mixed.reshape(b, -1, h, w)
