# PromQL Home Assistant Integration: Technical Advisory

This document provides technical guidance on implementing the core patterns required for a high-quality Home Assistant integration, drawing directly from official [Home Assistant Developer Documentation](https://developers.home-assistant.io/docs/development_index/).

## 1. Config Flow (`config_flow.py`)
The `ConfigFlow` is the entry point for users to set up your integration via the UI.

### Architectural Best Practices
*   **Connection Testing:** Always validate credentials and connectivity during the config flow. This ensures immediate feedback, adhering to the [Integration Quality Scale](https://developers.home-assistant.io/docs/integration_quality_scale_index/).
*   **Unique ID:** Assign a `unique_id` to the config entry. This is critical for preventing duplicate setups and enabling entity migrations.
*   **Data vs. Options:** Store only essential connectivity information in `ConfigEntry.data`. Use `OptionsFlow` for non-essential configuration, allowing users to modify queries after setup without re-creating the entry.

## 2. Data Update Coordinator (`coordinator.py`)
The `DataUpdateCoordinator` is the [standardized pattern](https://developers.home-assistant.io/docs/integration_fetching_data/) for efficient data polling.

### Architectural Best Practices
*   **Unified Polling:** Use one coordinator instance per config entry. This ensures you only make one API call to your Prometheus instance, even if multiple sensors are defined, avoiding API "hammering" [Source: HA Fetching Data Docs](https://developers.home-assistant.io/docs/integration_fetching_data/).
*   **Initialization:** Use `async_config_entry_first_refresh` to ensure valid data on startup and `_async_setup` for one-time initialization logic [Source: HA Blog](https://developers.home-assistant.io/blog/2024/08/05/data-update-coordinator-improvements/).
*   **Entity Linking:** Inherit from `CoordinatorEntity`. This provides out-of-the-box integration with the coordinator’s update cycle and sets `should_poll = False` automatically.

## 3. Recommended Resources
For further development, refer to these canonical sources:
*   [Config Flow Documentation](https://developers.home-assistant.io/docs/config_flow_index/)
*   [Fetching Data with Coordinator](https://developers.home-assistant.io/docs/integration_fetching_data/)
*   [Integration Quality Scale](https://developers.home-assistant.io/docs/integration_quality_scale_index/)
