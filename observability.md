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
│   ├── scrapes localhost:9142       → zigbee2mqtt metrics
│   ├── discovers unpoller addon     → UniFi network metrics
│   ├── receives UDM syslog on :514  → UniFi events (raw/UDP, split by log_type)
│   └── tails AdGuard querylog.json  → IOT DNS query log (per-domain, permanent)
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
| zigbee2mqtt | `integrations/zigbee2mqtt` | Zigbee metrics (link quality, message/join counters, adapter queue/retry) from the dev/edge z2m exporter on `localhost:9142`; Alloy reaches it via host networking |
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
| `adguard` | `integrations/adguard` | hostname | AdGuard Home query log (file tail) |

> Note: the AdGuard add-on's **container stdout** is also collected by the Docker
> pipeline and (addon prefix stripped) lands as `service_name=adguard`,
> `job=integrations/docker` — that's AdGuard's operational log (dnsproxy errors,
> etc.), **not** the query log. The per-domain query log is the file-tail stream
> `job=integrations/adguard`. Select on `job`, not `service_name`, to tell them
> apart.

| Source | Labels |
|---|---|
| Systemd journal (`/var/log/journal`) | `service_name=linux`, `unit`, `level`, `container` |
| Docker container logs | `service_name` (container name, addon prefix stripped), `container`, `stream`, `compose_service` |
| AdGuard Home query log (`querylog.json`, file tail) | `service_name=adguard`, `job=integrations/adguard`, `instance=<hostname>` |
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

#### AdGuard Home query log (`job=integrations/adguard`)

AdGuard Home (the IOT DNS resolver, HA add-on `a0d7b954_adguard` — see
[@network-security.md](network-security.md)) is the authoritative source of
per-domain IOT DNS visibility, but its own query log is **rotation- and
retention-capped** (`interval: 90d`), so it is not durable. To keep a permanent
history we tail its on-disk query log into Loki via the existing Alloy container.

AdGuard has **no native log export**, so Alloy reads the file directly:

- The add-on's data directory is bind-mounted **read-only** into Alloy at
  `/adguard` (host path
  `/mnt/data/supervisor/apps/data/a0d7b954_adguard/adguard/data` — see
  `docker-compose.yml`). The *directory* is mounted, not the file, so the tail
  survives rotation (which recreates `querylog.json` with a new inode).
- `local.file_match` + `loki.source.file` tail **only** `querylog.json` (not the
  rotated `querylog.json.1`, to avoid re-ingesting a whole file on rotation).
- Each line is one JSON object; the full line is the log body. A `loki.process`
  `stage.json` + `stage.timestamp` sets the Loki timestamp from AdGuard's own `T`
  field (RFC3339Nano), so a catch-up after Alloy downtime keeps real query times.

```
{"T":"…","QH":"connect.prusa3d.com","QT":"AAAA","IP":"192.168.2.67",
 "Upstream":"https://dns10.quad9.net:443/dns-query","Result":{},"Cached":true,…}
```

Query in Grafana Cloud — high-cardinality fields (domain `QH`, client `IP`) stay
in the body, parsed at query time:

```
{job="integrations/adguard"} | json                          # all IOT DNS queries
{job="integrations/adguard"} | json | IP="192.168.2.67"      # one device's domains
```

