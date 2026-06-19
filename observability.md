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
│   ├── discovers unpoller addon     → UniFi network metrics
│   └── receives UDM syslog on :514  → UniFi events (raw/UDP, split by log_type)
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

Every log stream is given an explicit **`service_name`** label in Alloy (the bare
name; its `job` is `integrations/<name>`). This overrides Loki's default
`discover_service_name` auto-detection, which otherwise derives `service_name`
from the first matching label and produced surprises: it used the raw `container`
name for Docker (incl. the `addon_<hash>_` prefix) and, worse, the per-event CEF
`name` label for UniFi (`motion`, `Ring`, …) — yielding many noisy `service_name`
values on the UniFi stream. The explicit values are:

| `service_name` | `job` | `instance` | Source |
|---|---|---|---|
| `alloy` | `integrations/alloy` | hostname | Alloy's own logs (`logging{}` block) |
| container name (`addon_<hash>_` stripped) | `integrations/docker` | hostname | Docker container logs |
| `linux` | `integrations/linux` | hostname | Systemd journal |
| `unifi` | `integrations/unifi` | `udm` | UniFi syslog |

| Source | Labels |
|---|---|
| Systemd journal (`/var/log/journal`) | `service_name=linux`, `unit`, `level`, `container` |
| Docker container logs | `service_name` (container name, addon prefix stripped), `container`, `stream`, `compose_service` |
| UniFi syslog (UDP 514) — all kinds share `service_name=unifi`, `job=integrations/unifi`, `instance=udm`, and are split by a `log_type` label (see below) | `log_type` ∈ {`firewall`, `dns`, `cef`, `system`} |
| └ `log_type=firewall` — kernel iptables per-flow logs | + `rule` (firewall policy name) |
| └ `log_type=dns` — CoreDNS query logs (JSON) | — |
| └ `log_type=cef` — CEF activity events (Protect cameras, Network, Access) | + `product`, `name`, `severity` |
| └ `log_type=system` — everything else (UniFi-OS daemons: `mcad`, `earlyoom`, `wevent`, …) | — |

#### UniFi syslog (CEF)

The UDM Pro Max's remote logging (UniFi's "Activity Logging" / SIEM exporter)
does **not** emit RFC-compliant syslog — it sends **CEF** over **UDP**, with no
`<PRI>` prefix and the site name (the home address) in the hostname position:

```
Jun 17 12:42:00 <site name> CEF:0|Ubiquiti|UniFi Protect|7.1.83|2159|motion|3|UNIFIcategory=detection ... msg="..."
```

Because the strict RFC3164/RFC5424 parsers reject this, Alloy's
`loki.source.syslog "unifi"` listens in **`syslog_format = "raw"`** mode (passes
each datagram through unparsed). `raw` is an **experimental** Alloy feature, so
the container is started with `--stability.level=experimental` (see
`docker-compose.yml`). The listener binds `0.0.0.0:514`; with
`network_mode: host` (and root) it's reachable on the LAN at the Home Assistant
host IP `192.168.0.12` (the DHCP-reserved address — see
[@network-security.md](network-security.md)).

The full raw line is forwarded as the log body. A single UDP/514 stream actually
multiplexes **four unrelated kinds of line** (firewall flow logs, CoreDNS
queries, CEF activity events, and UniFi-OS daemon noise), so `loki.process
"unifi"` classifies each line by content into a low-cardinality **`log_type`**
label — `firewall`, `dns`, `cef`, or `system` (the default) — putting each kind
in its own Loki stream. Without this, sporadic camera events are buried under the
firehose of firewall flow logs. Per-`log_type` extra labels:

| `log_type` | Matches lines containing | Extra labels |
|---|---|---|
| `firewall` | `[CUSTOM` (iptables policy log prefix) | `rule` — the policy name (DESCR) |
| `dns` | `coredns[` | — |
| `cef` | `CEF:` | `product`, `name`, `severity` (CEF header) |
| `system` | _(default — anything unmatched)_ | — |

High-cardinality fields (SRC/DST IPs, ports, DNS domains) stay in the log **body**
and are queried with `|=`/`|~`; only bounded fields become labels. The
classification is done with `stage.match` blocks whose `selector` uses a `|=`
line filter, each overriding the default `log_type=system` static label.

> The syslog "hostname" field is the UniFi site name (the home address); it is
> intentionally **not** stripped — these logs go to a private Grafana Cloud
> stack. If that ever changes, add a `stage.regex` keeping only `CEF:…` plus a
> `stage.output`.

Configure the UDM side in the **UniFi UI** (not the MCP — the site-settings
payload echoes the home address, which is PII per [CLAUDE.md](CLAUDE.md)): enable
Activity Logging / Remote Logging, **Server Address** = `192.168.0.12`, **Port**
= `514` (UDP), select the desired categories. No firewall rule is needed —
gateway→Internal traffic on the Default network is allowed by the ZBF predefined
matrix. Query in Grafana Cloud with `{job="integrations/unifi"}`.

#### UniFi firewall traffic & DNS logs (`log_type=firewall` / `dns`)

When the UDM's Remote Logging **firewall** category is enabled, the same UDP/514
stream *also* carries non-CEF lines, which Alloy passes through verbatim (raw
mode) and tags with `log_type` (above). Query by label rather than line content.

- **Kernel firewall (iptables) per-flow logs** (`log_type=firewall`) — emitted by
  any firewall policy with `logging: true` (e.g. `Log IOT to Internet (ALLOW)`,
  see [@network-security.md](network-security.md)); the policy name is the `rule`
  label:
  ```
  Jun 19 10:14:06 <host> [CUSTOM1_WAN-A-10003] DESCR="Log IOT to Internet (ALLOW)"
  IN=br2 OUT=eth8 SRC=192.168.2.67 DST=34.159.33.52 PROTO=TCP SPT=... DPT=443 ...
  ```
  This is the only reliable source of **per-device internet destinations** (as
  IPs) — Insights → Flows only retains *blocked* flows. Query:
  `{log_type="firewall", rule="Log IOT to Internet (ALLOW)"}`, then `|= "SRC=192.168.2"`
  to narrow to a device.

- **CoreDNS query logs** (`log_type=dns`) — JSON, but only ad-blocked queries
  (`"type":"dnsAdBlock"`), not full resolution:
  ```
  coredns[…]: {"type":"dnsAdBlock","category":"ADVERTISEMENT","domain":"…","src_ip":"…", …}
  ```
  Query: `{log_type="dns"}`.

> **Verifying syslog ingestion** (to tell "UDM isn't sending" from "Alloy is
> dropping"): tcpdump on the host sees packets *before* Alloy
> (`tcpdump -ni any udp port 514 -A`); Alloy's own metrics confirm
> ingestion/drops (`curl -s localhost:12345/metrics | grep -E
> 'loki_source_syslog_entries_total|loki_write_(dropped|sent)_entries_total'`).
> Firewall traffic logs are high-volume; CEF activity events are sporadic (a few
> per minute), so a short quiet capture window is normal for CEF alone.

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
