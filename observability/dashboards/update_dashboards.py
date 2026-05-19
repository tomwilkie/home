#!/usr/bin/env python3
"""Update Docker Grafana dashboards with expanded cAdvisor metrics."""

import copy
import json
import subprocess
import sys

PROM_DS = {"type": "prometheus", "uid": "${prometheus_datasource}"}
FOLDER_ID = 30

# ---------------------------------------------------------------------------
# Grafana API helpers
# ---------------------------------------------------------------------------

def gcx_get(path):
    result = subprocess.run(["gcx", "api", path], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR fetching {path}:", result.stderr, file=sys.stderr)
        sys.exit(1)
    lines = result.stdout.split("\n")
    # gcx sometimes emits a "hint: ..." prefix line before JSON
    json_start = next(
        (i for i, l in enumerate(lines) if l.strip().startswith("{")),
        0,
    )
    return json.loads("\n".join(lines[json_start:]))


def gcx_post(payload):
    body = json.dumps(payload)
    # Use -d @- to read request body from stdin (implies POST)
    result = subprocess.run(
        ["gcx", "api", "/api/dashboards/db", "-d", "@-"],
        input=body,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("ERROR posting dashboard:", result.stderr, file=sys.stderr)
        print("stdout:", result.stdout[:500], file=sys.stderr)
        sys.exit(1)
    lines = result.stdout.split("\n")
    json_start = next(
        (i for i, l in enumerate(lines) if l.strip().startswith("{")),
        0,
    )
    return json.loads("\n".join(lines[json_start:]))


def load_local_dashboard(path):
    """Load a local JSON file and return only the dashboard object (strip meta).

    Handles files that are missing the leading '{' (a quirk of hass-cli yaml export
    and the gcx download format).
    """
    with open(path) as f:
        content = f.read()

    # Some files are missing the outer opening brace — detect and repair.
    stripped = content.strip()
    if not stripped.startswith("{"):
        content = "{" + content

    try:
        raw = json.loads(content)
    except json.JSONDecodeError:
        # Fall back: try stripping and wrapping
        raw = json.loads("{" + stripped + "}")

    if "dashboard" in raw:
        return copy.deepcopy(raw["dashboard"])
    return copy.deepcopy(raw)


def save_local_dashboard(path, dashboard_obj, meta=None):
    """Save dashboard object (wrapped with meta if provided) back to disk."""
    if meta is not None:
        out = {"dashboard": dashboard_obj, "meta": meta}
    else:
        out = {"dashboard": dashboard_obj}
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")


def push_dashboard(dashboard_obj, overwrite=True):
    """POST a dashboard to Grafana. Strips 'id' but keeps uid/version."""
    d = copy.deepcopy(dashboard_obj)
    d.pop("id", None)
    payload = {
        "dashboard": d,
        "overwrite": overwrite,
        "folderId": FOLDER_ID,
        "folderUid": "integration---docker",
    }
    return gcx_post(payload)


# ---------------------------------------------------------------------------
# Panel-ID counter (global monotonic counter for the script run)
# ---------------------------------------------------------------------------

_panel_id_counter = 1000  # start above any existing IDs to avoid collision


def next_panel_id():
    global _panel_id_counter
    _panel_id_counter += 1
    return _panel_id_counter


# ---------------------------------------------------------------------------
# Layout helper
# ---------------------------------------------------------------------------

class Layout:
    """Simple top-to-bottom layout manager that tracks the current y position."""

    def __init__(self):
        self.y = 0

    def place(self, panel, h=None, w=24, x=0):
        """Assign gridPos to panel and advance y. Returns panel."""
        if h is None:
            # infer from type
            t = panel.get("type", "")
            h = {"stat": 3, "gauge": 6, "timeseries": 8, "text": 3, "table": 10, "row": 1}.get(t, 6)
        panel["gridPos"] = {"h": h, "w": w, "x": x, "y": self.y}
        self.y += h
        return panel

    def row(self, h=1):
        """Advance y by one row height (used after placing a row panel)."""
        # row panels advance y by 1 (already done by place), children start at current y
        pass


# ---------------------------------------------------------------------------
# Panel construction helpers
# ---------------------------------------------------------------------------

def _std_thresholds(values=None):
    """Standard green/yellow/red thresholds. values = [(color, value), ...]"""
    if values is None:
        values = [("green", 0), ("yellow", 70), ("red", 90)]
    return {
        "mode": "absolute",
        "steps": [{"color": c, "value": v} for c, v in values],
    }


def _target(expr, ref="A", instant=True, legend="", extra=None):
    t = {
        "datasource": copy.deepcopy(PROM_DS),
        "expr": expr,
        "instant": instant,
        "legendFormat": legend,
        "refId": ref,
    }
    if not instant:
        t["range"] = True
    if extra:
        t.update(extra)
    return t


def make_text(content, panel_id=None):
    return {
        "type": "text",
        "title": "",
        "id": panel_id or next_panel_id(),
        "options": {
            "mode": "markdown",
            "content": content,
        },
        "targets": [],
    }


def make_stat(
    title,
    expr,
    unit,
    description,
    thresholds=None,
    instant=True,
    ref="A",
    value_mappings=None,
    display_name=None,
    reduce_field=None,
    panel_id=None,
):
    if thresholds is None:
        thresholds = _std_thresholds([("green", 0), ("yellow", 70), ("red", 90)])
    defaults = {
        "unit": unit,
        "thresholds": thresholds,
        "color": {"mode": "thresholds"},
    }
    if display_name:
        defaults["displayName"] = display_name
    if value_mappings:
        defaults["mappings"] = value_mappings

    reduce_opts = {"calcs": ["lastNotNull"], "fields": "", "values": False}
    if reduce_field:
        reduce_opts["fields"] = reduce_field

    panel = {
        "type": "stat",
        "title": title,
        "description": description,
        "id": panel_id or next_panel_id(),
        "datasource": copy.deepcopy(PROM_DS),
        "fieldConfig": {
            "defaults": defaults,
        },
        "options": {
            "reduceOptions": reduce_opts,
            "colorMode": "background",
            "graphMode": "none",
            "justifyMode": "auto",
            "orientation": "auto",
            "textMode": "auto",
            "wideLayout": True,
        },
        "targets": [_target(expr, ref=ref, instant=instant)],
    }
    return panel


def make_timeseries(
    title,
    targets,
    unit,
    description,
    stacked=False,
    panel_id=None,
):
    fill = 20 if stacked else 10
    custom = {
        "fillOpacity": fill,
        "drawStyle": "line",
        "lineInterpolation": "smooth",
        "lineWidth": 2,
        "showPoints": "never",
        "axisBorderShow": False,
        "axisCenteredZero": False,
        "axisColorMode": "text",
        "axisLabel": "",
        "axisPlacement": "auto",
        "barAlignment": 0,
        "barWidthFactor": 0.6,
        "gradientMode": "opacity",
        "hideFrom": {"legend": False, "tooltip": False, "viz": False},
        "insertNulls": False,
        "pointSize": 5,
        "scaleDistribution": {"type": "linear"},
        "showValues": False,
        "spanNulls": False,
        "thresholdsStyle": {"mode": "off"},
    }
    if stacked:
        custom["stacking"] = {"mode": "normal", "group": "A"}
    else:
        custom["stacking"] = {"mode": "none", "group": "A"}

    panel = {
        "type": "timeseries",
        "title": title,
        "description": description,
        "id": panel_id or next_panel_id(),
        "datasource": copy.deepcopy(PROM_DS),
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "custom": custom,
                "min": 0,
                "thresholds": _std_thresholds([("green", 0), ("red", 80)]),
                "color": {"mode": "palette-classic"},
            }
        },
        "options": {
            "legend": {
                "calcs": [],
                "displayMode": "list",
                "placement": "bottom",
                "showLegend": True,
            },
            "tooltip": {"hideZeros": False, "mode": "multi", "sort": "desc"},
        },
        "targets": targets,
    }
    return panel


