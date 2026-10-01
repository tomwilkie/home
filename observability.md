# Observability

[Grafana Alloy](https://grafana.com/docs/alloy/latest/) ships Home Assistant metrics and logs to
Grafana Cloud. It runs as a plain Docker container on the Home Assistant OS (HAOS) host.

## Why Alloy is not an add-on

Add-ons run inside the Supervisor's managed Docker environment, which does not let a container
mount the host's `/proc` or `/sys`. Node exporter metrics (CPU, memory, disk and network at the
host level) need those mounts. The restriction is deliberate, as the
[community thread](https://community.home-assistant.io/t/mount-hosts-proc-sys-into-add-on-container/848705/3)
and [discussion #3203](https://github.com/orgs/home-assistant/discussions/3203) explain. Alloy
therefore runs as a standalone container under Docker Compose, outside the Supervisor.

## Architecture

Alloy collects from the following sources and ships everything to Grafana Cloud Prometheus and
Loki:

```
HAOS host
└── Grafana Alloy (Docker, host network)
    ├── scrapes /proc, /sys          → node metrics
    ├── scrapes Docker socket        → container metrics (cAdvisor) + container logs
    ├── reads /var/log/journal       → systemd journal logs
    ├── scrapes localhost:8123       → Home Assistant metrics
    ├── scrapes localhost:9142       → zigbee2mqtt metrics
    ├── discovers unpoller add-on    → UniFi network metrics
    ├── receives UDM syslog on :514  → UniFi events (raw UDP, split by log_type)
    └── tails AdGuard querylog.json  → IOT DNS query log
```

Alloy runs with `network_mode: host` so that it reaches Home Assistant on `localhost:8123`.

## Metrics

The following table lists the scrape jobs:

| Source | Job label | Notes |
|---|---|---|
| Alloy | `integrations/alloy` | Health and pipeline metrics |
| Node | `integrations/node_exporter` | CPU, memory, disk and network from `/proc` and `/sys` |
| Docker containers | `integrations/docker` | Per-container resource usage from cAdvisor |
| Home Assistant | `integrations/homeassistant` | All entity states from `/api/prometheus` |
| zigbee2mqtt | `integrations/zigbee2mqtt` | Link quality, message and join counters, adapter queue and retries, from the z2m exporter on `localhost:9142` |
| Unpoller | `integrations/unpoller` | UniFi device metrics. Alloy finds the add-on through Docker service discovery, because add-on DNS is unreachable from the host network. Unpoller 5.0.2 has no `umbb` device support, so the U5G Max has no cellular signal history. |

### Match add-on containers on the slug

Don't key discovery or relabelling on the Supervisor's container-name prefix. Add-on containers
are named `<kind>_<repo>_<slug>`, where `<repo>` is `core`, `local` or an eight-character
repository hash, and the Supervisor renamed `<kind>` from `addon` to `app`. A rule that matched
`addon_` then matched nothing, and the unpoller job disappeared with no error and no `up == 0`.

Match the stable parts instead. The unpoller scrape keeps `/.+_unpoller`, and the Docker log
pipeline strips any `[a-z]+_(core|local|<8 hex>)_` prefix. `hassio_*` and compose containers
have no `<repo>` segment, so they pass through unchanged. The [_Exporter down_](#exporter-down)
alert is the backstop, because it fires on a job that has vanished.

## Logs

Alloy gives every log stream an explicit `service_name` label, and the stream's `job` is
`integrations/<name>`. The explicit label overrides Loki's `discover_service_name`, which
otherwise picks the raw container name for Docker and the per-event CEF `name` label (`motion`,
`Ring`) for UniFi.

| Source | `service_name` | `job` | `instance` | Other labels |
|---|---|---|---|---|
| Alloy's own logs | `alloy` | `integrations/alloy` | hostname | |
| Docker container logs | container name with the add-on prefix stripped | `integrations/docker` | hostname | `container`, `stream`, `compose_service` |
| Systemd journal | `linux` | `integrations/linux` | hostname | `unit`, `level`, `container` |
| UniFi syslog | `unifi` | `integrations/unifi` | `udm` | `log_type`, plus the labels in [_UniFi syslog_](#unifi-syslog) |
| AdGuard Home query log | `adguard` | `integrations/adguard` | hostname | |

The AdGuard add-on's container stdout also arrives through the Docker pipeline as
`service_name=adguard` with `job=integrations/docker`. That stream is AdGuard's operational log,
not the query log. To tell them apart, select on `job`.

Loki keeps logs for 30 days, and a query range longer than about 30 days is rejected.

### Home Assistant's own logs

Home Assistant Core's container log arrives through the Docker pipeline as
`service_name="homeassistant"`. Loki is the only copy older than about four hours: `ha core
logs`, the `error_log` API and the MCP `ha_get_logs` tool all read a rolling in-memory buffer.

```sh
gcx logs query '{job="integrations/docker", service_name="homeassistant"}' \
  --from "2026-09-20T02:55:00Z" --to "2026-09-20T03:45:00Z" \
  --limit 5000 --jq '[.data.result[].values[].line] | .[]'
```

- **`--from` and `--to` are UTC, and the timestamps inside each line are local.** In British Summer Time a window aimed at the 04:00 restart by its log timestamps returns 05:00 instead. Convert first, then check the first line that comes back.
- **The result shape is `.data.result[].values[].line`**, an object per entry, not the `[ts, line]` tuple of the raw Loki HTTP API.
- **A multi-line traceback arrives as separate log lines**, so a line filter that matches the exception does not match the `Traceback` line or the frames. Pull the whole window and read around the match.

### UniFi syslog

The UDM's remote logging does not emit RFC-compliant syslog. It sends Common Event Format (CEF)
over UDP, with no `<PRI>` prefix and with the site name in the hostname position:

```
Jun 17 12:42:00 <site name> CEF:0|Ubiquiti|UniFi Protect|7.1.83|2159|motion|3|UNIFIcategory=detection ... msg="..."
```

The strict RFC 3164 and RFC 5424 parsers reject this, so `loki.source.syslog "unifi"` listens
with `syslog_format = "raw"`, which passes each datagram through unparsed. `raw` is an
experimental Alloy feature, so `docker-compose.yml` starts the container with
`--stability.level=experimental`. The listener binds `0.0.0.0:514`, reachable on the LAN at the
Home Assistant host address `192.168.0.12`.

One UDP stream carries four unrelated kinds of line. `loki.process "unifi"` classifies each line
by content into a `log_type` label, using `stage.match` blocks whose selector is a `|=` line
filter. Without the split, sporadic camera events are buried under firewall flow logs:

| `log_type` | Matches lines containing | Extra labels |
|---|---|---|
| `firewall` | `[CUSTOM` (the iptables policy log prefix) | `rule`, the policy name from `DESCR` |
| `dns` | `coredns[` | none |
| `cef` | `CEF:` | `product`, `name`, `severity` from the CEF header |
| `system` | anything else (UniFi OS daemons such as `mcad`, `earlyoom`, `wevent`) | none |

Only bounded fields become labels. High-cardinality fields (source and destination addresses,
ports, DNS domains) stay in the log body, and you query them with `|=` or `|~`.

The site name in the hostname position is the home address. Alloy does not strip it, because the
logs go to a private Grafana Cloud stack. If that changes, add a `stage.regex` that keeps only
the part from `CEF:` onwards, plus a `stage.output`.

Configure the UDM side in the UniFi UI, not through the MCP server, because the site-settings
payload echoes the home address. Enable remote logging, set **Server Address** to `192.168.0.12`
and **Port** to `514` (UDP), and select the categories. No firewall rule is needed, because the
ZBF predefined matrix allows gateway to Internal traffic.

### UniFi firewall and DNS logs

With the UDM's **firewall** logging category enabled, the stream carries two kinds of non-CEF
line.

**Firewall lines** (`log_type=firewall`) come from any policy with `logging: true`, and the
policy name is the `rule` label:

```
Jun 19 10:14:06 <host> [CUSTOM1_WAN-A-10003] DESCR="Log IOT to Internet (ALLOW)"
IN=br2 OUT=eth8 SRC=192.168.2.67 DST=34.159.33.52 PROTO=TCP SPT=... DPT=443 ...
```

To narrow to one device, add a line filter:
`{log_type="firewall", rule="Log IOT to Internet (ALLOW)"} |= "SRC=192.168.2.67"`. The policies
are described in [network-security.md](network-security.md).

**CoreDNS lines** (`log_type=dns`) are JSON, and cover only the queries that the UDM's ad
blocking stopped (`"type":"dnsAdBlock"`), not full resolution. IOT resolution goes through
AdGuard Home instead.

### Verify syslog ingestion

To tell "the UDM isn't sending" from "Alloy is dropping", capture on the host, which sees
packets before Alloy does, then read Alloy's own counters:

```sh
tcpdump -ni any udp port 514 -A
curl -s localhost:12345/metrics | grep -E 'loki_source_syslog_entries_total|loki_write_(dropped|sent)_entries_total'
```

Firewall lines are high-volume. CEF events arrive a few per minute, so a short quiet capture is
normal for CEF alone.

### AdGuard Home query log

AdGuard Home is the IOT resolver, as described in
[_DNS and NTP forcing_](network-security.md#dns-and-ntp-forcing). Alloy ships its query log to
Loki so that DNS lookups can be queried with LogQL next to the firewall log. AdGuard keeps its
own copy for 90 days, and Loki keeps 30.

AdGuard has no log export, so Alloy reads the file:

- **Mount:** the add-on's data directory is bind-mounted read-only into Alloy at `/adguard`, from host path `/mnt/data/supervisor/apps/data/a0d7b954_adguard/adguard/data`. The mount is the directory, not the file, so the tail survives rotation, which re-creates `querylog.json` with a different inode.
- **Tail:** `local.file_match` and `loki.source.file` tail only `querylog.json`, not the rotated `querylog.json.1`, so a rotation does not re-send a whole file.
- **Timestamp:** each line is one JSON object and becomes the log body. `stage.json` and `stage.timestamp` set the Loki timestamp from AdGuard's `T` field, so a catch-up after Alloy downtime keeps the real query times.

A line has the following shape:

```
{"T":"…","QH":"connect.prusa3d.com","QT":"AAAA","IP":"192.168.2.67",
 "Upstream":"https://dns10.quad9.net:443/dns-query","Result":{},"Cached":true,…}
```

The domain (`QH`) and client (`IP`) stay in the body, so parse them at query time:

```
{job="integrations/adguard"} | json | IP="192.168.2.67"
```

Only devices that resolve through AdGuard appear. A device that uses DoH shows up only as
destination addresses in the firewall log.

#### Flush every query to disk

`size_memory: 0` is set in `AdGuardHome.yaml`. AdGuard buffers the most recent `size_memory`
queries in memory and writes `querylog.json` only when the buffer fills, with no timer. At the
default of 1000 the file, and so Loki, updated in roughly hourly batches. AdGuard treats `0` as a
buffer of one, so it writes after every query and Alloy ships each line within seconds. The cost
is one small file append per DNS query.

The setting is not in the AdGuard UI or API. AdGuard owns and rewrites `AdGuardHome.yaml`, so to
change it, stop the add-on (slug `a0d7b954_adguard`), edit
`/mnt/data/supervisor/apps/data/a0d7b954_adguard/adguard/AdGuardHome.yaml`, then start the
add-on.

## Environment variables

Copy `observability/.env.example` to `observability/.env` and set the following:

| Variable | Description |
|---|---|
| `STACK_NAME` | Grafana Cloud stack slug |
| `ACCESS_TOKEN` | `glc_…` token with the MetricsPublisher and LogsPublisher roles |
| `HASS_METRICS_TOKEN` | Long-lived Home Assistant token for scraping `/api/prometheus` |

## Deployment

Run the following targets from the `observability/` directory. They act on the HAOS host over
SSH as `root@homeassistant.local`:

| Target | Action |
|---|---|
| `make deploy` | `push` then `up` |
| `make push` | Create `/homeassistant/alloy/` on the host and upload `alloy/config.alloy` |
| `make up` | `docker compose up -d` |
| `make down` | `docker compose down` |
| `make restart` | `docker compose restart alloy` |
| `make logs` | Tail the last 100 lines of Alloy logs |
| `make ps` | Show container status |
| `make shell` | Open a shell inside the Alloy container |

`make push` writes the config to `/homeassistant/alloy/config.alloy`, which the Supervisor sees
as `/mnt/data/supervisor/homeassistant/alloy/config.alloy`. Alloy's persistent state is the
Docker volume `alloy-data`.

## Grafana dashboards

Dashboard JSON files live in `observability/dashboards/`. This repo is the source of truth, so
edit the file here and upload it to Grafana.

| File | UID | Description |
|---|---|---|
| `docker-cluster-overview.json` | `docker-cluster-overview` | One row per Docker host |
| `docker-container-overview.json` | `docker-container-overview` | Per-container drill-down |
| `docker-host-overview.json` | `docker-host-overview` | Aggregate resource usage for one host |
| `zigbee2mqtt-overview.json` | `zigbee2mqtt-overview` | Fleet summary stats and a per-device table with last-seen age, link quality and message sparklines |
| `zigbee2mqtt-coordinator.json` | `zigbee2mqtt-coordinator` | Coordinator and adapter health: version, network status, MQTT throughput, queue and retries |
| `zigbee2mqtt-device.json` | `zigbee2mqtt-device` | Per-device drill-down, where `device` is the IEEE address |
| `home-temperature-by-area.json` | `home-temperature-by-area` | One row per area, each with a time series of that area's temperature entities |

The zigbee2mqtt dashboards are tagged `zigbee2mqtt-integration` and link to each other. The
overview's device table links to `/d/zigbee2mqtt-device?var-device=<ieee_address>`. It uses the
IEEE address and not the friendly name, so the link survives a device rename.

### Workflow

1. Diff the local file against Grafana, and fetch the live version first if they differ:

   ```bash
   diff <(jq -S . observability/dashboards/SLUG.json) <(gcx api /api/dashboards/uid/UID | jq -S .)
   gcx api /api/dashboards/uid/UID | jq . > observability/dashboards/SLUG.json
   ```

   Fetch with `jq .` and not `jq -S`, to keep the original key order and small diffs.

2. Edit `observability/dashboards/SLUG.json`.
3. Upload it. The stored file has `dashboard` and `meta` keys, and the upload endpoint wants `dashboard` and `overwrite`:

   ```bash
   jq '{dashboard: .dashboard, overwrite: true}' observability/dashboards/SLUG.json \
     | gcx api /api/dashboards/db -d @-
   ```

4. Snapshot the changed panels and look at them, as described in [_Verify a dashboard visually_](#verify-a-dashboard-visually).
5. Commit.

### Verify a dashboard visually

Valid JSON can still render wrong, so render the dashboard after every upload and read the PNG.
`gcx dashboards snapshot` uses the Grafana Image Renderer:

```bash
gcx dashboards snapshot UID --since 24h --output-dir .
gcx dashboards snapshot UID --panel PANEL_ID --var area=toms_office \
  --since 24h --width 1100 --height 500 --output-dir .
```

- **A single-panel snapshot is the real check.** Pass `--panel` and a `--var` override, because a repeating panel renders empty at the dashboard level.
- **Each call overwrites `<uid>-panel-<id>.png`.** Rename the file between renders when you compare two.
- **Don't commit or share a full-dashboard snapshot.** It renders the datasource picker, which shows the stack slug, and the slug contains the street name. A single-panel snapshot does not show the picker.

### How `home-temperature-by-area` derives the area

The Home Assistant Prometheus exporter emits no `area` label, so the dashboard groups by the
area-first `entity` ID prefix from [naming-conventions.md](naming-conventions.md).

- **A custom `area` variable lists `Display : <slug-regex>` pairs.** One repeating row (`repeat: "area"`) clones a graph per area. To add a room, add one entry to the variable.
- **The value is a regular expression fragment.** Hallway is `(hallway|front_door)`, and full slugs avoid the `master_bedroom` and `master_bathroom` prefix collision.
- **Interpolate with `${area:raw}`.** Grafana escapes a multi-value variable inside `=~`, which breaks the Hallway alternation.
- **The row is expanded.** It has `collapsed: false` and an empty `panels: []`, with the time series as a top-level sibling beneath it. Grafana needs that structure to repeat an expanded row.
- **A grey band shows the minimum-to-maximum range.** Two extra queries (`Min` and `Max`) and a `Max` field override of `custom.fillBelowTo: "Min"` draw it. Per-line `fillOpacity` is 0, because stacked line fills otherwise hide the band.
- **Only rooms appear.** Entities match by prefix at render time, which keeps the Server Rack entity, whose ID contains the street address, out of the committed JSON.

The queries exclude the following series:

| Excluded from | Series | Reason |
|---|---|---|
| Lines and band | `target_temperature` | A setpoint, not a reading |
| Lines and band | `boiler_monitor_temperature_[0-9]` | Boiler pipe probes |
| Lines and band | `device_temperature`, `internal_temperature`, `battery_temperature`, `door_temperature` | The temperature a device reports about itself, which reads 26 to 57 °C in a 22 to 28 °C room and compresses the axis |
| Band only | `outside` | The aircon outdoor probe, a real reading that distorts the room range |

The Norman shutter-motor temperatures stay in, because they track room temperature and give
per-window coverage. Radiators and towel heaters stay in the band, so radiator-only rooms get
one.

## Grafana alerting

Alert and recording rules are Grafana-managed and provisioned through
`/api/v1/provisioning/alert-rules`. Rules with a JSON file in `observability/alerts/` are
file-managed, and this section records the intent of the rest. Reference datasources by the
generic UIDs `grafanacloud-logs` and `grafanacloud-prom`, not by the datasource names, which
embed the stack slug.

```bash
gcx alert rules list
gcx api /api/v1/provisioning/alert-rules
gcx api /api/v1/provisioning/alert-rules -X POST -H "X-Disable-Provenance: true" -d @rule.json
```

`X-Disable-Provenance` keeps the rule editable in the UI.

The stack uses a recording rule, then a metric, then an alert: a Grafana-managed recording rule
runs a LogQL metric query and writes the result to Prometheus, and an alert thresholds the
metric. `zigbee2mqtt_errors:rate15m` is an example.

### Exporter down

`observability/alerts/exporter-down.json` defines one rule in folder `Observability`, group
`exporters`, with a one-minute interval and `for: 5m`. The default notification policy routes it
to email. It produces one alert instance per `job` and fires when the value is less than 1:

```promql
min by (job) (up)
or label_replace(vector(0), "job", "integrations/alloy", "", "")
or label_replace(vector(0), "job", "integrations/unpoller", "", "")
# … one line per expected job
```

- **`up == 0` alone is not enough.** It catches a target that is discovered and failing. A target that was never discovered has no `up` series. Each `label_replace(vector(0), …)` line supplies a `0` for an expected job, and `or` keeps it only when the job has no real series.
- **`min`, not `sum`,** so one failing target in a multi-target job still fires.
- **To add an exporter, add its line** and send the JSON again. The expected jobs are `alloy`, `docker`, `homeassistant`, `node_exporter`, `zigbee2mqtt` and `unpoller`.
- **If Alloy stops, every instance fires together.** That is intended.
- **`noDataState` is `Alerting`.** The fallbacks mean the query always returns data, so no data means the datasource is broken.

To test the absence path, evaluate the expression with a made-up job, which must return `0`:

```sh
gcx metrics query -d grafanacloud-prom \
  'min by (job) (up) or label_replace(vector(0), "job", "integrations/does_not_exist", "", "")'
```

After you edit the file, update the rule:

```sh
gcx api /api/v1/provisioning/alert-rules/exporter-down -X PUT \
  -H "X-Disable-Provenance: true" -d @observability/alerts/exporter-down.json
```

### U5G Max modem reset

`observability/alerts/u5g-modem-reset.json` defines one rule in folder `Unifi`, group `u5g-max`,
with a one-minute interval and `for: 0s`. It fires on any match in the UniFi syslog in the last
10 minutes, so one reset produces one notification that resolves about 10 minutes later:

```logql
sum(count_over_time({job="integrations/unifi"}
  |~ "U5G-Max.*(schedule syserr_worker|Modem disconnect detected)|wf-interface-gre1 .* is down"
  [10m])) or vector(0)
```

The U5G Max's cellular modem (a Sierra Wireless EM9291) hangs and reboots itself, typically on
weekday mornings, and keeps no crash dump. The rule exists to count those resets while firmware
fixes are tried, so it matches two independent signatures:

- **The U5G's own log lines.** `schedule syserr_worker` is the kernel seeing the modem reset, and `Modem disconnect detected` is the U5G's modem daemon losing it. Both lines carry the `U5G-Max-<version>` hostname, so the match survives a firmware upgrade unless the messages change. It survived 7.5.3 to 8.0.2: the flash on 2026-10-01 fired the rule from `U5G-Max-8.0.2+19972` lines.
- **The UDM's failover monitor marking the 5G WAN (`gre1`) down.** It does not depend on the U5G's firmware or logging, and it also catches 5G outages that are not modem resets.

To read the reset history further back than Loki's 30 days, copy the U5G's own logs with
`scripts/unifi-ssh device 192.168.4.34` (see [access-home-assistant.md](access-home-assistant.md#unifi-ssh)):
`/var/log/uiwwand-atd.log*` records every reset as `active AT device removed`, and
`/var/log/uiwwand-signal.log*` records serving-cell changes and signal samples, for about the
last five days.

#### Investigation status (2026-10-01)

- **Onset.** No modem resets from 2026-07-02 to 2026-08-04. The first was on 2026-08-05, four days after the U5G upgraded from 7.4.1 to 7.5.3, which left the modem firmware (`SWIX65C_02.17.08.00`) unchanged. There were 75 resets from then to 2026-09-25.
- **Pattern.** 36 of the 75 fell between 08:00 and 10:00, nearly all on weekdays (Fri 23, Thu 19, Sat 4, Sun 1). Load-balanced, the rate was 1.49 a day, with a reset on 61% of weekdays. As backup only, from 2026-09-20, it fell to 0.42 a day and 22% of weekdays, but four of the five resets as backup came with the link idle.
- **Ruled out.** Signal (SINR 12 to 17 dB, transmit power about 15 dBm), heat (43 °C), PoE (the U5G is not powered by the AP's passthrough port) and cell switching (about 260 a day, peaking at 13:00 to 16:00, not in the morning).
- **Change.** On 2026-10-01 the U5G went to Early Access 8.0.2 by manual firmware URL, which updated the modem to `SWIX65C_03.04.10.01`. After the update, SINR on the same n78 cell reads 0 to 3.5 dB, with RSRP and RSRQ unchanged, which may be a reporting change. A 30-ping test over `wwan0` showed no loss and a 42 ms average.
- **Plan.** Keep the U5G as backup for a week. If no resets occur, return it to load balancing for at least two weeks, the condition that produced most resets. Compare the 07:52 speed test over `gre1` (`unpoller_device_speedtest_download{port="if!gre1"}`, 314 Mbps before the upgrade) to tell a SINR reporting change from a real loss. If the radio is worse or the resets continue, roll back to 7.5.3, which is cached on the UDM.

### IOT DNAT redirect tripwire

The tripwire detects the removal of the UDM's DNS and NTP redirects described in
[_DNAT redirect_](network-security.md#dnat-redirect). Without the redirect, IOT port 53 and port
123 traffic escapes towards the internet and hits the logged BLOCK rules, which otherwise stay
at zero.

| Rule (folder `Unifi`) | Type | Definition |
|---|---|---|
| `iot_dnat_tripwire` | Recording rule, writes `iot_dnat_block_hits:count5m` | `sum(count_over_time({log_type="firewall", rule=~"Block IOT (DNS\|NTP) to Internet"} \|~ "DPT=(53\|123) " [5m])) or vector(0)` |
| `IOT DNAT redirect removed` | Alert | `iot_dnat_block_hits:count5m > 0`, `for: 5m`, to the email contact point |

- **The `DPT=(53|123)` line filter is required.** `Block IOT DNS to Internet` also matches DNS over TLS on port 853, which the redirect cannot rewrite, so port 853 hits are not drift.
- **`or vector(0)` keeps the series present at 0,** so the alert always has data.
- **The remediation is in the alert annotation:** run `apply.sh`, as described in [_Persistence_](network-security.md#persistence).
