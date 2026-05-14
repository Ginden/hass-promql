"""Fixtures for PromQL integration tests."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def mock_prometheus_scalar() -> dict[str, Any]:
    """Prometheus API response for a scalar query."""
    return {
        "status": "success",
        "data": {
            "resultType": "scalar",
            "result": [1715000000.0, "42.5"],
        },
    }


@pytest.fixture
def mock_prometheus_vector() -> dict[str, Any]:
    """Prometheus API response for a single-element instant vector query."""
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {
                    "metric": {"__name__": "up", "job": "prometheus"},
                    "value": [1715000000.0, "1"],
                }
            ],
        },
    }
