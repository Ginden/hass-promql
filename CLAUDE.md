# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dev dependencies
uv sync --group dev

# Run all tests
uv run pytest tests/ -v

# Run a single test file
uv run pytest tests/test_coordinator.py -v

# Lint
uv run ruff check custom_components/ tests/

# Type-check
uv run mypy custom_components/promql/
```

## Local dev environment

```bash
docker compose up --build          # start HA + Prometheus + node-exporter
rm -rf dev/ha-config && mkdir dev/ha-config  # reset HA state (re-seeded on next up)
```

- HA at http://localhost:8123 — credentials `dev` / `dev` (seeded from `dev/ha-seed/`)
- Prometheus at http://localhost:9090 — internal hostname `prometheus`
- `dev/ha-config/` is a git-ignored bind mount (contents ignored via `dev/ha-config/*` + `.gitkeep`); `dev/ha-seed/` is the committed seed template
- The `init` service copies the seed on first run only (idempotent)
- Example PromQL queries in `dev/example-queries.txt`

## Architecture

This is a Home Assistant custom integration that turns PromQL expressions into HA sensor entities.

**Two-level config entry model (HA 2024.11+ subentries):**
- A **config entry** represents one Prometheus instance (URL). `integration_type = "hub"`.
- A **config subentry** (type `"sensor"`) represents one PromQL query → one sensor entity.
- Users add queries via the "Add entry" button in the HA UI, which runs `PromQLSensorSubentryFlow`.
- When a subentry is created, HA reloads the parent entry, triggering a fresh `async_setup_entry` that picks up the new subentry.

**Data flow:**
1. `async_setup_entry` (`__init__.py`) creates a `PromQLCoordinator` and stores it in `entry.runtime_data`.
2. `PromQLCoordinator._async_update_data` iterates `self.config_entry.subentries` and fires one `GET /api/v1/query` per subentry against Prometheus.
3. Results are stored as `dict[subentry_id, str | None]` in `coordinator.data`.
4. Each `PromQLSensor` (a `CoordinatorEntity`) reads `coordinator.data[self._subentry.subentry_id]` and casts the string to `float` when possible.

**HA conventions used:**
- `entry.runtime_data` (not `hass.data`) for coordinator storage.
- `async_get_clientsession(hass)` (not a bare `aiohttp.ClientSession`) — reuses HA's shared session.
- `DataUpdateCoordinator(config_entry=entry)` — sets `self.config_entry` automatically; do not add a separate `self._entry`.
- `_attr_has_entity_name = True` with `DeviceInfo` grouping all sensors under a per-instance Prometheus device.

**No Python dependencies are declared** in `manifest.json` because `aiohttp` is bundled with HA core.

## Key constraints

- Queries must return a **scalar** or **single-element instant vector**; multi-series results yield `None`.
- Requires HA ≥ 2024.11 for `ConfigSubentryFlow` and `config_entry.subentries`.
- HACS distribution requires a **public GitHub repo** (`github.com/Ginden/hass-promql`). The current working repo is on private GitLab.
