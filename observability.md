# Observability

[Grafana Alloy](https://grafana.com/docs/alloy/latest/) ships Home Assistant metrics and logs,
and continuous profiles of itself and of Home Assistant Core, to Grafana Cloud. It runs as a plain Docker container on the Home Assistant OS (HAOS) host, with
`network_mode: host` so that it reaches Home Assistant on `localhost:8123`.

## Why Alloy is not an add-on

Add-ons run inside the Supervisor's managed Docker environment, which does not let a container
mount the host's `/proc` or `/sys`, and node exporter metrics need those mounts. The restriction
is deliberate, as the
[community thread](https://community.home-assistant.io/t/mount-hosts-proc-sys-into-add-on-container/848705/3)
and [discussion #3203](https://github.com/orgs/home-assistant/discussions/3203) explain, so
Alloy runs under Docker Compose outside the Supervisor.

## Why Alloy runs without AppArmor

`docker-compose.yml` runs Alloy with `apparmor=unconfined`, next to `seccomp:unconfined`. Alloy
shares the host's process namespace and reads other processes' `/proc` entries on every scrape.
Docker's default AppArmor profile, `docker-default`, denies those reads, and the kernel logs each
denial as an audit record, enough to overflow the kernel's audit backlog. The
[_AppArmor audit flood_](history.md#2026-10-30-apparmor-audit-flood) entry in history.md has the
measurements.

## Metrics

The following table lists the scrape jobs:

| Source | Job label | Notes |
|---|---|---|
| Alloy | `integrations/alloy` | Health and pipeline metrics |
| Node | `integrations/node_exporter` | CPU, memory, disk and network from `/proc` and `/sys` |
| Docker containers | `integrations/docker` | Per-container resource usage from cAdvisor |
| Home Assistant | `integrations/homeassistant` | All entity states from `/api/prometheus` |
| zigbee2mqtt | `integrations/zigbee2mqtt` | Link quality, message and join counters, adapter queue and retries, from the z2m exporter on `localhost:9142` |
| Unpoller | `integrations/unpoller` | UniFi device metrics, found through Docker service discovery because add-on DNS is unreachable from the host network. Includes the U5G Max's cellular metrics (`type="umbb"`, `unpoller_device_mbb_*`) from 2026-10-03. See [_Unpoller add-on_](#unpoller-add-on). |

### Match add-on containers on the slug

Add-on containers are named `<kind>_<repo>_<slug>`, where `<repo>` is `core`, `local` or an
eight-character repository hash, and the Supervisor has renamed `<kind>` before (`addon` to
`app`). Match the stable parts, not the prefix: the unpoller scrape keeps `/.+_unpoller`, and
the Docker log pipeline strips any `[a-z]+_(core|local|<8 hex>)_` prefix. `hassio_*` and compose
containers have no `<repo>` segment, so they pass through unchanged. A prefix match fails
silently, with no error and no `up == 0`, and the [_Exporter down_](#exporter-down) alert is the
backstop because it fires on a job that has vanished.

### Unpoller add-on

The UnPoller add-on comes from
[tomwilkie/home-assistant-addons](https://github.com/tomwilkie/home-assistant-addons), a copy
of [bluemaex's add-on](https://github.com/bluemaex/home-assistant-addons/tree/main/unpoller)
that bumps unpoller to v5.5.0, the first release with U5G Max (`umbb`) support. bluemaex's
Renovate holds major bumps for approval, so that add-on stayed on v3.5.0. The bump is proposed
upstream as
[bluemaex/home-assistant-addons#612](https://github.com/bluemaex/home-assistant-addons/pull/612).

- **Installed slug `39e0dbb4_unpoller`.** It has no prebuilt image, so the Supervisor builds it from the Dockerfile. To move to a newer unpoller, bump the tag in the Dockerfile and the add-on `version`, then update the add-on.
- **bluemaex's `71dadad1_unpoller` is stopped with `boot: manual`.** Both publish host port 9130, so only one can run, and both read `/config/addons/unpoller/up.conf`.

The UniFi-Poller dashboards in the Grafana `Unifi` folder are imported from
[unpoller/dashboards](https://github.com/unpoller/dashboards/tree/master/v2.0.0), with
`${DS_PROMETHEUS}` replaced by `grafanacloud-prom`, and are not file-managed in this repo.
`UniFi-Poller: UMBB Insights - Prometheus` (`unpoller-umbb`) covers the U5G Max.

## Logs

Alloy gives every log stream an explicit `service_name` label, and the stream's `job` is
`integrations/<name>`. The explicit label overrides Loki's `discover_service_name`, which
otherwise picks the raw container name for Docker and the per-event CEF `name` label (`motion`,
`Ring`) for UniFi.

| Source | `service_name` | `job` | `instance` | Other labels |
|---|---|---|---|---|
| Alloy's own logs | `alloy` | `integrations/alloy` | hostname | |
| Docker container logs | container name with the add-on prefix stripped | `integrations/docker` | hostname | `container`, `stream`, `compose_service` |
| Systemd journal | `linux` | `integrations/linux` | hostname | `unit`, `level` |
| UniFi syslog | `unifi` | `integrations/unifi` | `udm` | `log_type`, plus the labels in [_UniFi syslog_](#unifi-syslog) |
| AdGuard Home query log | `adguard` | `integrations/adguard` | hostname | |

HAOS sends container output to journald as well as to Docker. The journal pipeline drops any
entry with a container name, because the Docker pipeline already ships it, and keeps Docker's
own `docker.service` lines, which have none. The cost is that container logs have no second
path: if the Docker pipeline stops matching a container, its logs are lost rather than still
arriving through the journal.

The AdGuard add-on's container stdout also arrives as `service_name=adguard` with
`job=integrations/docker`. That is AdGuard's operational log, not the query log, so select on
`job`.

Loki keeps logs for 30 days and rejects a longer query range.

### Home Assistant's own logs

Home Assistant Core's container log arrives as `service_name="homeassistant"`. Loki is the only
copy older than about four hours: `ha core logs`, the `error_log` API and the MCP `ha_get_logs`
tool all read a rolling in-memory buffer.

```sh
gcx logs query '{job="integrations/docker", service_name="homeassistant"}' \
  --from "2026-09-20T02:55:00Z" --to "2026-09-20T03:45:00Z" \
  --limit 5000 --jq '[.data.result[].values[].line] | .[]'
```

- **`--from` and `--to` are UTC, and the timestamps inside each line are local.** In British Summer Time a window aimed at the 04:00 restart by its log timestamps returns 05:00 instead.
- **The result shape is `.data.result[].values[].line`**, an object per entry, not the `[ts, line]` tuple of the raw Loki HTTP API.
- **A multi-line traceback arrives as separate log lines**, so a line filter that matches the exception misses the `Traceback` line and the frames. Pull the whole window and read around the match.

### UniFi syslog

The UDM's remote logging sends Common Event Format (CEF) over UDP, with no `<PRI>` prefix and
with the site name in the hostname position:

```
Jun 17 12:42:00 <site name> CEF:0|Ubiquiti|UniFi Protect|7.1.83|2159|motion|3|UNIFIcategory=detection ... msg="..."
```

The RFC 3164 and RFC 5424 parsers reject this, so `loki.source.syslog "unifi"` listens with
`syslog_format = "raw"`, which passes each datagram through unparsed. `raw` is experimental, so
`docker-compose.yml` starts Alloy with `--stability.level=experimental`. The listener binds
`0.0.0.0:514`, reachable on the LAN at `192.168.0.12`.

One UDP stream carries four unrelated kinds of line, and without a split the sporadic camera
events are buried under firewall flow logs. `loki.process "unifi"` sets a `log_type` label from
`stage.match` blocks with `|=` line filters:

| `log_type` | Matches lines containing | Extra labels |
|---|---|---|
| `firewall` | `[CUSTOM` (the iptables policy log prefix) | `rule`, the policy name from `DESCR` |
| `dns` | `coredns[` | none |
| `cef` | `CEF:` | `product`, `name`, `severity` from the CEF header |
| `system` | anything else (UniFi OS daemons such as `mcad`, `earlyoom`, `wevent`) | none |

Only bounded fields become labels. Addresses, ports and DNS domains stay in the log body, and you
query them with `|=` or `|~`.

The site name in the hostname position is the home address. Alloy does not strip it, because the
logs go to a private Grafana Cloud stack. If that changes, add a `stage.regex` that keeps only
the part from `CEF:` onwards, plus a `stage.output`.

Configure the UDM side in the UniFi UI, not through the MCP server, because the site-settings
payload echoes the home address: enable remote logging, set **Server Address** to `192.168.0.12`
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
are in [network-security.md](network-security.md).

**CoreDNS lines** (`log_type=dns`) are JSON and cover only the queries that the UDM's ad blocking
stopped (`"type":"dnsAdBlock"`). IOT resolution goes through AdGuard Home instead.

### Verify syslog ingestion

To tell "the UDM isn't sending" from "Alloy is dropping", capture on the host, which sees
packets before Alloy does, then read Alloy's own counters:

```sh
tcpdump -ni any udp port 514 -A
curl -s localhost:12345/metrics | grep -E 'loki_source_syslog_entries_total|loki_write_(dropped|sent)_entries_total'
```

Firewall lines are high-volume, and CEF events arrive a few per minute, so a short quiet capture
is normal for CEF alone.

### AdGuard Home query log

AdGuard Home is the IOT resolver, as described in
[_DNS and NTP forcing_](network-security.md#dns-and-ntp-forcing). Alloy ships its query log to
Loki so that DNS lookups can be queried with LogQL next to the firewall log. AdGuard keeps its
own copy for 90 days.

AdGuard has no log export, so Alloy reads the file:

- **Mount:** the add-on's data directory, `/mnt/data/supervisor/apps/data/a0d7b954_adguard/adguard/data`, is bind-mounted read-only at `/adguard`. Mounting the directory rather than the file means the tail survives rotation, which re-creates `querylog.json` with a different inode.
- **Tail:** `local.file_match` and `loki.source.file` tail only `querylog.json`, not the rotated `querylog.json.1`, so a rotation does not re-send a whole file.
- **Timestamp:** each line is one JSON object and becomes the log body. `stage.json` and `stage.timestamp` take the Loki timestamp from AdGuard's `T` field, so a catch-up after Alloy downtime keeps the real query times.

A line has the following shape, and the domain (`QH`) and client (`IP`) are parsed at query
time:

```
{"T":"…","QH":"connect.prusa3d.com","QT":"AAAA","IP":"192.168.2.67",
 "Upstream":"https://dns10.quad9.net:443/dns-query","Result":{},"Cached":true,…}
```

```
{job="integrations/adguard"} | json | IP="192.168.2.67"
```

Only devices that resolve through AdGuard appear. A device that uses DoH shows up only as
destination addresses in the firewall log.

#### Flush every query to disk

`size_memory: 0` is set in `AdGuardHome.yaml`. AdGuard writes `querylog.json` only when its
in-memory buffer of `size_memory` queries fills, with no timer, so at the default of 1000 Loki
received the log in roughly hourly batches. `0` means a buffer of one, so Alloy ships each line
within seconds, at the cost of one small file append per DNS query.

The setting is not in the AdGuard UI or API, and AdGuard rewrites `AdGuardHome.yaml`. To change
it, stop the add-on (slug `a0d7b954_adguard`), edit
`/mnt/data/supervisor/apps/data/a0d7b954_adguard/adguard/AdGuardHome.yaml`, then start the
add-on.

## Profiles

`pyroscope.scrape "alloy"` scrapes Alloy's own pprof endpoints on `localhost:12345` and
`pyroscope.write` sends the profiles to Grafana Cloud Profiles, so you can see where Alloy spends
CPU and memory without capturing a profile by hand. The profiles carry `service_name="alloy"`,
`job="integrations/alloy"` and the host as `instance`. The endpoint comes from the stack lookup,
like the metrics and logs endpoints. The following command shows the CPU flame graph for the last
hour:

```sh
gcx profiles query -d grafanacloud-profiles '{service_name="alloy"}' \
  --profile-type process_cpu:cpu:nanoseconds:cpu:nanoseconds --since 1h
```

### Home Assistant profiles

The [`ha-pyroscope`](https://github.com/tomwilkie/ha-pyroscope) integration, installed through
HACS, runs the Pyroscope Python SDK inside Home Assistant Core. It pushes to
`pyroscope.receive_http "homeassistant"` on `http://localhost:4040` with no credentials, and
Alloy forwards the profiles through `pyroscope.write`, so the Grafana Cloud token stays in
`.env` and Home Assistant holds none. The profiles carry `service_name="homeassistant"` and an
`ha_version` tag. To see them, run the command above with `{service_name="homeassistant"}`.

- **Both receiver listeners bind to `127.0.0.1`.** The receiver has no auth, and Alloy runs on the host network, so a wildcard bind would let any LAN client push profiles. The `grpc` block is there because the gRPC listener otherwise binds `[::]` on a random port.
- **Change the sample rate under the integration's Configure.** Saving restarts the profiler. It defaults to 100 Hz.
- **Profiling is in-process, not eBPF.** `pyroscope.ebpf` cannot start on HAOS, because the kernel is built without syscall tracepoints (`CONFIG_FTRACE_SYSCALLS`). The [2026-10-29 entry](history.md#2026-10-29-ebpf-profiling-ruled-out) in history.md records the attempt.

The cAdvisor exporter has `disk` in `disabled_metrics`. cAdvisor collects disk usage by walking
every container's filesystem once a minute, which took about half of Alloy's CPU, and Alloy
exposes no setting for that interval. Without it, the `Disk usage`, `Filesystem Utilisation` and
`Inode Utilisation` panels on `docker-container-overview` are empty. The read and write panels
come from `diskIO`, which stays on.

## Environment variables

`make .env` writes `observability/.env` from a 1Password Environment with `op environment read`,
so the [1Password CLI](https://developer.1password.com/docs/cli/) must be signed in. `make up`
runs it when `.env` is missing, but never refreshes an existing file, so after you rotate a
secret, delete `.env` and run `make up` again. To set the values by hand instead, copy
`observability/.env.example` to `observability/.env` and set the following:

| Variable | Description |
|---|---|
| `STACK_NAME` | Grafana Cloud stack slug |
| `ACCESS_TOKEN` | `glc_…` token that can write metrics, logs and profiles |
| `HASS_METRICS_TOKEN` | Long-lived Home Assistant token for scraping `/api/prometheus` |

## Deployment

Run the following targets from the `observability/` directory. They act on the HAOS host over
SSH as `root@homeassistant.local`:

| Target | Action |
|---|---|
| `make deploy` | `push` then `up` |
| `make push` | Create `/homeassistant/alloy/` on the host and upload `alloy/config.alloy` |
| `make up` | `docker compose up -d`, after `make .env` if `.env` is missing |
| `make .env` | Write `.env` from the 1Password Environment |
| `make down` | `docker compose down` |
| `make restart` | `docker compose restart alloy` |
| `make logs` | Tail the last 100 lines of Alloy logs |
| `make ps` | Show container status |
| `make shell` | Open a shell inside the Alloy container |

`/homeassistant/alloy/config.alloy` is `/mnt/data/supervisor/homeassistant/alloy/config.alloy`
to the Supervisor. Alloy's persistent state is the Docker volume `alloy-data`.

### Upgrading Alloy

Renovate watches the `image:` tag in `docker-compose.yml` and opens a pull request when Grafana
releases a new Alloy, with the release notes in the PR body. Its config is `renovate.json` at the
repo root. Check the breaking changes against the components in `alloy/config.alloy`, merge, then
run `make up` to pull the new image, because merging alone changes nothing on the host. The
container runs at `--stability.level=experimental`, so changes to experimental features apply
too. After the restart, confirm the container is `healthy` with `make ps` and look for `level=warn`
in `make logs`: a deprecation warning there means the config needs a change before the function
is removed.

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
| `central-heating.json` | `eeasfye26sge8c` | Hive thermostat, water heater and boiler status, with boiler runtime and radiator, boiler and outside temperatures |

Select a single entity's series with `entity`, and aggregate `friendly_name` away with
`max by (__name__, entity)`. The exporter puts `friendly_name` in the labels, so a rename starts
a new series, and a stat or gauge panel shows the old and new series side by side until the old
one leaves the time range.

The zigbee2mqtt dashboards are tagged `zigbee2mqtt-integration` and link to each other. The
overview's device table links to `/d/zigbee2mqtt-device?var-device=<ieee_address>` by IEEE
address, not friendly name, so the link survives a device rename.

### Workflow

1. Diff the local file against Grafana, and fetch the live version first if they differ. Fetch with `jq .` and not `jq -S`, to keep the original key order and small diffs:

   ```bash
   diff <(jq -S . observability/dashboards/SLUG.json) <(gcx api /api/dashboards/uid/UID | jq -S .)
   gcx api /api/dashboards/uid/UID | jq . > observability/dashboards/SLUG.json
   ```

2. Edit `observability/dashboards/SLUG.json`.
3. Upload it. The stored file has `dashboard` and `meta` keys, and the upload endpoint wants `dashboard` and `overwrite`:

   ```bash
   jq '{dashboard: .dashboard, overwrite: true}' observability/dashboards/SLUG.json \
     | gcx api /api/dashboards/db -d @-
   ```

4. Snapshot the changed panels, as described in [_Verify a dashboard visually_](#verify-a-dashboard-visually).
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
- **Each call overwrites `<uid>-panel-<id>.png`,** so rename the file between renders when you compare two.
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
| Lines and band | `device_temperature`, `internal_temperature`, `battery_temperature`, `door_temperature` | A device's self-heat, which reads far above room temperature and compresses the axis |
| Band only | `outside` | The aircon outdoor probe, a real reading that distorts the room range |

The Norman shutter-motor temperatures stay in, because they track room temperature and give
per-window coverage. Radiators and towel heaters stay in the band, so radiator-only rooms get
one.

## Grafana alerting

Alert and recording rules are Grafana-managed and provisioned through
`/api/v1/provisioning/alert-rules`. Rules with a JSON file in `observability/alerts/` are
file-managed, and this section records the intent of the rest. Reference datasources by the
generic UIDs `grafanacloud-logs` and `grafanacloud-prom`, not by the datasource names, which
embed the stack slug. `X-Disable-Provenance` keeps a provisioned rule editable in the UI:

```bash
gcx alert rules list
gcx api /api/v1/provisioning/alert-rules
gcx api /api/v1/provisioning/alert-rules -X POST -H "X-Disable-Provenance: true" -d @rule.json
```

A log-derived alert is a recording rule, then a metric, then an alert: the recording rule runs a
LogQL metric query and writes the result to Prometheus, and the alert thresholds the metric.
`zigbee2mqtt_errors:rate15m` is an example.

Alerts reach a person through the `email receiver` contact point, which the default
notification policy routes to. The following rules keep delivery working:

- **Don't route to `grafana-default-email`.** Grafana ships it with the placeholder address `<example@email.com>`, so an alert sent there reaches nobody. It has an empty `uid`, so it cannot be updated in place: to change delivery, create a contact point and repoint the policy.
- **Change contact points and policies through the provisioning API** (`/api/v1/provisioning/contact-points` and `/api/v1/provisioning/policies`). Writing the whole Alertmanager config to `/api/alertmanager/grafana/config/api/v1/alerts` through `gcx` returns `404 data source not found`.
- **Test a contact point in the Grafana UI** (**Contact points**, **Test**). The legacy test endpoint returns `410`, and the replacement under `/apis/notifications.alerting.grafana.app/` rejects every request body tried.

The incident that found the placeholder is in [_Alerts never delivered_](history.md#2026-06-25-alerts-never-delivered).

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

- **`up == 0` alone is not enough.** A target that was never discovered has no `up` series. Each `label_replace(vector(0), …)` line supplies a `0` for an expected job, and `or` keeps it only when the job has no real series.
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

The U5G Max's cellular modem (a Sierra Wireless EM9291) hangs and reboots itself and keeps no
crash dump. The rule counts those resets while firmware fixes are tried, from two independent
signatures:

- **The U5G's own log lines.** `schedule syserr_worker` is the kernel seeing the modem reset, and `Modem disconnect detected` is the U5G's modem daemon losing it. Both carry the `U5G-Max-<version>` hostname, so the match survived the 7.5.3 to 8.0.2 upgrade and survives the next unless the messages change.
- **The UDM's failover monitor marking the 5G WAN (`gre1`) down.** It does not depend on the U5G's firmware or logging, and it also catches 5G outages that are not modem resets.

To read the reset history further back than Loki's 30 days, copy the U5G's own logs with
`scripts/unifi-ssh device 192.168.4.34` (see [access-home-assistant.md](access-home-assistant.md#unifi-ssh)):
`/var/log/uiwwand-atd.log*` records every reset as `active AT device removed`, and
`/var/log/uiwwand-signal.log*` records serving-cell changes and signal samples, for about the
last five days.

The investigation into the resets is in
[_U5G Max modem resets_](history.md#2026-10-01-u5g-max-modem-resets) in `history.md`.

### IOT DNAT redirect tripwire

The tripwire detects the removal of the UDM's DNS and NTP redirects described in
[_DNAT redirect_](network-security.md#dnat-redirect). Without the redirect, IOT port 53 and port
123 traffic hits the logged BLOCK rules, which otherwise stay at zero.

| Rule (folder `Unifi`) | Type | Definition |
|---|---|---|
| `iot_dnat_tripwire` | Recording rule, writes `iot_dnat_block_hits:count5m` | `sum(count_over_time({log_type="firewall", rule=~"Block IOT (DNS\|NTP) to Internet"} \|~ "DPT=(53\|123) " [5m])) or vector(0)` |
| `IOT DNAT redirect removed` | Alert | `iot_dnat_block_hits:count5m > 0`, `for: 5m`, to the email contact point |

- **The `DPT=(53|123)` line filter is required.** `Block IOT DNS to Internet` also matches DNS over TLS on port 853, which the redirect cannot rewrite, so port 853 hits are not drift.
- **`or vector(0)` keeps the series present at 0,** so the alert always has data.
- **The remediation is in the alert annotation:** run `apply.sh`, as described in [_Persistence_](network-security.md#persistence).