def make_gauge(
    title,
    expr,
    unit,
    description,
    thresholds=None,
    ref="A",
    min_val=0,
    max_val=100,
    panel_id=None,
):
    if thresholds is None:
        thresholds = _std_thresholds([("green", 0), ("yellow", 80), ("red", 95)])
    panel = {
        "type": "gauge",
        "title": title,
        "description": description,
        "id": panel_id or next_panel_id(),
        "datasource": copy.deepcopy(PROM_DS),
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "min": min_val,
                "max": max_val,
                "thresholds": thresholds,
                "color": {"mode": "thresholds"},
            }
        },
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "orientation": "auto",
            "showThresholdLabels": False,
            "showThresholdMarkers": True,
        },
        "targets": [_target(expr, ref=ref, instant=True)],
    }
    return panel


def make_row(title, collapsed=False, panels=None, panel_id=None):
    return {
        "type": "row",
        "title": title,
        "collapsed": collapsed,
        "panels": panels or [],
        "id": panel_id or next_panel_id(),
    }


def make_table(title, description, targets, transformations, overrides, panel_id=None):
    return {
        "type": "table",
        "title": title,
        "description": description,
        "id": panel_id or next_panel_id(),
        "datasource": copy.deepcopy(PROM_DS),
        "fieldConfig": {
            "defaults": {
                "custom": {
                    "align": "left",
                    "cellOptions": {"type": "auto"},
                    "filterable": True,
                    "footer": {"reducers": []},
                    "inspect": False,
                }
            },
            "overrides": overrides,
        },
        "options": {
            "cellHeight": "sm",
            "showHeader": True,
        },
        "targets": targets,
        "transformations": transformations,
    }


# ---------------------------------------------------------------------------
# Build Container Overview (uid: tog2fp8)
# ---------------------------------------------------------------------------

