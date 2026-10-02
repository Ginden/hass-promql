"""Tests for PromQL query handling and polling."""

import asyncio
import json
from collections import Counter
from typing import Any, cast

import aiohttp
import pytest
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.promql.const import (
    AUTH_TYPE_BASIC,
    AUTH_TYPE_BEARER,
    AUTH_TYPE_NONE,
    CONF_AUTH_TYPE,
    CONF_PROMETHEUS_URL,
    CONF_QUERIES,
    CONF_QUERY,
    CONF_QUERY_ID,
    CONF_TOKEN,
    DOMAIN,
)
from custom_components.promql.coordinator import (
    _MAX_CONCURRENT_QUERIES,
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
    def __init__(self, response: _FakeResponse | dict[str, _FakeResponse]) -> None:
        self._response = response
        self.requests: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.requests.append({"url": url, **kwargs})
        if isinstance(self._response, dict):
            return self._response[kwargs["params"]["query"]]
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
    coordinator._listeners = {}
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
    kwargs = _request_auth_kwargs({CONF_AUTH_TYPE: AUTH_TYPE_BEARER, CONF_TOKEN: "abc"})
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


def _scalar_response(value: str) -> _FakeResponse:
    return _FakeResponse(
        200,
        {"status": "success", "data": {"resultType": "scalar", "result": [0, value]}},
    )


async def test_duplicate_expressions_share_a_request_but_are_refreshed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = {"up": _scalar_response("1"), "sum(up)": _scalar_response("2")}
    session = _FakeSession(responses)
    monkeypatch.setattr(
        "custom_components.promql.coordinator.async_get_clientsession",
        lambda hass: session,
    )
    coordinator = _make_coordinator(
        _FakeEntry(
            {
                CONF_QUERIES: [
                    {CONF_QUERY_ID: "first", CONF_QUERY: "up"},
                    {CONF_QUERY_ID: "duplicate", CONF_QUERY: "up"},
                    {CONF_QUERY_ID: "total", CONF_QUERY: "sum(up)"},
                ]
            }
        )
    )

    assert await coordinator._async_update_data() == {
        "first": "1",
        "duplicate": "1",
        "total": "2",
    }
    assert Counter(r["params"]["query"] for r in session.requests) == {
        "up": 1,
        "sum(up)": 1,
    }
    responses["up"] = _scalar_response("0")
    assert await coordinator._async_update_data() == {
        "first": "0",
        "duplicate": "0",
        "total": "2",
    }
    assert Counter(r["params"]["query"] for r in session.requests) == {
        "up": 2,
        "sum(up)": 2,
    }


async def test_polling_limits_concurrent_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch_started = asyncio.Event()
    release_batch = asyncio.Event()
    started = 0

    class BlockingResponse(_FakeResponse):
        async def __aenter__(self) -> _FakeResponse:
            nonlocal started
            started += 1
            if started == _MAX_CONCURRENT_QUERIES:
                batch_started.set()
            await release_batch.wait()
            return self

    response = _scalar_response("1")
    session = _FakeSession(BlockingResponse(response.status, response._payload))
    monkeypatch.setattr(
        "custom_components.promql.coordinator.async_get_clientsession",
        lambda hass: session,
    )
    queries = [
        {CONF_QUERY_ID: str(i), CONF_QUERY: str(i)}
        for i in range(_MAX_CONCURRENT_QUERIES * 2)
    ]
    coordinator = _make_coordinator(_FakeEntry({CONF_QUERIES: queries}))
    task = asyncio.create_task(coordinator._async_update_data())
    try:
        await asyncio.wait_for(batch_started.wait(), timeout=1)
        assert len(session.requests) == _MAX_CONCURRENT_QUERIES
    finally:
        release_batch.set()
        result = await task
    assert result == {query[CONF_QUERY_ID]: "1" for query in queries}


async def test_refresh_skips_inactive_sensors_and_unchanged_notifications(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = {"up": _scalar_response("1"), "sum(up)": _scalar_response("2")}
    session = _FakeSession(responses)
    monkeypatch.setattr(
        "custom_components.promql.coordinator.async_get_clientsession",
        lambda hass: session,
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PROMETHEUS_URL: "http://prometheus:9090"},
        options={
            CONF_QUERIES: [
                {CONF_QUERY_ID: "active", CONF_QUERY: "up"},
                {CONF_QUERY_ID: "disabled", CONF_QUERY: "sum(up)"},
            ]
        },
    )
    coordinator = PromQLCoordinator(hass, entry)
    await coordinator.async_refresh()
    assert coordinator.data == {"active": "1", "disabled": "2"}

    notifications = []
    unsubscribe = coordinator.async_add_listener(
        lambda: notifications.append(coordinator.data.copy()), context="active"
    )
    try:
        session.requests.clear()
        await coordinator.async_refresh()
        assert [r["params"]["query"] for r in session.requests] == ["up"]
        await coordinator.async_refresh()
        assert notifications == [{"active": "1"}]
        responses["up"] = _scalar_response("0")
        await coordinator.async_refresh()
        assert notifications == [{"active": "1"}, {"active": "0"}]
    finally:
        unsubscribe()
        await coordinator.async_shutdown()


@pytest.mark.parametrize("raw", ["NaN", "+Inf", "-Inf"])
async def test_query_non_finite_values_are_json_safe(
    raw: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession(_scalar_response(raw))
    monkeypatch.setattr(
        "custom_components.promql.coordinator.async_get_clientsession",
        lambda hass: session,
    )
    result = await _make_coordinator(_FakeEntry({})).async_query("1 / 0")
    assert result["value"] is None
    assert result["raw_value"] == raw
    json.dumps(result, allow_nan=False)


async def test_invalid_json_only_affects_its_sensor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InvalidJSONResponse(_FakeResponse):
        async def json(self) -> dict[str, Any]:
            raise json.JSONDecodeError("Expecting value", "invalid", 0)

    session = _FakeSession(
        {
            "up": _scalar_response("1"),
            "broken": InvalidJSONResponse(200, {}),
        }
    )
    monkeypatch.setattr(
        "custom_components.promql.coordinator.async_get_clientsession",
        lambda hass: session,
    )
    coordinator = _make_coordinator(
        _FakeEntry(
            {
                CONF_QUERIES: [
                    {CONF_QUERY_ID: "healthy", CONF_QUERY: "up"},
                    {CONF_QUERY_ID: "broken", CONF_QUERY: "broken"},
                ]
            }
        )
    )
    assert await coordinator._async_update_data() == {"healthy": "1", "broken": None}
