# Accessing Home Assistant

You can talk to Home Assistant in the following ways

## Home Assistant MCP server

Use the `mcp__claude_ai_ha-mcp__*` tools to read and write live HA configuration.

The server is **[`ha-mcp`](https://github.com/homeassistant-ai/ha-mcp)** (the "unofficial" Home Assistant MCP server) — its tool set is the `ha_*` family (`ha_get_state`, `ha_set_entity`, `ha_get_integration`, `ha_search`, `ha_config_get_dashboard`, etc.).

### Setup

ha-mcp runs **inside Home Assistant** as its in-process server (the `ha_mcp_tools` custom component, from HACS), and reaches Claude Code as a **claude.ai connector** rather than as a local MCP server. One connector serves both terminal sessions and Claude Code cloud environments, with nothing to configure per machine.

- **Endpoint:** an HA webhook, `https://<your-ha-external-host>/api/webhook/<your-webhook-id>` — the connect URL on the integration entry's Configure screen, reached through HA's own remote access. Don't put a port in it, not even `:443`: ha-mcp warns that any port breaks remote MCP clients.
- **Auth:** the entry's **Authentication mode** is `ha_auth`. HA itself is the OAuth server, and clients sign in with an HA **administrator** account (non-admin logins are refused). A request without a token gets `401` plus an OAuth challenge, so the URL on its own is not a credential. Don't switch back to `none`, where the URL *is* the credential — the endpoint is internet-facing.
- **Connector:** added at [claude.ai/customize/connectors](https://claude.ai/customize/connectors) as a custom connector named `ha-mcp`. That name sets the tool prefix, `mcp__claude_ai_ha-mcp__*`. It's authorized once in the browser; claude.ai holds the token, and in cloud sessions the session proxy authenticates for you. To re-authorize, reconnect it on claude.ai, not with `/mcp`.
- Terminal sessions fetch connectors **at startup**, so restart Claude Code after adding or re-authorizing the connector. Connectors only load when Claude Code is logged in with a claude.ai subscription — not when `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` or `apiKeyHelper` is in use.
- **Don't** add HA to a project `.mcp.json` (it's gitignored). It would duplicate every tool under a second prefix, the connect URL (external hostname + webhook ID) must not be committed (see the [PII policy](CLAUDE.md)), and OAuth tokens from `/mcp` sit in the local macOS Keychain, so they would never reach a cloud environment anyway.

## Home Assistant CLI

There is the `hass-cli` command which can be used to e.g. download & upload dashboards.

### Setup

The `dashboard` subcommands used below are **not yet in upstream** [`home-assistant/home-assistant-cli`](https://github.com/home-assistant/home-assistant-cli) — they live on the `add-dashboard-commands` branch of the fork [`tomwilkie/home-assistant-cli`](https://github.com/tomwilkie/home-assistant-cli/tree/add-dashboard-commands) (PR pending). Install from the fork until it's merged:

```sh
pipx install git+https://github.com/tomwilkie/home-assistant-cli.git@add-dashboard-commands
```

`hass-cli` reads the HA connection from the environment — a long-lived access token, separate from the MCP connector's OAuth sign-in (see [PII policy](CLAUDE.md), keep it out of files):

```sh
export HASS_SERVER=http://homeassistant.local:8123
export HASS_TOKEN=<your-long-lived-token>
```

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
- Credentials are read from the **shell environment** (`UNIFI_PROTECT_*`, `UNIFI_NETWORK_*`, and `UNIFI_API_KEY` — the last is required for the firewall integration API; host `192.168.0.1`) — exported from `~/.zshrc` or a sourced secrets file, **never** in this repo or in `settings.json`. Changing them requires a **full Claude Code restart** (MCP servers read env only at process startup; `/reload-plugins` is not enough).
- Both servers use lazy tool loading: call `protect_tool_index` / `unifi_tool_index` to discover tools, then `protect_execute` / `unifi_execute` to run them. Write tools take `confirm: false` (returns a preview) then `confirm: true` (applies).
- ⚠️ The UniFi **site name is the home street address**, so `unifi_get_site_settings` and some device payloads return it. **Never** echo it into repo files or commit messages (see the PII policy in [CLAUDE.md](CLAUDE.md)).

### Useful operations

- DHCP reservation: `unifi_set_client_ip_settings(mac_address, use_fixedip=true, fixed_ip=...)`. Clients are matched by **lowercase** MAC; if a MAC lookup returns "not found", find the record with `unifi_lookup_by_ip`.
- Read/write Protect alarm rules: `protect_alarm_list_rules` / `protect_alarm_get_rule` / `protect_alarm_update_rule`. Legacy rules have `_new`-suffixed ids (e.g. `66d12910038b6803e40003eb_new`) — these are accepted by the write tools as of v0.5.2+.
- Find a wired device's switch + port (e.g. to apply port isolation): `unifi_get_client_details(mac_address, summary=false)` → `sw_mac`, `sw_port`, `last_uplink_name`. Read/confirm port isolation via `unifi_get_switch_ports(device_mac)` → `port_overrides[].isolation`.

### Firewall (Zone-Based Firewall)

The full VLAN/firewall design and audit procedure live in [@network-security.md](network-security.md). MCP operating notes:

- The firewall tools (`unifi_list_firewall_zones` / `_policies` / `_groups`, `unifi_create_firewall_policy`, the ordering tools) need **`UNIFI_API_KEY`** set **and** **Zone-Based Firewall enabled** on the UDM. If either is missing the reads return `success: true` with an **empty** list — *not* an auth error. To disambiguate, call a key-only endpoint like `unifi_get_firewall_policy_ordering`: a `401` means the key is missing/wrong; a `400` (argument validation) means the key works and the gap is elsewhere (e.g. ZBF not enabled).
- The MCP can create/update firewall **policies** and **groups**, but **not zones** — create zones and assign networks in the UniFi UI, then reference their ids. After ZBF migration, all corporate LANs default into the `Internal` zone; dedicated per-VLAN zones give a default-deny posture.
- `unifi_create_firewall_policy` takes a `policy_data` object; `source`/`destination` each are `{zone_id, matching_target}` where `matching_target` is `ANY`, or `IP` + `matching_target_type: SPECIFIC` + `ips: [...]`, or `NETWORK` + `OBJECT` + `network_ids: [...]`. Set `logging: true` on BLOCK rules. New custom rules auto-index above predefined ones; within a zone-pair order ALLOW above BLOCK.
- `unifi_update_wlan` / `unifi_update_network` take changed fields inside an **`update_data`** object (e.g. WLAN client isolation = `update_data: {l2_isolation: true}`).
- **Traffic Flows** (`unifi_get_traffic_flows`) is read-only, **batches/lags** (not real-time), and only logs traffic that **matches a policy** — so containment audits depend on the BLOCK policies having `logging` enabled.

### Limitations

- The unified UniFi-OS Alarm Manager API (`/api/v2/alarms`) is **not active** on this console; only the legacy Protect automations are present (ids carry a `_new` suffix). The write tools (`protect_alarm_update_rule`, `protect_alarm_create_rule`) handle these correctly as of v0.5.2+.

## Grafana

Home Assistant logs and metrics are sent to Grafana Cloud.
For access metrics & logs related to this home assistant instance, use the `gcx` skill & tools.

`gcx` is the [Grafana Cloud CLI](https://github.com/grafana/gcx); the Claude skills/workflows are a thin layer over it, so the **CLI and the plugin are installed separately**.

### Setup

1. **CLI** — via Homebrew (installs to `/opt/homebrew/bin/gcx`):

   ```sh
   brew install grafana/grafana/gcx
   ```

   Verify with `gcx version`. (An older build installed from source under `~/go/bin` would shadow the brew binary on `PATH` — remove it so `gcx` resolves to the brew copy.)

2. **Claude skills/workflows** — via the Claude Code plugin marketplace (`grafana/gcx`):

   ```sh
   claude plugin marketplace add grafana/gcx
   claude plugin install gcx@gcx-marketplace
   ```

   This ships the `gcx:*` namespaced skills (e.g. `gcx:debug-with-grafana`, `gcx:setup-gcx`, `gcx:slo-manage`, `gcx:oncall-triage`). Run `gcx:setup-gcx` for first-run authentication.

- `gcx` stores its own config/credentials under `~/.config/gcx` (written by its auth flow) — **never** commit those into this repo.