def build_container_overview(existing_dashboard):
    """Rebuild the Container Overview dashboard."""
    d = copy.deepcopy(existing_dashboard)
    # Keep all top-level metadata but rebuild panels
    d.pop("id", None)

    # Extract original panels keyed by id for reuse
    orig_panels = {p["id"]: p for p in d.get("panels", [])}

    # Also extract child panels from collapsed rows
    for p in d.get("panels", []):
        if p.get("type") == "row":
            for cp in p.get("panels", []):
                orig_panels[cp["id"]] = cp

    layout = Layout()
    panels = []

    # --- 1. Title panel (y=0) ---
    title_panel = make_text(
        "## 🐳 Docker - Container Overview\n\n"
        "Per-container drill-down showing CPU, memory, network, disk, "
        "and resource pressure for a single Docker container."
    )
    panels.append(layout.place(title_panel, h=3))

    # --- 2. Integration Status row (collapsed) ---
    # Keep existing 3 child panels from original row (id=33), add 2 new ones
    orig_integration_row = orig_panels.get(33, {})
    orig_integration_children = list(orig_integration_row.get("panels", []))

    cadvisor_version_stat = make_stat(
        title="cAdvisor Version",
        expr='cadvisor_version_info{job="$job", instance="$instance"}',
        unit="string",
        description="Version of cAdvisor running on this host.",
        display_name="${__field.labels.version}",
        thresholds=_std_thresholds([("green", 0)]),
        reduce_field="",
    )
    cadvisor_version_stat["options"]["reduceOptions"]["values"] = True
    cadvisor_version_stat["options"]["reduceOptions"]["fields"] = ""
    cadvisor_version_stat["options"]["textMode"] = "name"

    scrape_errors_stat = make_stat(
        title="Scrape Errors",
        expr='container_scrape_error{job="$job", instance="$instance", name="$name"}',
        unit="short",
        description="1 if cAdvisor encountered errors scraping this container.",
        thresholds=_std_thresholds([("green", 0), ("red", 1)]),
    )

    # Assign relative gridPos for children in collapsed row
    child_y = 1
    for i, cp in enumerate(orig_integration_children):
        cp = copy.deepcopy(cp)
        if "gridPos" not in cp:
            cp["gridPos"] = {"h": 2, "w": 8, "x": (i % 3) * 8, "y": child_y}
        panels_in_row_count = len(orig_integration_children)
        _ = cp  # just keep as-is

    # Set gridPos on new children
    n = len(orig_integration_children)
    cadvisor_version_stat["gridPos"] = {"h": 3, "w": 8, "x": (n % 3) * 8, "y": child_y}
    scrape_errors_stat["gridPos"] = {"h": 3, "w": 8, "x": ((n + 1) % 3) * 8, "y": child_y}

    integration_children = [copy.deepcopy(cp) for cp in orig_integration_children] + [
        cadvisor_version_stat,
        scrape_errors_stat,
    ]
    integration_row = make_row("Integration Status", collapsed=True, panels=integration_children)
    panels.append(layout.place(integration_row, h=1))

    # --- 3. Overview row ---
    overview_row = make_row("Overview")
    panels.append(layout.place(overview_row, h=1))

    # Keep existing Image (id=20), Start Time (id=21), Last Seen (id=3) panels
    image_panel = copy.deepcopy(orig_panels.get(20, {}))
    image_panel["gridPos"] = {"h": 3, "w": 8, "x": 0, "y": layout.y}
    panels.append(image_panel)

    start_panel = copy.deepcopy(orig_panels.get(21, {}))
    start_panel["gridPos"] = {"h": 3, "w": 8, "x": 8, "y": layout.y}
    panels.append(start_panel)

    last_seen_panel = copy.deepcopy(orig_panels.get(3, {}))
    last_seen_panel["gridPos"] = {"h": 3, "w": 8, "x": 16, "y": layout.y}
    panels.append(last_seen_panel)

    layout.y += 3

    # Keep existing labels table (id=32)
    labels_table = copy.deepcopy(orig_panels.get(32, {}))
    labels_table["gridPos"] = {"h": 4, "w": 24, "x": 0, "y": layout.y}
    panels.append(labels_table)
    layout.y += 4

    # Health State stat (new)
    health_state = make_stat(
        title="Health State",
        expr='container_health_state{job="$job", instance="$instance", name="$name"}',
        unit="short",
        description=(
            "Result of the container's Docker HEALTHCHECK. "
            "Only populated for containers that define a health check."
        ),
        thresholds=_std_thresholds([("green", 0)]),
        value_mappings=[
            {
                "type": "value",
                "options": {
                    "1": {"text": "Healthy", "color": "green", "index": 0},
                    "0": {"text": "Unhealthy", "color": "red", "index": 1},
                },
            }
        ],
    )
    health_state["gridPos"] = {"h": 3, "w": 8, "x": 0, "y": layout.y}
    panels.append(health_state)

    # Resource Limits table (new, instant join)
    resource_limits_targets = [
        _target(
            'container_spec_cpu_shares{job="$job", instance="$instance", name="$name"}',
            ref="A", instant=True, legend="CPU Shares",
            extra={"format": "table", "range": False},
        ),
        _target(
            'container_spec_memory_limit_bytes{job="$job", instance="$instance", name="$name"}',
            ref="B", instant=True, legend="Memory Limit",
            extra={"format": "table", "range": False},
        ),
        _target(
            'container_spec_memory_reservation_limit_bytes{job="$job", instance="$instance", name="$name"}',
            ref="C", instant=True, legend="Memory Reservation",
            extra={"format": "table", "range": False},
        ),
        _target(
            'container_spec_memory_swap_limit_bytes{job="$job", instance="$instance", name="$name"}',
            ref="D", instant=True, legend="Swap Limit",
            extra={"format": "table", "range": False},
        ),
    ]
    resource_limits_transforms = [
        {"id": "timeSeriesTable", "options": {
            "A": {"stat": "lastNotNull", "timeField": "Time"},
            "B": {"stat": "lastNotNull", "timeField": "Time"},
            "C": {"stat": "lastNotNull", "timeField": "Time"},
            "D": {"stat": "lastNotNull", "timeField": "Time"},
        }},
        {"id": "joinByField", "options": {"byField": "name", "mode": "outer"}},
        {"id": "organize", "options": {
            "excludeByName": {},
            "includeByName": {},
            "indexByName": {},
            "renameByName": {
                "Trend #A": "cpu_shares",
                "Trend #B": "memory_limit",
                "Trend #C": "memory_reservation",
                "Trend #D": "swap_limit",
            },
        }},
    ]
    resource_limits_overrides = [
        {"matcher": {"id": "byName", "options": "memory_limit"},
         "properties": [{"id": "unit", "value": "decbytes"}, {"id": "displayName", "value": "Memory Limit"}]},
        {"matcher": {"id": "byName", "options": "memory_reservation"},
         "properties": [{"id": "unit", "value": "decbytes"}, {"id": "displayName", "value": "Memory Reservation"}]},
        {"matcher": {"id": "byName", "options": "swap_limit"},
         "properties": [{"id": "unit", "value": "decbytes"}, {"id": "displayName", "value": "Swap Limit"}]},
        {"matcher": {"id": "byName", "options": "cpu_shares"},
         "properties": [{"id": "displayName", "value": "CPU Shares"}]},
    ]
    resource_limits_table = make_table(
        title="Resource Limits",
        description="Static resource limits configured on this container.",
        targets=resource_limits_targets,
        transformations=resource_limits_transforms,
        overrides=resource_limits_overrides,
    )
    resource_limits_table["gridPos"] = {"h": 5, "w": 16, "x": 8, "y": layout.y}
    panels.append(resource_limits_table)

    layout.y += 5

    # --- 4. Compute row ---
    compute_row = make_row("Compute")
    panels.append(layout.place(compute_row, h=1))

    # CPU gauge (keep existing id=28, fix unit/thresholds/description)
    cpu_gauge = copy.deepcopy(orig_panels.get(28, {}))
    cpu_gauge["description"] = "Instant CPU usage percentage for the selected container."
    if "fieldConfig" not in cpu_gauge:
        cpu_gauge["fieldConfig"] = {"defaults": {}}
    cpu_gauge["fieldConfig"]["defaults"]["unit"] = "percent"
    cpu_gauge["fieldConfig"]["defaults"]["thresholds"] = _std_thresholds(
        [("green", 0), ("yellow", 70), ("red", 90)]
    )
    cpu_gauge["gridPos"] = {"h": 8, "w": 5, "x": 0, "y": layout.y}
    panels.append(cpu_gauge)

    # CPU Usage User/System stacked timeseries (replaces original)
    cpu_ts = make_timeseries(
        title="CPU Usage — User / System",
        targets=[
            _target(
                'rate(container_cpu_user_seconds_total{job="$job", instance="$instance", name="$name"}[$__rate_interval]) * 100',
                ref="A", instant=False, legend="User",
            ),
            _target(
                'rate(container_cpu_system_seconds_total{job="$job", instance="$instance", name="$name"}[$__rate_interval]) * 100',
                ref="B", instant=False, legend="Kernel",
            ),
        ],
        unit="percent",
        description=(
            "Breakdown of CPU time in user space vs kernel space. "
            "High Kernel% suggests syscall-heavy or I/O-heavy workload."
        ),
        stacked=True,
    )
    for t in cpu_ts["targets"]:
        t["range"] = True
        t["instant"] = False
    cpu_ts["gridPos"] = {"h": 8, "w": 19, "x": 5, "y": layout.y}
    panels.append(cpu_ts)

    layout.y += 8

    # --- 5. Memory row ---
    memory_row = make_row("Memory")
    panels.append(layout.place(memory_row, h=1))

    # Working Set gauge
    ws_gauge = make_gauge(
        title="Working Set",
        expr='container_memory_working_set_bytes{job="$job", instance="$instance", name="$name"}',
        unit="decbytes",
        description="Non-reclaimable memory. This is what the OOM killer acts on.",
        thresholds=_std_thresholds([("green", 0), ("yellow", 80), ("red", 95)]),
        min_val=0,
        max_val=0,  # auto max
    )
    ws_gauge["fieldConfig"]["defaults"].pop("max", None)
    ws_gauge["gridPos"] = {"h": 8, "w": 5, "x": 0, "y": layout.y}
    panels.append(ws_gauge)

    # Memory Breakdown stacked timeseries
    mem_breakdown_ts = make_timeseries(
        title="Memory Breakdown",
        targets=[
            _target(
                'container_memory_working_set_bytes{job="$job", instance="$instance", name="$name"}',
                ref="A", instant=False, legend="Working Set",
            ),
            _target(
                'container_memory_rss{job="$job", instance="$instance", name="$name"}',
                ref="B", instant=False, legend="RSS",
            ),
            _target(
                'container_memory_cache{job="$job", instance="$instance", name="$name"}',
                ref="C", instant=False, legend="Cache",
            ),
        ],
        unit="decbytes",
        description=(
            "Working set = RSS + non-reclaimable cache. "
            "Page cache is normal to be high — it can be reclaimed under pressure."
        ),
        stacked=True,
    )
    for t in mem_breakdown_ts["targets"]:
        t["range"] = True
        t["instant"] = False
    mem_breakdown_ts["gridPos"] = {"h": 8, "w": 19, "x": 5, "y": layout.y}
    panels.append(mem_breakdown_ts)

    layout.y += 8

    # Swap Usage timeseries
    swap_ts = make_timeseries(
        title="Swap Usage",
        targets=[
            _target(
                'container_memory_swap{job="$job", instance="$instance", name="$name"}',
                ref="A", instant=False, legend="Swap",
            ),
        ],
        unit="decbytes",
        description=(
            "Container swap usage. Non-zero values indicate the container "
            "has exceeded its RAM budget."
        ),
    )
    for t in swap_ts["targets"]:
        t["range"] = True
        t["instant"] = False
    swap_ts["gridPos"] = {"h": 8, "w": 12, "x": 0, "y": layout.y}
    panels.append(swap_ts)

    # OOM Events stat
    oom_events_stat = make_stat(
        title="OOM Events",
        expr='increase(container_oom_events_total{job="$job", instance="$instance", name="$name"}[$__range])',
        unit="short",
        description=(
            "OOM kills in the selected time range. "
            "Any kill means a process was forcibly terminated due to memory exhaustion."
        ),
        thresholds=_std_thresholds([("green", 0), ("red", 1)]),
    )
    oom_events_stat["gridPos"] = {"h": 4, "w": 6, "x": 12, "y": layout.y}
    panels.append(oom_events_stat)

    # OOM Rate timeseries
    oom_rate_ts = make_timeseries(
        title="OOM Rate",
        targets=[
            _target(
                'rate(container_oom_events_total{job="$job", instance="$instance", name="$name"}[$__rate_interval])',
                ref="A", instant=False, legend="OOM Rate",
            ),
        ],
        unit="short",
        description="Rate of OOM kill events over time.",
    )
    for t in oom_rate_ts["targets"]:
        t["range"] = True
        t["instant"] = False
    oom_rate_ts["gridPos"] = {"h": 4, "w": 6, "x": 18, "y": layout.y}
    panels.append(oom_rate_ts)

    layout.y += 8

    # --- 6. Network row (fix existing panels) ---
    network_row = make_row("Network")
    panels.append(layout.place(network_row, h=1))

    # Network Traffic timeseries (fix: unit binBps, legend RX/TX, description)
    net_traffic = make_timeseries(
        title="Network Traffic",
        targets=[
            _target(
                'rate(container_network_receive_bytes_total{job="$job", instance="$instance", name="$name"}[$__rate_interval])',
                ref="A", instant=False, legend="RX",
            ),
            _target(
                'rate(container_network_transmit_bytes_total{job="$job", instance="$instance", name="$name"}[$__rate_interval])',
                ref="B", instant=False, legend="TX",
            ),
        ],
        unit="binBps",
        description="Bytes received and transmitted per second.",
    )
    for t in net_traffic["targets"]:
        t["range"] = True
        t["instant"] = False
    net_traffic["gridPos"] = {"h": 8, "w": 12, "x": 0, "y": layout.y}
    panels.append(net_traffic)

    # Network Errors & Drops (fix: unit short, description)
    # Keep original queries but with new description
    orig_net_errors = copy.deepcopy(orig_panels.get(12, {}))
    orig_net_errors["description"] = (
        "Rate of dropped packets and errors. "
        "Sustained drops indicate network saturation or misconfiguration."
    )
    orig_net_errors["fieldConfig"]["defaults"]["unit"] = "short"
    orig_net_errors["gridPos"] = {"h": 8, "w": 12, "x": 12, "y": layout.y}
    panels.append(orig_net_errors)

    layout.y += 8

    # --- 7. Storage row ---
    storage_row = make_row("Storage")
    panels.append(layout.place(storage_row, h=1))

    # Disk Usage timeseries (fix unit to decbytes, description)
    orig_disk_usage = copy.deepcopy(orig_panels.get(14, {}))
    orig_disk_usage["description"] = (
        "Bytes consumed by this container on its writable filesystem layer."
    )
    orig_disk_usage["fieldConfig"]["defaults"]["unit"] = "decbytes"
    # Remove the override that was setting unit via refId if it exists
    overrides_filtered = [
        ov for ov in orig_disk_usage.get("fieldConfig", {}).get("overrides", [])
        if ov.get("matcher", {}).get("options") != "Disk space usage"
    ]
    orig_disk_usage["fieldConfig"]["overrides"] = overrides_filtered
    orig_disk_usage["gridPos"] = {"h": 8, "w": 8, "x": 0, "y": layout.y}
    panels.append(orig_disk_usage)

    # Disk I/O bytes timeseries (replace ops queries with bytes)
    disk_io_ts = make_timeseries(
        title="Disk I/O",
        targets=[
            _target(
                'rate(container_fs_reads_bytes_total{job="$job", instance="$instance", name="$name"}[$__rate_interval])',
                ref="A", instant=False, legend="Read",
            ),
            _target(
                'rate(container_fs_writes_bytes_total{job="$job", instance="$instance", name="$name"}[$__rate_interval])',
                ref="B", instant=False, legend="Write",
            ),
        ],
        unit="binBps",
        description="Read and write throughput in bytes per second.",
    )
    for t in disk_io_ts["targets"]:
        t["range"] = True
        t["instant"] = False
    disk_io_ts["gridPos"] = {"h": 8, "w": 8, "x": 8, "y": layout.y}
    panels.append(disk_io_ts)

    # Filesystem Utilisation gauge
    fs_util_gauge = make_gauge(
        title="Filesystem Utilisation",
        expr=(
            'container_fs_usage_bytes{job="$job", instance="$instance", name="$name"} '
            '/ (container_fs_limit_bytes{job="$job", instance="$instance", name="$name"} > 0) * 100'
        ),
        unit="percent",
        description=(
            "Used bytes as a percentage of the filesystem limit. "
            "Values near 100% will cause write failures."
        ),
        thresholds=_std_thresholds([("green", 0), ("yellow", 80), ("red", 95)]),
        min_val=0,
        max_val=100,
    )
    fs_util_gauge["gridPos"] = {"h": 4, "w": 4, "x": 16, "y": layout.y}
    panels.append(fs_util_gauge)

    # Inode Utilisation gauge
    inode_util_gauge = make_gauge(
        title="Inode Utilisation",
        expr=(
            '(container_fs_inodes_total{job="$job", instance="$instance", name="$name"} '
            '- container_fs_inodes_free{job="$job", instance="$instance", name="$name"}) '
            '/ container_fs_inodes_total{job="$job", instance="$instance", name="$name"} * 100'
        ),
        unit="percent",
        description=(
            "Used inodes as a percentage of total. "
            "Inode exhaustion causes 'no space left' errors even when disk bytes are available."
        ),
        thresholds=_std_thresholds([("green", 0), ("yellow", 80), ("red", 95)]),
        min_val=0,
        max_val=100,
    )
    inode_util_gauge["gridPos"] = {"h": 4, "w": 4, "x": 20, "y": layout.y}
    panels.append(inode_util_gauge)

    layout.y += 8

    # --- 8. Resource Pressure row ---
    pressure_row = make_row("Resource Pressure")
    panels.append(layout.place(pressure_row, h=1))

    # CPU Pressure
    cpu_pressure_ts = make_timeseries(
        title="CPU Pressure",
        targets=[
            _target(
                'rate(container_pressure_cpu_waiting_seconds_total{job="$job", instance="$instance", name="$name"}[$__rate_interval]) * 100',
                ref="A", instant=False, legend="Waiting",
            ),
            _target(
                'rate(container_pressure_cpu_stalled_seconds_total{job="$job", instance="$instance", name="$name"}[$__rate_interval]) * 100',
                ref="B", instant=False, legend="Stalled",
            ),
        ],
        unit="percent",
        description=(
            "% of time tasks waited for (Waiting) or were completely blocked by (Stalled) CPU. "
            "Stalled > 0 = severe CPU starvation."
        ),
    )
    for t in cpu_pressure_ts["targets"]:
        t["range"] = True
        t["instant"] = False
    cpu_pressure_ts["gridPos"] = {"h": 8, "w": 8, "x": 0, "y": layout.y}
    panels.append(cpu_pressure_ts)

    # I/O Pressure
    io_pressure_ts = make_timeseries(
        title="I/O Pressure",
        targets=[
            _target(
                'rate(container_pressure_io_waiting_seconds_total{job="$job", instance="$instance", name="$name"}[$__rate_interval]) * 100',
                ref="A", instant=False, legend="Waiting",
            ),
            _target(
                'rate(container_pressure_io_stalled_seconds_total{job="$job", instance="$instance", name="$name"}[$__rate_interval]) * 100',
                ref="B", instant=False, legend="Stalled",
            ),
        ],
        unit="percent",
        description=(
            "% of time tasks waited on or were stalled by I/O. "
            "Sustained stalled values = disk bottleneck."
        ),
    )
    for t in io_pressure_ts["targets"]:
        t["range"] = True
        t["instant"] = False
    io_pressure_ts["gridPos"] = {"h": 8, "w": 8, "x": 8, "y": layout.y}
    panels.append(io_pressure_ts)

    # Memory Pressure
    mem_pressure_ts = make_timeseries(
        title="Memory Pressure",
        targets=[
            _target(
                'rate(container_pressure_memory_waiting_seconds_total{job="$job", instance="$instance", name="$name"}[$__rate_interval]) * 100',
                ref="A", instant=False, legend="Waiting",
            ),
            _target(
                'rate(container_pressure_memory_stalled_seconds_total{job="$job", instance="$instance", name="$name"}[$__rate_interval]) * 100',
                ref="B", instant=False, legend="Stalled",
            ),
        ],
        unit="percent",
        description=(
            "% of time tasks were waiting for or completely blocked by memory reclaim. "
            "Any stalled time is an OOM precursor."
        ),
    )
    for t in mem_pressure_ts["targets"]:
        t["range"] = True
        t["instant"] = False
    mem_pressure_ts["gridPos"] = {"h": 8, "w": 8, "x": 16, "y": layout.y}
    panels.append(mem_pressure_ts)

    layout.y += 8

    d["panels"] = panels
    return d


