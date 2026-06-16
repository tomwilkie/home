# Accessing Home Assistant

You can talk to Home Assistant in the following ways

## Home Assistant MCP server

Use the `mcp__home-assistant__*` tools to read and write live HA configuration. The MCP server connects to `http://homeassistant.local:8123` when on the local network.

## Home Assistant CLI

There is the `hass-cli` command which can be used to e.g. download & upload dashboards.

To list dashboards in home assistant:
```sh
% hass-cli dashboard list
```

To download dashboards from home assistant
```sh
% hass-cli -o yaml dashboard get kitchen-home > dashboards/kitchen-home.yaml
```

To upload dashboards to home assistant
```sh
% hass-cli dashboard set dashboards/kitchen-home.yaml kitchen-home
```

To see difference between version controlled dashboard and uploaded dashboard
```sh
% diff -u dashboards/kitchen-home.yaml <(hass-cli -o yaml dashboard get kitchen-home)
```

## SSH

For information not exposed via MCP/API, SSH access is available as `root@homeassistant.local`. 
SSH is a last resort — prefer MCP tools. In particular:
- Use `ha_get_integration(domain="<domain>")` to inspect config entries and their current option values (the `options_schema` on each entry shows `suggested_value` for every field, which is the live value).
- Use `ha_get_integration(entry_id="...", include_schema=True)` to get the full options flow schema for a specific entry before updating it.

SSH access: `ssh root@homeassistant.local -C "<command>"` — always use `root@homeassistant.local`; host key verification fails with other usernames or hostnames.

Registry files live at `/config/.storage/` on the HA host:
- `core.entity_registry` — entities; structure: `.data.entities[]` (active), `.data.deleted_entities[]` (orphaned/removed)
- `core.device_registry` — devices; structure: `.data.devices[]` (active), `.data.deleted_devices[]` (removed)
- `core.config_entries` — integration config entries; structure: `.data.entries[]` (active only, no deleted section)

Orphaned entity fields: `orphaned_timestamp` (unix float), `platform`, `entity_id`
Deleted device fields: `identifiers` (array of `[integration, id]` pairs), `orphaned_timestamp`

**Never modify these files** — inspect only. HA must be stopped before any edits to prevent it overwriting changes.

Useful jq patterns:
```bash
# Deleted entities by platform count
jq '[.data.deleted_entities[] | .platform] | group_by(.) | map({platform: .[0], count: length}) | sort_by(-.count)' /config/.storage/core.entity_registry

# Deleted devices by integration count
jq '[.data.deleted_devices[] | .identifiers[0][0]] | group_by(.) | map({integration: .[0], count: length}) | sort_by(-.count)' /config/.storage/core.device_registry

# Find orphaned entities for a specific platform
jq '[.data.deleted_entities[] | select(.platform == "some_integration") | .entity_id]' /config/.storage/core.entity_registry
```

## UniFi MCP servers

