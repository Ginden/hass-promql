"""Tests for PromQL sensor entity configuration."""

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import CONF_NAME, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.promql.const import (
    CONF_DEVICE_CLASS,
    CONF_PROMETHEUS_URL,
    CONF_QUERIES,
    CONF_QUERY,
    CONF_QUERY_ID,
    CONF_STATE_CLASS,
    CONF_UNIT,
    DEFAULT_STATE_CLASS,
    DOMAIN,
    STATE_CLASS_NONE,
)
from custom_components.promql.coordinator import PromQLCoordinator
from custom_components.promql.sensor import (
    PromQLSensor,
    _device_class_from_config,
    _icon_for_config,
    _query_configs,
    _state_class_from_config,
)


def test_query_configs_preserves_configured_device_class() -> None:
    options = {
        CONF_QUERIES: [
            {
                CONF_QUERY_ID: "gpu_memory",
                CONF_NAME: "GPU Memory",
                CONF_QUERY: "node_memory_MemAvailable_bytes",
                CONF_UNIT: "MiB",
                CONF_DEVICE_CLASS: "data_size",
                CONF_STATE_CLASS: DEFAULT_STATE_CLASS,
            }
        ]
    }

    assert _query_configs(options) == [
        {
            CONF_QUERY_ID: "gpu_memory",
            CONF_NAME: "GPU Memory",
            CONF_QUERY: "node_memory_MemAvailable_bytes",
            CONF_UNIT: "MiB",
            CONF_DEVICE_CLASS: "data_size",
            CONF_STATE_CLASS: DEFAULT_STATE_CLASS,
        }
    ]


def test_query_configs_does_not_infer_device_class_from_unit() -> None:
    options = {
        CONF_QUERIES: [
            {
                CONF_QUERY_ID: "gpu_memory",
                CONF_NAME: "GPU Memory",
                CONF_QUERY: "node_memory_MemAvailable_bytes",
                CONF_UNIT: "MiB",
            }
        ]
    }

    assert _query_configs(options)[0][CONF_DEVICE_CLASS] == ""


def test_device_class_from_config_validates_stored_value() -> None:
    assert _device_class_from_config("data_size") is SensorDeviceClass.DATA_SIZE
    assert _device_class_from_config("") is None
    assert _device_class_from_config("not_a_device_class") is None


def test_query_configs_preserves_configured_state_class() -> None:
    options = {
        CONF_QUERIES: [
            {
                CONF_QUERY_ID: "requests",
                CONF_NAME: "Requests",
                CONF_QUERY: "http_requests_total",
                CONF_STATE_CLASS: "total_increasing",
            }
        ]
    }

    assert _query_configs(options)[0][CONF_STATE_CLASS] == "total_increasing"


def test_query_configs_defaults_state_class_to_measurement() -> None:
    options = {
        CONF_QUERIES: [
            {
                CONF_QUERY_ID: "running_pods",
                CONF_NAME: "Running pods",
                CONF_QUERY: "sum(kubelet_running_pods)",
            }
        ]
    }

    assert _query_configs(options)[0][CONF_STATE_CLASS] == DEFAULT_STATE_CLASS


def test_state_class_from_config_validates_stored_value() -> None:
    assert _state_class_from_config("measurement") is SensorStateClass.MEASUREMENT
    assert _state_class_from_config("total_increasing") is (
        SensorStateClass.TOTAL_INCREASING
    )
    assert _state_class_from_config(STATE_CLASS_NONE) is None
    assert _state_class_from_config("not_a_state_class") is None


def test_icon_for_config_lets_device_class_provide_default_icon() -> None:
    assert _icon_for_config(SensorDeviceClass.DATA_SIZE) is None
    assert _icon_for_config(None) == "mdi:chart-line"


@pytest.mark.parametrize("raw", [None, "NaN", "+Inf", "-Inf", "invalid"])
async def test_sensor_recovers_from_unusable_values(
    hass: HomeAssistant,
    raw: str | None,
) -> None:
    coordinator = PromQLCoordinator(
        hass,
        MockConfigEntry(
            domain=DOMAIN,
            data={CONF_PROMETHEUS_URL: "http://prometheus:9090"},
        ),
    )
    sensor = PromQLSensor(
        coordinator,
        {
            CONF_QUERY_ID: "cpu",
            CONF_NAME: "CPU",
            CONF_QUERY: "cpu_usage",
        },
    )
    healthy = PromQLSensor(
        coordinator,
        {
            CONF_QUERY_ID: "healthy",
            CONF_NAME: "Healthy",
            CONF_QUERY: "up",
        },
    )
    assert sensor.available is False
    coordinator.async_set_updated_data({"cpu": raw, "healthy": "1"})
    assert sensor.native_value is None
    assert sensor.available is False
    assert healthy.available is True
    assert healthy.native_value == 1
    coordinator.async_set_updated_data({"cpu": "0", "healthy": "1"})
    assert sensor.native_value == 0
    assert sensor.available is True
    await coordinator.async_shutdown()


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_query_failure_and_recovery_reach_home_assistant_states(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    url = "http://prometheus:9090"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PROMETHEUS_URL: url},
        options={
            CONF_QUERIES: [
                {CONF_QUERY_ID: "cpu", CONF_NAME: "CPU", CONF_QUERY: "cpu_usage"},
                {CONF_QUERY_ID: "healthy", CONF_NAME: "Healthy", CONF_QUERY: "up"},
            ]
        },
    )
    entry.add_to_hass(hass)

    def respond(cpu_value: str | None) -> None:
        aioclient_mock.clear_requests()
        aioclient_mock.get(
            f"{url}/api/v1/query",
            params={"query": "up"},
            json={
                "status": "success",
                "data": {
                    "resultType": "scalar",
                    "result": [0, "1"],
                },
            },
        )
        aioclient_mock.get(
            f"{url}/api/v1/query",
            params={"query": "cpu_usage"},
            status=200 if cpu_value is not None else 400,
            json={
                "status": "success",
                "data": {
                    "resultType": "scalar",
                    "result": [0, cpu_value],
                },
            }
            if cpu_value is not None
            else {"status": "error", "error": "parse error"},
        )

    respond("42.5")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    cpu_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_cpu")
    healthy_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_healthy"
    )
    assert hass.states.get(cpu_id).state == "42.5"
    assert hass.states.get(healthy_id).state == "1.0"

    respond(None)
    await entry.runtime_data.async_refresh()
    assert hass.states.get(cpu_id).state == STATE_UNAVAILABLE
    assert hass.states.get(healthy_id).state == "1.0"

    respond("0")
    await entry.runtime_data.async_refresh()
    assert hass.states.get(cpu_id).state == "0.0"
    assert hass.states.get(healthy_id).state == "1.0"