> **Near-real-time delivery via `size_memory: 0`.** AdGuard normally buffers the
> most recent `size_memory` queries in RAM and flushes to `querylog.json` only
> when that buffer fills (count-based, **no timer**) — at the default `1000` that
> meant the file (and therefore Loki) updated in roughly hourly batches. We set
> **`size_memory: 0`** in `AdGuardHome.yaml`, which AdGuard internally treats as a
> buffer of **1** (it does *not* fall back to the 1000 default), so it flushes
> **after every query** → Alloy ships each line within seconds. Tradeoff: a small
> file append per DNS query (~24–36k/day) — negligible on SSD, a minor
> write-amplification note on eMMC/SD.
>
> `size_memory` is **not exposed in the AdGuard UI/API**, so changing it means
> editing `AdGuardHome.yaml` and restarting the add-on. AdGuard owns and rewrites
> that file, so **stop** the add-on first, edit, then **start** (editing while it
> runs risks being overwritten on shutdown):
> ```sh
> # via the HA add-on lifecycle (slug a0d7b954_adguard): stop → edit → start
> # host path: /mnt/data/supervisor/apps/data/a0d7b954_adguard/adguard/AdGuardHome.yaml
> ```
>
> Only devices that use AdGuard appear here; hardcoded-DNS/DoH IOT devices are
> visible only as destination IPs in `{log_type="firewall"}` (above).

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
| `observability/dashboards/zigbee2mqtt-overview.json` | `zigbee2mqtt-overview` | zigbee2mqtt device fleet: a Fleet Summary stat row (device/router/end-device counts, an Unavailable count, MQTT & device message rates, errors, retries) and a per-device table with a colour-coded Last seen cell (availability merged into last-seen age), an LQI gauge, and Received/Sent/Errors `irate` sparklines (links to the device dashboard) |
| `observability/dashboards/zigbee2mqtt-coordinator.json` | `zigbee2mqtt-coordinator` | Instance-wide coordinator/adapter health: z2m version, Network status (MQTT connected + permit-join), Coordinator/network metadata (channel/PAN/firmware), and the adapter/protocol diagnostics (MQTT throughput, send-duration & queue-duration quantiles, queue length & retries, top ZCL clusters) |
| `observability/dashboards/zigbee2mqtt-device.json` | `zigbee2mqtt-device` | Per-device drill-down (`device` = ieee_address): metadata (type/vendor/model/power), availability + last-seen, LQI now/over-time, messages received/sent/errors, lifecycle events, request queue |
| `observability/dashboards/home-temperature-by-area.json` | `home-temperature-by-area` | Temperature trends with one **collapsible row per area** (repeating row driven by a custom `area` variable), each holding a time-series of that area's temperature entities |

> **`home-temperature-by-area` — deriving area without an `area` label.** The HA
> Prometheus exporter emits **no `area` label** (series carry only `entity`,
> `friendly_name`, `domain`), so the per-area grouping is built from the
> **area-first `entity` ID prefix** (per [naming-conventions.md](naming-conventions.md)).
> A custom template variable `area` lists `Display : <slug-regex>` pairs and a
> single **repeating, collapsed** `row` (`repeat: "area"`) clones one graph per
> area, querying `homeassistant_sensor_temperature_celsius{entity=~"sensor\.${area}_.*"}`
> plus `homeassistant_climate_current_temperature_celsius{entity=~"climate\.${area}_.*"}`.
> Notes: the `area` **value is a regex fragment** — Hallway is `(hallway|front_door)`
> to fold the front-door sensor device-temps into the Hallway row; full slugs avoid
> the `master_bedroom`/`master_bathroom` prefix collision.
> A soft grey **min–max band** is shaded behind the lines via two extra aggregation
> queries (`min(...)`/`max(...)`, legend `Min`/`Max`) and a `Max` field override
> `custom.fillBelowTo: "Min"` (band series hidden from the legend). The band is
> **ambient-only** — its selectors exclude non-room temps with
> `entity!~".*(radiator|aircon_outside|device_temperature|internal_temperature|battery|door_temperature|boiler_monitor|leak_sensor|towel_heater|thermostat_target).*"`
> — so it reflects room warmth, while the individual lines still show every entity.
> **Rooms only** — Server
> Rack and the whole-house sensor are excluded, which also keeps the PII entity
> `sensor.server_rack_…_cpu_temperature` (contains the street address) out of the
> committed JSON, since entities are matched by prefix at render time, never
> hardcoded. Adding a new room = one entry in the `area` variable.

> The three zigbee2mqtt dashboards are linked: the overview's device table links to
> `/d/zigbee2mqtt-device?var-device=<ieee_address>` (the stable IEEE address, not the
> friendly name, so it survives device renames). All three are tagged `zigbee2mqtt-integration`
> and carry an "All zigbee2mqtt dashboards" links dropdown for cross-navigation. The overview
> models the Docker dashboards' table-sparkline pattern (`timeSeriesTable` → Trend columns →
> `joinByField`/`organize`). Source metrics come from `job="integrations/zigbee2mqtt"`.

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

### Snapshot & verify visually

