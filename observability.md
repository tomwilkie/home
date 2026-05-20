# Observability

Home Assistant metrics and logs are shipped to Grafana Cloud using [Grafana Alloy](https://grafana.com/docs/alloy/latest/), running as a plain Docker container on the HAOS host.

## Why not a HA addon?

HAOS addons run inside the Supervisor's managed Docker environment, which does not permit mounting the host's `/proc` or `/sys` filesystems into a container. Those mounts are required for node exporter metrics (CPU, memory, disk, network at the host level). This is a known, deliberate restriction — see:

- [community.home-assistant.io — Mount host's /proc & /sys into add-on container](https://community.home-assistant.io/t/mount-hosts-proc-sys-into-add-on-container/848705/3)
- [github.com/orgs/home-assistant — Discussion #3203](https://github.com/orgs/home-assistant/discussions/3203)

As a result, Alloy is deployed as a standalone Docker container managed directly via Docker Compose, outside of the Supervisor.

## Architecture

```
HAOS host
├── Grafana Alloy (Docker, host network)
│   ├── scrapes /proc, /sys          → node metrics
│   ├── scrapes Docker socket        → container metrics (cAdvisor) + container logs
│   ├── reads /var/log/journal       → systemd journal logs
│   ├── scrapes localhost:8123       → Home Assistant metrics
│   └── discovers unpoller addon     → UniFi network metrics
└── ships everything → Grafana Cloud (Prometheus + Loki)
```

Alloy runs with `network_mode: host` so it can reach Home Assistant on `localhost:8123` and resolve addon hostnames that are only reachable from the host network.

## Data collected

### Metrics

| Source | Job label | Notes |
|---|---|---|
| Alloy self | `integrations/alloy` | Health and pipeline metrics |
| Node / system | `integrations/node_exporter` | CPU, memory, disk, network via `/proc` and `/sys` |
| Docker containers | `integrations/docker` | Per-container resource usage via cAdvisor |
| Home Assistant | `integrations/homeassistant` | All HA entity states via `/api/prometheus` |
| Unpoller | `integrations/unpoller` | UniFi device metrics; discovered via Docker SD because addon DNS is unreachable from host network |

### Logs

| Source | Labels |
|---|---|
| Systemd journal (`/var/log/journal`) | `unit`, `level`, `container` |
| Docker container logs | `container`, `stream`, `compose_service` |

## Environment variables

Copy `observability/.env.example` to `observability/.env` and populate:

| Variable | Description |
|---|---|
| `STACK_NAME` | Grafana Cloud stack slug |
| `ACCESS_TOKEN` | `glc_…` token with MetricsPublisher + LogsPublisher roles |
| `HASS_METRICS_TOKEN` | Long-lived HA token for scraping `/api/prometheus` |

## Deployment

All commands are run from the `observability/` directory and target the HAOS host over SSH (`root@homeassistant.local`).

| Target | Action |
|---|---|
| `make deploy` | Push config then start (= `push` + `up`) |
| `make push` | SSH to HAOS, create `/homeassistant/alloy/`, upload `alloy/config.alloy` |
| `make up` | `docker compose up -d` |
| `make down` | `docker compose down` |
| `make restart` | `docker compose restart alloy` |
| `make logs` | Tail last 100 lines of Alloy logs |
| `make ps` | Show container status |
| `make shell` | Interactive bash inside the Alloy container |

### Paths on HAOS

| Purpose | Path |
|---|---|
| Config written by `make push` | `/homeassistant/alloy/config.alloy` |
| Config as seen by Supervisor | `/mnt/data/supervisor/homeassistant/alloy/config.alloy` |
| Alloy persistent state | Docker volume `alloy-data` |

## Grafana Dashboards

Dashboard JSON files live in `observability/dashboards/`. This repo is the **source of truth** — all edits must be made to files here, then uploaded to Grafana.

### Dashboard inventory

| File | UID | Description |
|---|---|---|
| `observability/dashboards/docker-cluster-overview.json` | `docker-cluster-overview` | Cross-host summary — one row per Docker host |
| `observability/dashboards/docker-container-overview.json` | `docker-container-overview` | Per-container drill-down |
| `observability/dashboards/docker-host-overview.json` | `docker-host-overview` | Aggregate resource usage for a single host |

### Fetch (re-download to repo)

```bash
gcx api /api/dashboards/uid/{uid} | jq . > observability/dashboards/{slug}.json
```

Use `jq .` (not `jq -S`) to preserve the original key ordering so future diffs are minimal. The hint line gcx prints goes to stderr and does not affect the JSON on stdout.

### Diff local vs live

```bash
diff <(jq -S . observability/dashboards/{slug}.json) \
     <(gcx api /api/dashboards/uid/{uid} | jq -S .)
```

### Upload (push local → Grafana)

```bash
jq '{dashboard: .dashboard, overwrite: true}' observability/dashboards/{slug}.json \
  | gcx api /api/dashboards/db -d @-
```

The stored format has `dashboard` + `meta` keys; the upload endpoint (`/api/dashboards/db`) only wants `dashboard` + `overwrite`.

### Workflow

1. **Check for remote changes** before editing — diff local vs live (see above)
2. Edit `observability/dashboards/{slug}.json` in this repo
3. Diff to review your outgoing change
4. Upload to Grafana
5. Commit to git
