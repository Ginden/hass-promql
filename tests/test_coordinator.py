"""Smoke tests for PromQL coordinator helpers."""

from typing import Any, cast

import aiohttp
import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from custom_components.promql.const import (
    AUTH_TYPE_BASIC,
    AUTH_TYPE_BEARER,
    AUTH_TYPE_NONE,
    CONF_AUTH_TYPE,
    CONF_QUERIES,
    CONF_QUERY,
    CONF_QUERY_ID,
    CONF_TOKEN,
)
from custom_components.promql.coordinator import (
    _QUERY_TIMEOUT,
    PromQLCoordinator,
    _extract_scalar,
    _request_auth_kwargs,
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


def _make_coordinator(
    entry: _FakeEntry, auth_kwargs: dict[str, Any] | None = None
) -> PromQLCoordinator:
    coordinator: Any = object.__new__(PromQLCoordinator)
    coordinator.hass = object()
    coordinator.prometheus_url = "http://prometheus:9090"
    coordinator.config_entry = entry
    coordinator._auth_kwargs = auth_kwargs or {}
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
async def test_update_data_sends_basic_auth_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession(
        _FakeResponse(
            200,
            {
                "status": "success",
                "data": {"resultType": "scalar", "result": [1715000000.0, "1"]},
            },
        )
    )
    monkeypatch.setattr(
        "custom_components.promql.coordinator.async_get_clientsession",
        lambda hass: session,
    )

    auth = aiohttp.BasicAuth("alice", "s3cret")
    coordinator = _make_coordinator(
        _FakeEntry({CONF_QUERIES: [{CONF_QUERY_ID: "ping", CONF_QUERY: "1"}]}),
        auth_kwargs={"auth": auth},
    )

    assert await coordinator._async_update_data() == {"ping": "1"}
    assert session.requests[0]["auth"] is auth


@pytest.mark.asyncio
async def test_update_data_sends_bearer_token_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession(
        _FakeResponse(
            200,
            {
                "status": "success",
                "data": {"resultType": "scalar", "result": [1715000000.0, "1"]},
            },
        )
    )
    monkeypatch.setattr(
        "custom_components.promql.coordinator.async_get_clientsession",
        lambda hass: session,
    )

    coordinator = _make_coordinator(
        _FakeEntry({CONF_QUERIES: [{CONF_QUERY_ID: "ping", CONF_QUERY: "1"}]}),
        auth_kwargs={"headers": {"Authorization": "Bearer my-token"}},
    )

    assert await coordinator._async_update_data() == {"ping": "1"}
    assert session.requests[0]["headers"] == {"Authorization": "Bearer my-token"}


def test_request_auth_kwargs_none() -> None:
    assert _request_auth_kwargs({CONF_AUTH_TYPE: AUTH_TYPE_NONE}) == {}
    assert _request_auth_kwargs({}) == {}


def test_request_auth_kwargs_basic() -> None:
    kwargs = _request_auth_kwargs(
        {
            CONF_AUTH_TYPE: AUTH_TYPE_BASIC,
            CONF_USERNAME: "alice",
            CONF_PASSWORD: "s3cret",
        }
    )
    auth = kwargs.get("auth")
    assert isinstance(auth, aiohttp.BasicAuth)
    assert auth.login == "alice"
    assert auth.password == "s3cret"


def test_request_auth_kwargs_bearer() -> None:
    kwargs = _request_auth_kwargs(
        {CONF_AUTH_TYPE: AUTH_TYPE_BEARER, CONF_TOKEN: "abc"}
    )
    assert kwargs == {"headers": {"Authorization": "Bearer abc"}}


@pytest.mark.asyncio
async def test_async_query_returns_scalar_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    coordinator = _make_coordinator(_FakeEntry({}))
    result = await coordinator.async_query("1")

    assert result == {
        "status": "success",
        "value": 42.5,
        "raw_value": "42.5",
        "error": None,
    }


@pytest.mark.asyncio
async def test_async_query_returns_error_on_prometheus_error(
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

    coordinator = _make_coordinator(_FakeEntry({}))
    result = await coordinator.async_query("not valid")

    assert result["status"] == "error"
    assert result["value"] is None
    assert result["raw_value"] is None
    assert result["error"] == "parse error"


@pytest.mark.asyncio
async def test_async_query_returns_success_with_value_none_for_multi_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession(
        _FakeResponse(
            200,
            {
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {"metric": {"job": "a"}, "value": [0, "1"]},
                        {"metric": {"job": "b"}, "value": [0, "2"]},
                    ],
                },
            },
        )
    )
    monkeypatch.setattr(
        "custom_components.promql.coordinator.async_get_clientsession",
        lambda hass: session,
    )

    coordinator = _make_coordinator(_FakeEntry({}))
    result = await coordinator.async_query("up")

    assert result == {
        "status": "success",
        "value": None,
        "raw_value": None,
        "error": None,
    }


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