**Don't trust the JSON — render it and look.** After uploading, take a PNG
snapshot and actually inspect it (with the `Read` tool); a valid, well-formed
JSON can still render wrong (e.g. per-series `fillOpacity` stacking into a grey
blob that buries a min–max band). `gcx dashboards snapshot` renders via the
Grafana Image Renderer:

```bash
# whole dashboard (collapsed rows render collapsed — good for "do all rows exist")
gcx dashboards snapshot {uid} --since 24h --output-dir .

# a single panel is the real visual check — pass template-var overrides so it
# has data (repeating-row/collapsed panels render empty at the dashboard level)
gcx dashboards snapshot {uid} --panel {panelId} --var area=toms_office \
  --since 24h --width 1100 --height 500 --output-dir .
```

- Panel snapshots default to `home-temperature-by-area-panel-{id}.png`; **it is
  overwritten each call**, so `mv` it to a distinct name between renders (e.g. when
  comparing two areas) or you'll read the same image twice.
- Use `--panel {id}` + `--var {name}={value}` to force data into a **repeating /
  collapsed** panel — a dashboard-level snapshot of collapsed rows shows only the
  row headers, not the graphs.
- ⚠️ **PII:** a full-dashboard snapshot renders the datasource picker showing the
  real stack slug (which contains the street name). That's only in the throwaway
  PNG, never the committed JSON — **do not** commit or `SendUserFile` the
  full-dashboard PNG. A single-panel PNG doesn't show the picker and is safe to
  share.

### Workflow

1. **Check for remote changes** before editing — diff local vs live (see above)
2. Edit `observability/dashboards/{slug}.json` in this repo
3. Diff to review your outgoing change
4. Upload to Grafana
5. **Snapshot the changed panel(s) and verify visually** (see above) — not just
   that the JSON is valid
6. Commit to git

## Grafana Alerting

Alert and recording rules are **Grafana-managed** (provisioned via
`/api/v1/provisioning/alert-rules`). They are **not** yet file-managed in this
repo; this section records their intent. Datasources are referenced by their
generic UIDs `grafanacloud-logs` (Loki) and `grafanacloud-prom` (Prometheus) —
**never** the stack-slug-prefixed datasource names, which embed PII (see
[CLAUDE.md](CLAUDE.md)).

Manage with `gcx`:

```bash
gcx alert rules list                 # list (read-only)
gcx api /api/v1/provisioning/alert-rules            # full JSON (GET)
gcx api /api/v1/provisioning/alert-rules -X POST -H "X-Disable-Provenance: true" -d @rule.json
# (X-Disable-Provenance keeps the rule UI-editable instead of locked/provisioned)
```

The stack already uses the **recording-rule → metric → alert** pattern (e.g.
`zigbee2mqtt_errors:rate15m`): a Grafana-managed recording rule runs a LogQL
metric query and writes the result to Prometheus, then an alert thresholds the
metric.

### IOT DNAT redirect drift tripwire

Detects if the UDM's IOT NTP/DNS DNAT redirects are removed (reboot before the
boot service runs, or a controller provision flush — see
[@network-security.md](network-security.md)). When the redirect is gone, IOT
:53/:123 escapes to the internet and hits the logged BLOCK rules; those are ~0
while the redirect works, so any sustained hits = drift.

| Rule (folder `Unifi`) | Type | Definition |
|---|---|---|
| `iot_dnat_tripwire` | recording → `iot_dnat_block_hits:count5m` | Loki: `sum(count_over_time({log_type="firewall", rule=~"Block IOT (DNS\|NTP) to Internet"} \|~ "DPT=(53\|123) " [5m])) or vector(0)` |
| `IOT DNAT redirect removed` | alert | thresholds `iot_dnat_block_hits:count5m > 0`, `for: 5m` → email contact point |

- The `DPT=(53|123)` line filter is essential: the `Block IOT DNS to Internet`
  rule also matches DoT (`:853`), which has a legitimate ongoing baseline (devices
  attempting DoH/DoT that can't be transparently redirected). Filtering to
  `53`/`123` keeps the tripwire at 0 in steady state — no false alerts.
- `or vector(0)` keeps the series present at 0 so the alert always has data.
- **Remediation** (in the alert annotation): `ssh root@192.168.0.1
  '/persistent/iot-redirect/apply.sh'` (or `systemctl restart iot-redirect` — not
  `start`, which is a no-op on the `RemainAfterExit` oneshot).
