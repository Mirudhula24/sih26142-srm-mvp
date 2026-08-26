"""Smoke tests for the gateway contracts."""
import numpy as np
import pytest
from fastapi.testclient import TestClient

from main import app
from services.exporter import class_metrics

client = TestClient(app)


def test_health_reports_five_classes():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["scale_factor"] == 4
    assert len(body["classes"]) == 5


def test_class_metrics_percentages_sum_to_100():
    classes = np.random.randint(0, 5, size=(64, 64)).astype(np.uint8)
    metrics = class_metrics(classes, pixel_size_m=2.5)

    total_pct = sum(m["percent"] for m in metrics.values())
    assert total_pct == pytest.approx(100.0, abs=0.05)

    total_area = sum(m["area_sqm"] for m in metrics.values())
    assert total_area == pytest.approx(64 * 64 * 2.5**2)


def test_fetch_rejects_malformed_aoi():
    res = client.post("/api/v1/imagery/fetch", json={"aoi_geojson": {"type": "Point"}})
    assert res.status_code == 422
