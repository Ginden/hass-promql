# PromQL Integration for Home Assistant

A Home Assistant custom component that lets you define [PromQL](https://prometheus.io/docs/prometheus/latest/querying/basics/) queries in the UI and expose results as sensors.

## Features

- Configure Prometheus connections via the Home Assistant UI
- Add any number of PromQL sensors per Prometheus instance
- Sensors update every 30 seconds
- Installable via [HACS](https://hacs.xyz)

## Requirements

- Home Assistant 2024.11 or later (config subentries support)

## Installation

### HACS (recommended)

1. Add `https://github.com/Ginden/hass-promql` to HACS as a custom repository
2. Install **PromQL** from the integrations list
3. Restart Home Assistant

### Manual

Copy `custom_components/promql/` into your Home Assistant `custom_components/` directory and restart.

## Setup

1. Go to **Settings → Devices & Services → Add Integration** and search for **PromQL**
2. Enter the base URL of your Prometheus server (e.g. `http://prometheus:9090`)
3. Add sensors by clicking **Add entry** on the integration card — each sensor takes a name, a PromQL expression, and an optional unit of measurement

## Query requirements

Queries must return a **scalar** or a **single-element instant vector**. Multi-series results are not supported and will produce an unavailable sensor.

Examples:

```promql
# Current memory usage in bytes
node_memory_MemAvailable_bytes{job="node"}

# Scalar arithmetic
100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
```

## Local development

```bash
docker compose up --build
```

Starts Home Assistant, Prometheus, and node-exporter. On first run the init
container seeds `dev/ha-config/` from the committed template in `dev/ha-seed/`.

| Service       | URL                    |
|---------------|------------------------|
| Home Assistant | http://localhost:8123  |
| Prometheus    | http://localhost:9090  |

**Credentials:** `dev` / `dev`

**First sensor to add:** go to Settings → Devices & Services → PromQL →
Add entry. Use `http://prometheus:9090` as the Prometheus URL (Docker
internal hostname). Example queries are in `dev/example-queries.txt`.

To reset HA state: `rm -rf dev/ha-config && mkdir dev/ha-config`

For a standalone self-contained image (no Prometheus bundled):
```bash
docker run -p 8123:8123 $(docker build -q .)
```

## Notes

- `aiohttp` is bundled with Home Assistant — no additional Python dependencies are installed
- HACS distribution requires a public GitHub repository
