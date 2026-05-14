"""Smoke tests for PromQL coordinator helpers."""

from custom_components.promql.coordinator import _extract_scalar


def test_extract_scalar_from_scalar_result() -> None:
    payload = {
        "status": "success",
        "data": {"resultType": "scalar", "result": [1715000000.0, "42.5"]},
    }
    assert _extract_scalar(payload) == "42.5"


def test_extract_scalar_from_single_vector() -> None:
    payload = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{"metric": {}, "value": [1715000000.0, "1"]}],
        },
    }
    assert _extract_scalar(payload) == "1"


def test_extract_scalar_returns_none_for_multi_vector() -> None:
    payload = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {"metric": {"job": "a"}, "value": [1715000000.0, "1"]},
                {"metric": {"job": "b"}, "value": [1715000000.0, "2"]},
            ],
        },
    }
    assert _extract_scalar(payload) is None


def test_extract_scalar_returns_none_for_malformed() -> None:
    assert _extract_scalar({}) is None
    assert _extract_scalar({"data": {}}) is None
