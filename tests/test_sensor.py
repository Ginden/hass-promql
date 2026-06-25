"""Tests for PromQL sensor entity configuration."""

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import CONF_NAME

from custom_components.promql.const import (
    CONF_DEVICE_CLASS,
    CONF_QUERIES,
    CONF_QUERY,
    CONF_QUERY_ID,
    CONF_STATE_CLASS,
    CONF_UNIT,
    DEFAULT_STATE_CLASS,
    STATE_CLASS_NONE,
)
from custom_components.promql.sensor import (
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
    assert (
        _state_class_from_config("measurement")
        is SensorStateClass.MEASUREMENT
    )
    assert _state_class_from_config("total_increasing") is (
        SensorStateClass.TOTAL_INCREASING
    )
    assert _state_class_from_config(STATE_CLASS_NONE) is None
    assert _state_class_from_config("not_a_state_class") is None


def test_icon_for_config_lets_device_class_provide_default_icon() -> None:
    assert _icon_for_config(SensorDeviceClass.DATA_SIZE) is None
    assert _icon_for_config(None) == "mdi:chart-line"
