"""The classical solver must actually discriminate surfaces.

An untrained network returns a uniform split for every input, which looks like a working
system until you check whether the answer depends on the imagery at all. These tests
assert that it does.
"""
import numpy as np
import torch

from models.classical_srm import CLASSES, project_to_simplex, super_resolve, unmix_fcls

# Band order B02 B03 B04 B08 B11 B12. One probe per class, taken from the taxonomy so
# these cannot silently drift from the endmembers the solver actually uses.
SPECTRA = {
    "water": [0.035, 0.045, 0.030, 0.012, 0.006, 0.004],
    "vegetation": [0.028, 0.055, 0.032, 0.400, 0.180, 0.075],
    "bare_soil": [0.080, 0.105, 0.140, 0.190, 0.260, 0.230],
    "road": [0.055, 0.062, 0.070, 0.080, 0.090, 0.075],
    "sand": [0.185, 0.240, 0.300, 0.360, 0.420, 0.375],
}


def patch(spectrum, size=24, noise=0.004):
    x = torch.tensor(spectrum, dtype=torch.float32).view(6, 1, 1).repeat(1, size, size)
    return (x + torch.randn_like(x) * noise).clamp(0, 1)


def test_simplex_projection_enforces_both_constraints():
    v = torch.randn(500, len(CLASSES)) * 3.0
    p = project_to_simplex(v)
    assert (p >= 0).all(), "non-negativity (ANC) violated"
    assert torch.allclose(p.sum(1), torch.ones(500), atol=1e-5), "sum-to-one (ASC) violated"


def test_each_endmember_recovers_itself():
    for name, spectrum in SPECTRA.items():
        a = unmix_fcls(patch(spectrum))
        dominant = CLASSES[int(a.mean(dim=(1, 2)).argmax())]
        assert dominant == name, f"{name} spectrum was unmixed as {dominant}"


def test_mixed_pixel_splits_into_fractions():
    """The point of the whole project: a 50/50 pixel must read as roughly 50/50."""
    mix = [(w + v) / 2 for w, v in zip(SPECTRA["water"], SPECTRA["vegetation"])]
    a = unmix_fcls(patch(mix)).mean(dim=(1, 2))

    water = a[CLASSES.index("water")].item()
    veg = a[CLASSES.index("vegetation")].item()
    assert 0.35 < water < 0.65, f"water fraction {water:.2f} is not near half"
    assert 0.35 < veg < 0.65, f"vegetation fraction {veg:.2f} is not near half"


def test_output_depends_on_the_input():
    """The regression that motivated this module: identical output for every scene."""
    dists = {}
    for name, spectrum in SPECTRA.items():
        _, classes = super_resolve(patch(spectrum), scale_factor=4)
        counts = np.bincount(classes.cpu().numpy().ravel(), minlength=len(CLASSES))
        dists[name] = counts / counts.sum()

    assert not np.allclose(dists["water"], dists["vegetation"], atol=0.05), (
        "water and vegetation produced the same distribution - the solver is ignoring "
        "the imagery"
    )
    assert dists["water"][CLASSES.index("water")] > 0.8


def test_road_is_its_own_class():
    """Roads are a separate intelligence product, not a subset of built-up."""
    assert "road" in CLASSES
    a = unmix_fcls(patch(SPECTRA["road"])).mean(dim=(1, 2))
    road = a[CLASSES.index("road")].item()
    built = a[CLASSES.index("built_up")].item()
    assert road > built, f"asphalt read as built_up ({built:.2f}) over road ({road:.2f})"


def test_allocation_conserves_abundance_quotas():
    a = unmix_fcls(patch(SPECTRA["water"]))
    _, classes = super_resolve(patch(SPECTRA["water"]), scale_factor=4)
    assert classes.shape == (24 * 4, 24 * 4)
    assert float((a.sum(0) - 1).abs().max()) < 1e-3