# ---------------------------------------------------------------------------
# Build Host Overview (uid: toj7b4l)
# ---------------------------------------------------------------------------

def build_host_overview(existing_dashboard):
    """Rebuild the Host Overview dashboard."""
    d = copy.deepcopy(existing_dashboard)
    d.pop("id", None)

    # Extract original panels
    orig_panels = {p["id"]: p for p in d.get("panels", [])}
    for p in d.get("panels", []):
        if p.get("type") == "row":
            for cp in p.get("panels", []):
                orig_panels[cp["id"]] = cp

    layout = Layout()
    panels = []

    # --- 1. Title panel ---
    title_panel = make_text(
        "## 🐳 Docker - Host Overview\n\n"
        "Aggregate resource usage across all containers on a single Docker host."
    )
    panels.append(layout.place(title_panel, h=3))

    # --- 2. Host Stats row ---
    host_stats_row = make_row("Host Stats")
    panels.append(layout.place(host_stats_row, h=1))

    stat_y = layout.y

    cpu_cores_stat = make_stat(
        title="CPU Cores",
        expr='machine_cpu_cores{job="$job", instance=~"$instance"}',
        unit="short",
        description="Logical CPU cores on this host.",
        thresholds=_std_thresholds([("green", 0)]),
    )
    cpu_cores_stat["gridPos"] = {"h": 3, "w": 4, "x": 0, "y": stat_y}
    panels.append(cpu_cores_stat)

    total_ram_stat = make_stat(
        title="Total RAM",
        expr='machine_memory_bytes{job="$job", instance=~"$instance"}',
        unit="decbytes",
        description="Total physical memory on this host.",
        thresholds=_std_thresholds([("green", 0)]),
    )
    total_ram_stat["gridPos"] = {"h": 3, "w": 4, "x": 4, "y": stat_y}
    panels.append(total_ram_stat)

    agg_cpu_stat = make_stat(
        title="Aggregate CPU %",
        expr=(
            'sum(rate(container_cpu_usage_seconds_total{job="$job", instance=~"$instance", name!=""}[$__rate_interval])) '
            '/ scalar(machine_cpu_cores{job="$job", instance=~"$instance"}) * 100'
        ),
        unit="percent",
        description="Total CPU across all containers as % of host cores.",
        thresholds=_std_thresholds([("green", 0), ("yellow", 70), ("red", 90)]),
    )
    agg_cpu_stat["gridPos"] = {"h": 3, "w": 5, "x": 8, "y": stat_y}
    panels.append(agg_cpu_stat)

    mem_pct_stat = make_stat(
        title="Memory %",
        expr=(
            'sum(container_memory_working_set_bytes{job="$job", instance=~"$instance", name!=""}) '
            '/ scalar(machine_memory_bytes{job="$job", instance=~"$instance"}) * 100'
        ),
        unit="percent",
        description="Total working-set memory as % of host RAM.",
        thresholds=_std_thresholds([("green", 0), ("yellow", 80), ("red", 95)]),
    )
    mem_pct_stat["gridPos"] = {"h": 3, "w": 5, "x": 13, "y": stat_y}
    panels.append(mem_pct_stat)

    oom_stat = make_stat(
        title="OOM Events",
        expr='sum(increase(container_oom_events_total{job="$job", instance=~"$instance", name!=""}[$__range]))',
        unit="short",
        description="Total OOM kills across all containers in the time range.",
        thresholds=_std_thresholds([("green", 0), ("red", 1)]),
    )
    oom_stat["gridPos"] = {"h": 3, "w": 6, "x": 18, "y": stat_y}
    panels.append(oom_stat)

    layout.y = stat_y + 3

    # --- 3. Overview stat bar (keep existing id=2, update memory query + description) ---
    overview_stat = copy.deepcopy(orig_panels.get(2, {}))
    if overview_stat:
        # Fix memory target: replace container_memory_usage_bytes with working_set
        for t in overview_stat.get("targets", []):
            if "container_memory_usage_bytes" in t.get("expr", ""):
                t["expr"] = t["expr"].replace(
                    "container_memory_usage_bytes", "container_memory_working_set_bytes"
                )
                t["legendFormat"] = "Memory Usage"
        # Fix memory unit in overrides
        for ov in overview_stat.get("fieldConfig", {}).get("overrides", []):
            if ov.get("matcher", {}).get("options") == "Memory Usage":
                for prop in ov.get("properties", []):
                    if prop.get("id") == "unit":
                        prop["value"] = "decbytes"
        overview_stat["description"] = (
            "Non-reclaimable working-set memory across all containers."
        )
        overview_stat["gridPos"] = {"h": 4, "w": 24, "x": 0, "y": layout.y}
        panels.append(overview_stat)
        layout.y += 4

    # --- 4. Container table (keep existing id=3, update) ---
    container_table = copy.deepcopy(orig_panels.get(3, {}))
    if container_table:
        # Fix memory query in targets
        for t in container_table.get("targets", []):
            if "container_memory_usage_bytes" in t.get("expr", ""):
                t["expr"] = t["expr"].replace(
                    "container_memory_usage_bytes", "container_memory_working_set_bytes"
                )

        # Fix column overrides
        new_overrides = []
        for ov in container_table.get("fieldConfig", {}).get("overrides", []):
            opt = ov.get("matcher", {}).get("options", "")
            if opt == "memory":
                # Replace with updated properties
                ov = {
                    "matcher": {"id": "byName", "options": "memory"},
                    "properties": [
                        {"id": "displayName", "value": "Memory (WS)"},
                        {"id": "unit", "value": "decbytes"},
                        {"id": "cellOptions", "value": {"type": "sparkline"}},
                    ],
                }
            elif opt in ("network_receive", "network_transmit", "disk_read", "disk_write"):
                # Fix units to binBps and add sparkline
                new_props = []
                for prop in ov.get("properties", []):
                    if prop.get("id") == "unit":
                        prop = {"id": "unit", "value": "binBps"}
                    new_props.append(prop)
                # Ensure sparkline
                if not any(p.get("id") == "cellOptions" for p in new_props):
                    new_props.append({"id": "cellOptions", "value": {"type": "sparkline"}})
                display_map = {
                    "network_receive": "Net RX",
                    "network_transmit": "Net TX",
                    "disk_read": "Disk R",
                    "disk_write": "Disk W",
                }
                if opt in display_map:
                    # update displayName
                    for prop in new_props:
                        if prop.get("id") == "displayName":
                            prop["value"] = display_map[opt]
                ov = {"matcher": ov["matcher"], "properties": new_props}
            elif opt == "cpu":
                new_props = list(ov.get("properties", []))
                if not any(p.get("id") == "cellOptions" for p in new_props):
                    new_props.append({"id": "cellOptions", "value": {"type": "sparkline"}})
                ov = {"matcher": ov["matcher"], "properties": new_props}
            new_overrides.append(ov)

        # Ensure name column has a data link
        name_ov = next(
            (ov for ov in new_overrides if ov.get("matcher", {}).get("options") == "name"),
            None,
        )
        if name_ov is None:
            new_overrides.insert(0, {
                "matcher": {"id": "byName", "options": "name"},
                "properties": [
                    {"id": "displayName", "value": "Container Name"},
                    {"id": "links", "value": [{
                        "keepTime": True,
                        "targetBlank": False,
                        "title": "Docker - Container Overview",
                        "url": (
                            "/d/tog2fp8?var-prometheus_datasource=${prometheus_datasource}"
                            "&var-job=${job}&var-instance=${instance}&var-name=${__value.raw}"
                        ),
                    }]},
                ],
            })
        else:
            # Ensure data link is present
            links_prop = next(
                (p for p in name_ov.get("properties", []) if p.get("id") == "links"),
                None,
            )
            if links_prop is None:
                name_ov["properties"].append({
                    "id": "links",
                    "value": [{
                        "keepTime": True,
                        "targetBlank": False,
                        "title": "Docker - Container Overview",
                        "url": (
                            "/d/tog2fp8?var-prometheus_datasource=${prometheus_datasource}"
                            "&var-job=${job}&var-instance=${instance}&var-name=${__value.raw}"
                        ),
                    }],
                })

        container_table["fieldConfig"]["overrides"] = new_overrides
        container_table["description"] = (
            "All running containers with average resource usage. "
            "Click a container name to open the Container Overview."
        )
        container_table["gridPos"] = {"h": 11, "w": 24, "x": 0, "y": layout.y}
        panels.append(container_table)
        layout.y += 11

    # --- 5. Hardware Details row (collapsed) ---
    hw_children_y = 1

    phys_cores_stat = make_stat(
        title="Physical Cores",
        expr='machine_cpu_physical_cores{job="$job", instance=~"$instance"}',
        unit="short",
        description="Physical (non-hyperthreaded) CPU cores.",
        thresholds=_std_thresholds([("green", 0)]),
    )
    phys_cores_stat["gridPos"] = {"h": 3, "w": 6, "x": 0, "y": hw_children_y}

    cpu_sockets_stat = make_stat(
        title="CPU Sockets",
        expr='machine_cpu_sockets{job="$job", instance=~"$instance"}',
        unit="short",
        description="Number of physical CPU sockets.",
        thresholds=_std_thresholds([("green", 0)]),
    )
    cpu_sockets_stat["gridPos"] = {"h": 3, "w": 6, "x": 6, "y": hw_children_y}

    nvm_capacity_stat = make_stat(
        title="NVM Capacity",
        expr='machine_nvm_capacity{job="$job", instance=~"$instance"}',
        unit="decbytes",
        description="NVDIMM capacity, if present on this host.",
        thresholds=_std_thresholds([("green", 0)]),
    )
    nvm_capacity_stat["gridPos"] = {"h": 3, "w": 6, "x": 12, "y": hw_children_y}

    nvm_power_stat = make_stat(
        title="NVM Power Budget",
        expr='machine_nvm_avg_power_budget_watts{job="$job", instance=~"$instance"}',
        unit="watt",
        description="NVM average power budget in watts.",
        thresholds=_std_thresholds([("green", 0)]),
    )
    nvm_power_stat["gridPos"] = {"h": 3, "w": 6, "x": 18, "y": hw_children_y}

    hw_row = make_row(
        "Hardware Details",
        collapsed=True,
        panels=[phys_cores_stat, cpu_sockets_stat, nvm_capacity_stat, nvm_power_stat],
    )
    panels.append(layout.place(hw_row, h=1))

    # --- 6. Integration Status row (collapsed) ---
    int_children_y = 1

    cadvisor_version_host = make_stat(
        title="cAdvisor Version",
        expr='cadvisor_version_info{job="$job", instance=~"$instance"}',
        unit="string",
        description="cAdvisor version running on this host.",
        display_name="${__field.labels.version}",
        thresholds=_std_thresholds([("green", 0)]),
    )
    cadvisor_version_host["options"]["reduceOptions"]["values"] = True
    cadvisor_version_host["options"]["textMode"] = "name"
    cadvisor_version_host["gridPos"] = {"h": 3, "w": 8, "x": 0, "y": int_children_y}

    build_info_table = make_table(
        title="Build Info",
        description="cAdvisor build metadata.",
        targets=[
            _target(
                'cadvisor_build_info{job="$job", instance=~"$instance"}',
                ref="A", instant=True,
                extra={"format": "table"},
            )
        ],
        transformations=[],
        overrides=[],
    )
    build_info_table["gridPos"] = {"h": 5, "w": 8, "x": 8, "y": int_children_y}

    scrape_errors_host = make_stat(
        title="Scrape Errors",
        expr='machine_scrape_error{job="$job", instance=~"$instance"}',
        unit="short",
        description="1 if cAdvisor had errors collecting host metrics.",
        thresholds=_std_thresholds([("green", 0), ("red", 1)]),
    )
    scrape_errors_host["gridPos"] = {"h": 3, "w": 8, "x": 16, "y": int_children_y}

    integration_row_host = make_row(
        "Integration Status",
        collapsed=True,
        panels=[cadvisor_version_host, build_info_table, scrape_errors_host],
    )
    panels.append(layout.place(integration_row_host, h=1))

    d["panels"] = panels
    return d


