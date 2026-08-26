"""The ingest -> GPU worker hand-off contract.

These two workers live in different images, so nothing but this archive format keeps
them in agreement. If the keys drift, inference silently loses its georeferencing.
"""
import numpy as np
import pytest
from affine import Affine

from utils import tensor_exchange


def write_bundle(path, height=8, width=8):
    """Mirror of backend/services/tensor_exchange.save."""
    transform = Affine(10.0, 0.0, 700000.0, 0.0, -10.0, 3100000.0)
    np.savez_compressed(
        path,
        tensor=np.random.rand(6, height, width).astype(np.float32),
        valid_mask=np.ones((height, width), dtype=bool),
        transform=np.asarray(transform[:6], dtype=np.float64),
        crs=np.array("EPSG:32643"),
        bbox=np.asarray([77.1, 28.7, 77.2, 28.8], dtype=np.float64),
    )
    return transform


def test_round_trip_preserves_georeferencing(tmp_path):
    path = tmp_path / "job.npz"
    transform = write_bundle(str(path))

    bundle = tensor_exchange.load(str(path))

    assert bundle["tensor"].shape == (6, 8, 8)
    assert bundle["tensor"].dtype == np.float32
    assert bundle["valid_mask"].dtype == np.bool_
    assert bundle["crs"] == "EPSG:32643"
    assert bundle["transform"] == transform, "affine must survive the hand-off intact"
    assert bundle["bbox"] == [77.1, 28.7, 77.2, 28.8]


def test_missing_bundle_names_the_volume_problem(tmp_path):
    with pytest.raises(FileNotFoundError, match="TENSOR_EXCHANGE_DIR"):
        tensor_exchange.load(str(tmp_path / "absent.npz"))


def test_cleanup_removes_file_and_tolerates_absence(tmp_path):
    path = tmp_path / "job.npz"
    write_bundle(str(path))

    tensor_exchange.cleanup(str(path))
    assert not path.exists()

    tensor_exchange.cleanup(str(path))  # second call must not raise
