"""Smoke tests for PromQL coordinator helpers."""

from typing import Any, cast

import pytest

from custom_components.promql.const import CONF_QUERIES, CONF_QUERY, CONF_QUERY_ID
from custom_components.promql.coordinator import (
    _QUERY_TIMEOUT,
    PromQLCoordinator,
    _extract_scalar,
)


class _FakeResponse:
    def __init__(self, status: int, payload: dict[str, Any]) -> None:
        self.status = status
        self._payload = payload

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def json(self) -> dict[str, Any]:
        return self._payload


class _FakeSession:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.requests: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.requests.append({"url": url, **kwargs})
        return self._response


class _FakeEntry:
    options: dict[str, Any]

    def __init__(self, options: dict[str, Any]) -> None:
        self.options = options


def _make_coordinator(entry: _FakeEntry) -> PromQLCoordinator:
    coordinator: Any = object.__new__(PromQLCoordinator)
    coordinator.hass = object()
    coordinator.prometheus_url = "http://prometheus:9090"
    coordinator._entry = entry
    return cast(PromQLCoordinator, coordinator)


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


@pytest.mark.asyncio
async def test_update_data_sends_promql_query_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    query = '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
    session = _FakeSession(
        _FakeResponse(
            200,
            {
                "status": "success",
                "data": {"resultType": "scalar", "result": [1715000000.0, "42.5"]},
            },
        )
    )
    monkeypatch.setattr(
        "custom_components.promql.coordinator.async_get_clientsession",
        lambda hass: session,
    )

    coordinator = _make_coordinator(
        _FakeEntry({CONF_QUERIES: [{CONF_QUERY_ID: "cpu", CONF_QUERY: query}]})
    )

    assert await coordinator._async_update_data() == {"cpu": "42.5"}
    assert session.requests == [
        {
            "url": "http://prometheus:9090/api/v1/query",
            "params": {"query": query},
            "timeout": _QUERY_TIMEOUT,
        }
    ]


@pytest.mark.asyncio
async def test_update_data_keeps_query_http_400_per_sensor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession(
        _FakeResponse(
            400,
            {
                "status": "error",
                "errorType": "bad_data",
                "error": "parse error",
            },
        )
    )
    monkeypatch.setattr(
        "custom_components.promql.coordinator.async_get_clientsession",
        lambda hass: session,
    )

    coordinator = _make_coordinator(
        _FakeEntry({CONF_QUERIES: [{CONF_QUERY_ID: "cpu", CONF_QUERY: "not valid"}]})
    )

    assert await coordinator._async_update_data() == {"cpu": None}