# ---------------------------------------------------------------------------
# Build Cluster Overview (new, uid: docker-cluster-overview)
# ---------------------------------------------------------------------------

def build_cluster_overview(existing_container_overview):
    """Build the Cluster Overview dashboard from scratch."""
    # Base template vars from container overview
    layout = Layout()
    panels = []

    # --- 1. Title panel ---
    title_panel = make_text(
        "## 🐳 Docker - Cluster Overview\n\n"
        "Cross-host summary — one row per Docker host — for comparing CPU, memory, "
        "network, and disk usage across all instances."
    )
    panels.append(layout.place(title_panel, h=3))

    # --- 2. Overview stat bar ---
    stat_y = layout.y

    hosts_stat = make_stat(
        title="Hosts",
        expr='count(count by (instance) (container_last_seen{job=~"$job", name!=""}))',
        unit="short",
        description="Distinct Docker hosts reporting metrics.",
        thresholds=_std_thresholds([("green", 0)]),
    )
    hosts_stat["gridPos"] = {"h": 3, "w": 4, "x": 0, "y": stat_y}
    panels.append(hosts_stat)

    containers_stat = make_stat(
        title="Containers",
        expr='count(count by (instance, name) (container_last_seen{job=~"$job", name!=""}))',
        unit="short",
        description="Total containers across all hosts.",
        thresholds=_std_thresholds([("green", 0)]),
    )
    containers_stat["gridPos"] = {"h": 3, "w": 4, "x": 4, "y": stat_y}
    panels.append(containers_stat)

    total_cpu_stat = make_stat(
        title="Total CPU %",
        expr='sum(rate(container_cpu_usage_seconds_total{job=~"$job", name!=""}[$__rate_interval])) * 100',
        unit="percent",
        description="Aggregate CPU across all containers and hosts.",
        thresholds=_std_thresholds([("green", 0), ("yellow", 70), ("red", 90)]),
    )
    total_cpu_stat["gridPos"] = {"h": 3, "w": 4, "x": 8, "y": stat_y}
    panels.append(total_cpu_stat)

    total_mem_stat = make_stat(
        title="Total Memory",
        expr='sum(container_memory_working_set_bytes{job=~"$job", name!=""})',
        unit="decbytes",
        description="Total working-set memory across all containers.",
        thresholds=_std_thresholds([("green", 0)]),
    )
    total_mem_stat["gridPos"] = {"h": 3, "w": 4, "x": 12, "y": stat_y}
    panels.append(total_mem_stat)

    total_net_stat = make_stat(
        title="Total Network",
        expr=(
            'sum(rate(container_network_receive_bytes_total{job=~"$job",name!=""}[$__rate_interval])) '
            '+ sum(rate(container_network_transmit_bytes_total{job=~"$job",name!=""}[$__rate_interval]))'
        ),
        unit="binBps",
        description="Combined inbound + outbound traffic.",
        thresholds=_std_thresholds([("green", 0)]),
    )
    total_net_stat["gridPos"] = {"h": 3, "w": 4, "x": 16, "y": stat_y}
    panels.append(total_net_stat)

    total_disk_stat = make_stat(
        title="Total Disk I/O",
        expr=(
            'sum(rate(container_fs_reads_bytes_total{job=~"$job",name!=""}[$__rate_interval])) '
            '+ sum(rate(container_fs_writes_bytes_total{job=~"$job",name!=""}[$__rate_interval]))'
        ),
        unit="binBps",
        description="Combined read + write throughput.",
        thresholds=_std_thresholds([("green", 0)]),
    )
    total_disk_stat["gridPos"] = {"h": 3, "w": 4, "x": 20, "y": stat_y}
    panels.append(total_disk_stat)

    layout.y = stat_y + 3

    # --- 3. Hosts table ---
    hosts_table_targets = [
        {
            "datasource": copy.deepcopy(PROM_DS),
            "expr": 'count by (instance) (count by (instance,name) (container_last_seen{job=~"$job",name!=""}))',
            "instant": True,
            "range": False,
            "legendFormat": "__auto",
            "refId": "A",
        },
        {
            "datasource": copy.deepcopy(PROM_DS),
            "expr": 'sum by (instance) (rate(container_cpu_usage_seconds_total{job=~"$job",name!=""}[$__rate_interval])) * 100',
            "instant": False,
            "range": True,
            "legendFormat": "__auto",
            "refId": "B",
        },
        {
            "datasource": copy.deepcopy(PROM_DS),
            "expr": 'sum by (instance) (container_memory_working_set_bytes{job=~"$job",name!=""})',
            "instant": False,
            "range": True,
            "legendFormat": "__auto",
            "refId": "C",
        },
        {
            "datasource": copy.deepcopy(PROM_DS),
            "expr": 'sum by (instance) (rate(container_network_receive_bytes_total{job=~"$job",name!=""}[$__rate_interval]))',
            "instant": False,
            "range": True,
            "legendFormat": "__auto",
            "refId": "D",
        },
        {
            "datasource": copy.deepcopy(PROM_DS),
            "expr": 'sum by (instance) (rate(container_network_transmit_bytes_total{job=~"$job",name!=""}[$__rate_interval]))',
            "instant": False,
            "range": True,
            "legendFormat": "__auto",
            "refId": "E",
        },
        {
            "datasource": copy.deepcopy(PROM_DS),
            "expr": 'sum by (instance) (rate(container_fs_reads_bytes_total{job=~"$job",name!=""}[$__rate_interval]))',
            "instant": False,
            "range": True,
            "legendFormat": "__auto",
            "refId": "F",
        },
        {
            "datasource": copy.deepcopy(PROM_DS),
            "expr": 'sum by (instance) (rate(container_fs_writes_bytes_total{job=~"$job",name!=""}[$__rate_interval]))',
            "instant": False,
            "range": True,
            "legendFormat": "__auto",
            "refId": "G",
        },
    ]

    hosts_table_transforms = [
        {
            "id": "timeSeriesTable",
            "options": {
                "A": {"stat": "mean", "timeField": "Time"},
                "B": {"stat": "mean", "timeField": "Time"},
                "C": {"stat": "mean", "timeField": "Time"},
                "D": {"stat": "mean", "timeField": "Time"},
                "E": {"stat": "mean", "timeField": "Time"},
                "F": {"stat": "mean", "timeField": "Time"},
                "G": {"stat": "mean", "timeField": "Time"},
            },
        },
        {"id": "joinByField", "options": {"byField": "instance", "mode": "outer"}},
        {
            "id": "organize",
            "options": {
                "excludeByName": {},
                "includeByName": {},
                "indexByName": {},
                "renameByName": {
                    "Trend #A": "containers",
                    "Trend #B": "cpu",
                    "Trend #C": "memory",
                    "Trend #D": "net_rx",
                    "Trend #E": "net_tx",
                    "Trend #F": "disk_r",
                    "Trend #G": "disk_w",
                },
            },
        },
    ]

    hosts_table_overrides = [
        {
            "matcher": {"id": "byName", "options": "instance"},
            "properties": [
                {"id": "displayName", "value": "Host"},
                {
                    "id": "links",
                    "value": [{
                        "keepTime": True,
                        "targetBlank": False,
                        "title": "Docker - Host Overview",
                        "url": (
                            "/d/toj7b4l?var-prometheus_datasource=${prometheus_datasource}"
                            "&var-job=${__data.fields.job}&var-instance=${__value.raw}"
                        ),
                    }],
                },
            ],
        },
        {
            "matcher": {"id": "byName", "options": "containers"},
            "properties": [
                {"id": "displayName", "value": "Containers"},
                {"id": "unit", "value": "short"},
                {"id": "custom.width", "value": 90},
                {"id": "cellOptions", "value": {"type": "auto"}},
            ],
        },
        {
            "matcher": {"id": "byName", "options": "cpu"},
            "properties": [
                {"id": "displayName", "value": "CPU %"},
                {"id": "unit", "value": "percent"},
                {
                    "id": "thresholds",
                    "value": _std_thresholds([("green", 0), ("yellow", 70), ("red", 90)]),
                },
                {"id": "cellOptions", "value": {"type": "sparkline"}},
            ],
        },
        {
            "matcher": {"id": "byName", "options": "memory"},
            "properties": [
                {"id": "displayName", "value": "Memory (WS)"},
                {"id": "unit", "value": "decbytes"},
                {"id": "cellOptions", "value": {"type": "sparkline"}},
            ],
        },
        {
            "matcher": {"id": "byName", "options": "net_rx"},
            "properties": [
                {"id": "displayName", "value": "Net RX"},
                {"id": "unit", "value": "binBps"},
                {"id": "cellOptions", "value": {"type": "sparkline"}},
            ],
        },
        {
            "matcher": {"id": "byName", "options": "net_tx"},
            "properties": [
                {"id": "displayName", "value": "Net TX"},
                {"id": "unit", "value": "binBps"},
                {"id": "cellOptions", "value": {"type": "sparkline"}},
            ],
        },
        {
            "matcher": {"id": "byName", "options": "disk_r"},
            "properties": [
                {"id": "displayName", "value": "Disk Read"},
                {"id": "unit", "value": "binBps"},
                {"id": "cellOptions", "value": {"type": "sparkline"}},
            ],
        },
        {
            "matcher": {"id": "byName", "options": "disk_w"},
            "properties": [
                {"id": "displayName", "value": "Disk Write"},
                {"id": "unit", "value": "binBps"},
                {"id": "cellOptions", "value": {"type": "sparkline"}},
            ],
        },
    ]

    hosts_table = make_table(
        title="",
        description=(
            "One row per Docker host. "
            "Click a host name to drill into its Host Overview dashboard."
        ),
        targets=hosts_table_targets,
        transformations=hosts_table_transforms,
        overrides=hosts_table_overrides,
    )
    panels.append(layout.place(hosts_table, h=12))

    # --- 4. Integration Status row (collapsed) ---
    int_children_y = 1

    cadvisor_version_cluster = make_stat(
        title="cAdvisor Version",
        expr='cadvisor_version_info{job=~"$job"}',
        unit="string",
        description="cAdvisor version(s) in use.",
        display_name="${__field.labels.version}",
        thresholds=_std_thresholds([("green", 0)]),
    )
    cadvisor_version_cluster["options"]["reduceOptions"]["values"] = True
    cadvisor_version_cluster["options"]["textMode"] = "name"
    cadvisor_version_cluster["gridPos"] = {"h": 3, "w": 8, "x": 0, "y": int_children_y}

    build_info_cluster = make_table(
        title="Build Info",
        description="cAdvisor build metadata.",
        targets=[
            _target(
                'cadvisor_build_info{job=~"$job"}',
                ref="A", instant=True,
                extra={"format": "table"},
            )
        ],
        transformations=[],
        overrides=[],
    )
    build_info_cluster["gridPos"] = {"h": 5, "w": 8, "x": 8, "y": int_children_y}

    scrape_errors_cluster = make_stat(
        title="Scrape Errors",
        expr='sum(machine_scrape_error{job=~"$job"})',
        unit="short",
        description="Total scrape errors across all hosts.",
        thresholds=_std_thresholds([("green", 0), ("red", 1)]),
    )
    scrape_errors_cluster["gridPos"] = {"h": 3, "w": 8, "x": 16, "y": int_children_y}

    int_row_cluster = make_row(
        "Integration Status",
        collapsed=True,
        panels=[cadvisor_version_cluster, build_info_cluster, scrape_errors_cluster],
    )
    panels.append(layout.place(int_row_cluster, h=1))

    # Use container overview variables as base for prom datasource + job, drop others
    existing_vars = existing_container_overview.get("templating", {}).get("list", [])
    prom_ds_var = next(
        (v for v in existing_vars if v.get("name") == "prometheus_datasource"),
        None,
    )
    job_var_base = next(
        (v for v in existing_vars if v.get("name") == "job"),
        None,
    )

    if prom_ds_var is None:
        prom_ds_var = {
            "allowCustomValue": True,
            "hide": 0,
            "includeAll": False,
            "label": "Prometheus data source",
            "multi": False,
            "name": "prometheus_datasource",
            "options": [],
            "query": "prometheus",
            "refresh": 1,
            "regex": "(?!grafanacloud-usage|grafanacloud-ml-metrics).+",
            "skipUrlSync": False,
            "type": "datasource",
        }

    # Build job var for cluster (multi=false, no instance/name vars needed)
    cluster_job_var = {
        "allValue": ".+",
        "allowCustomValue": False,
        "datasource": copy.deepcopy(PROM_DS),
        "definition": "label_values(container_last_seen,job)",
        "hide": 0,
        "includeAll": False,
        "label": "Job",
        "multi": False,
        "name": "job",
        "options": [],
        "query": {
            "qryType": 1,
            "query": "label_values(container_last_seen,job)",
            "refId": "PrometheusVariableQueryEditor-VariableQuery",
        },
        "refresh": 2,
        "regex": "",
        "regexApplyTo": "value",
        "skipUrlSync": False,
        "sort": 1,
        "type": "query",
    }

    # Existing annotations from the container overview
    existing_annotations = existing_container_overview.get("annotations", {"list": []})

    cluster_dashboard = {
        "annotations": existing_annotations,
        "editable": True,
        "fiscalYearStartMonth": 0,
        "graphTooltip": 0,
        "links": [
            {
                "asDropdown": False,
                "icon": "",
                "includeVars": True,
                "keepTime": True,
                "tags": ["docker-integration"],
                "targetBlank": False,
                "title": "All Docker dashboards",
                "tooltip": "",
                "type": "dashboards",
            }
        ],
        "liveNow": False,
        "panels": panels,
        "preload": False,
        "refresh": "30s",
        "schemaVersion": 42,
        "templating": {
            "list": [copy.deepcopy(prom_ds_var), cluster_job_var]
        },
        "time": {"from": "now-1h", "to": "now"},
        "timepicker": {
            "refresh_intervals": [
                "5s", "10s", "30s", "1m", "5m", "15m", "30m", "1h", "2h", "1d"
            ]
        },
        "timezone": "browser",
        "title": "Docker - Cluster Overview",
        "uid": "docker-cluster-overview",
        "version": 1,
    }

    return cluster_dashboard


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    base_dir = "observability/dashboards"

    container_path = f"{base_dir}/docker-container-overview.json"
    host_path = f"{base_dir}/docker-host-overview.json"
    cluster_path = f"{base_dir}/docker-cluster-overview.json"

    print("Loading existing dashboards from disk...")
    container_existing = load_local_dashboard(container_path)
    host_existing = load_local_dashboard(host_path)

    # --- Container Overview ---
    print("\nBuilding Container Overview (tog2fp8)...")
    container_dashboard = build_container_overview(container_existing)
    print("Pushing Container Overview to Grafana...")
    result = push_dashboard(container_dashboard)
    url = result.get("url") or result.get("dashboardUid") or str(result)
    print(f"  -> {url}")
    # Fetch the pushed version back from Grafana to save the canonical form
    try:
        pushed_container = gcx_get("/api/dashboards/uid/tog2fp8")
        save_local_dashboard(
            container_path,
            pushed_container.get("dashboard", container_dashboard),
            meta=pushed_container.get("meta"),
        )
        print(f"  -> Saved to {container_path}")
    except Exception as e:
        print(f"  Warning: could not fetch back Container Overview: {e}", file=sys.stderr)
        save_local_dashboard(container_path, container_dashboard)

    # --- Host Overview ---
    print("\nBuilding Host Overview (toj7b4l)...")
    host_dashboard = build_host_overview(host_existing)
    print("Pushing Host Overview to Grafana...")
    result = push_dashboard(host_dashboard)
    url = result.get("url") or result.get("dashboardUid") or str(result)
    print(f"  -> {url}")
    try:
        pushed_host = gcx_get("/api/dashboards/uid/toj7b4l")
        save_local_dashboard(
            host_path,
            pushed_host.get("dashboard", host_dashboard),
            meta=pushed_host.get("meta"),
        )
        print(f"  -> Saved to {host_path}")
    except Exception as e:
        print(f"  Warning: could not fetch back Host Overview: {e}", file=sys.stderr)
        save_local_dashboard(host_path, host_dashboard)

    # --- Cluster Overview (new) ---
    print("\nBuilding Cluster Overview (docker-cluster-overview)...")
    cluster_dashboard = build_cluster_overview(container_existing)
    print("Pushing Cluster Overview to Grafana...")
    result = push_dashboard(cluster_dashboard)
    url = result.get("url") or result.get("dashboardUid") or str(result)
    print(f"  -> {url}")
    try:
        pushed_cluster = gcx_get("/api/dashboards/uid/docker-cluster-overview")
        save_local_dashboard(
            cluster_path,
            pushed_cluster.get("dashboard", cluster_dashboard),
            meta=pushed_cluster.get("meta"),
        )
        print(f"  -> Saved to {cluster_path}")
    except Exception as e:
        print(f"  Warning: could not fetch back Cluster Overview: {e}", file=sys.stderr)
        save_local_dashboard(cluster_path, cluster_dashboard)

    print("\nDone.")


if __name__ == "__main__":
    main()
