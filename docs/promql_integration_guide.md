# PromQL Home Assistant Integration Guide

This guide outlines the architectural path to creating a Home Assistant integration that supports UI-based PromQL query definition and is distributable via HACS.

## 1. Project Structure
Your GitHub repository must follow the standard Home Assistant custom component layout:

```text
custom_components/
  promql_integration/
    __init__.py          # Integration setup
    manifest.json        # Metadata
    sensor.py            # PromQL sensor implementation
    config_flow.py       # UI configuration flow
    coordinator.py       # Data polling and API logic
hacs.json                # HACS metadata
README.md                # Documentation
```

## 2. Key Components

### `manifest.json`
Required for Home Assistant to recognize the integration.
```json
{
  "domain": "promql_integration",
  "name": "PromQL Integration",
  "version": "1.0.0",
  "documentation": "https://github.com/yourusername/promql_integration",
  "issue_tracker": "https://github.com/yourusername/promql_integration/issues",
  "codeowners": ["@yourusername"],
  "requirements": ["requests==2.31.0"]
}
```

### `hacs.json`
Required for HACS distribution.
```json
{
  "name": "PromQL Integration",
  "render_readme": true,
  "category": "integration"
}
```

## 3. Implementation Strategy
*   **Configuration Flow (`config_flow.py`):** Use this to allow users to input their Prometheus URL and authentication credentials directly in the Home Assistant UI.
*   **Data Coordinator (`DataUpdateCoordinator`):** Centralize your PromQL API calls here. This ensures efficiency if multiple sensors are defined.
*   **Sensors (`sensor.py`):** Create dynamic sensors based on the queries defined by the user in the configuration flow.

## 4. Development Workflow
1.  **Use the Blueprint:** Fork the [Integration Blueprint](https://github.com/ludeeus/integration_blueprint) to get a pre-configured development environment with VS Code Dev Containers.
2.  **Iterative Testing:** Use the Dev Container to run a local Home Assistant instance to test your UI flow and PromQL result processing.
3.  **Versioning:** Create GitHub Releases (e.g., `v1.0.0`) to trigger HACS indexing.