The home network and cameras run on a UniFi **Dream Machine Pro Max** (UniFi Network + Protect). Two MCP plugin servers from the [`sirkirby/unifi-mcp`](https://github.com/sirkirby/unifi-mcp) marketplace expose it to Claude:

- **`unifi-protect`** — cameras, NVR, events, and Alarm Manager rules
- **`unifi-network`** — clients, devices, firewall, and DHCP reservations

### Setup

- Installed via the Claude Code plugin marketplace (`/plugin marketplace add sirkirby/unifi-mcp`, then `/plugin install unifi-protect@unifi-plugins` and `unifi-network@unifi-plugins`).
- Auth uses a **dedicated local admin account on the UDM** (UniFi OS → Admins & Users, "Restrict to Local Access Only", no MFA) — **not** a Ubiquiti SSO cloud account.
- Credentials live in `~/.claude/settings.json` env (`UNIFI_PROTECT_*`, `UNIFI_NETWORK_*`, and `UNIFI_API_KEY` — the last is required for the firewall integration API; host `192.168.0.1`) — **never** in this repo. Changing them requires a **full Claude Code restart** (MCP servers read env only at process startup; `/reload-plugins` is not enough).
- Both servers use lazy tool loading: call `protect_tool_index` / `unifi_tool_index` to discover tools, then `protect_execute` / `unifi_execute` to run them. Write tools take `confirm: false` (returns a preview) then `confirm: true` (applies).
- ⚠️ The UniFi **site name is the home street address**, so `unifi_get_site_settings` and some device payloads return it. **Never** echo it into repo files or commit messages (see the PII policy in [CLAUDE.md](CLAUDE.md)).

### Useful operations

- DHCP reservation: `unifi_set_client_ip_settings(mac_address, use_fixedip=true, fixed_ip=...)`. Clients are matched by **lowercase** MAC; if a MAC lookup returns "not found", find the record with `unifi_lookup_by_ip`.
- Read Protect alarm rules: `protect_alarm_list_rules` / `protect_alarm_get_rule`.
- Find a wired device's switch + port (e.g. to apply port isolation): `unifi_get_client_details(mac_address, summary=false)` → `sw_mac`, `sw_port`, `last_uplink_name`. Read/confirm port isolation via `unifi_get_switch_ports(device_mac)` → `port_overrides[].isolation`.

### Firewall (Zone-Based Firewall)

The full VLAN/firewall design and audit procedure live in [@network-security.md](network-security.md). MCP operating notes:

- The firewall tools (`unifi_list_firewall_zones` / `_policies` / `_groups`, `unifi_create_firewall_policy`, the ordering tools) need **`UNIFI_API_KEY`** set **and** **Zone-Based Firewall enabled** on the UDM. If either is missing the reads return `success: true` with an **empty** list — *not* an auth error. To disambiguate, call a key-only endpoint like `unifi_get_firewall_policy_ordering`: a `401` means the key is missing/wrong; a `400` (argument validation) means the key works and the gap is elsewhere (e.g. ZBF not enabled).
- The MCP can create/update firewall **policies** and **groups**, but **not zones** — create zones and assign networks in the UniFi UI, then reference their ids. After ZBF migration, all corporate LANs default into the `Internal` zone; dedicated per-VLAN zones give a default-deny posture.
- `unifi_create_firewall_policy` takes a `policy_data` object; `source`/`destination` each are `{zone_id, matching_target}` where `matching_target` is `ANY`, or `IP` + `matching_target_type: SPECIFIC` + `ips: [...]`, or `NETWORK` + `OBJECT` + `network_ids: [...]`. Set `logging: true` on BLOCK rules. New custom rules auto-index above predefined ones; within a zone-pair order ALLOW above BLOCK.
- `unifi_update_wlan` / `unifi_update_network` take changed fields inside an **`update_data`** object (e.g. WLAN client isolation = `update_data: {l2_isolation: true}`).
- **Traffic Flows** (`unifi_get_traffic_flows`) is read-only, **batches/lags** (not real-time), and only logs traffic that **matches a policy** — so containment audits depend on the BLOCK policies having `logging` enabled.

### Limitations

- The Protect server is **beta**. Its Alarm Manager **write** tools cannot modify this console's **legacy Protect alarm automations**: `protect_alarm_update_rule` rejects their `_new`-suffixed rule ids ("must be a v2 UUID or 24-char ObjectID"), and `protect_alarm_create_rule` fails because the normalized read shape is lossy and omits `trigger_id`. **Reads work fine** — edit alarm rules in the UniFi Protect UI instead (see the Front Door webhook note in [@notifications.md](notifications.md)).
- The unified UniFi-OS Alarm Manager API (`/api/v2/alarms`) is **not active** on this console; only the legacy Protect automations are present.

## Grafana

Home Assistant logs and metrics are sent to Grafana Cloud.
For access metrics & logs related to this home assistant instance, use the `gcx` skill & tools.