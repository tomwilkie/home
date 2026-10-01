# Access Home Assistant

This document covers each way to reach Home Assistant, the UniFi gateway and Grafana Cloud, and
the operating quirks of each tool.

## Home Assistant MCP server

To read and write live Home Assistant configuration, use the `mcp__claude_ai_ha-mcp__*` tools.
The server is [`ha-mcp`](https://github.com/homeassistant-ai/ha-mcp), the unofficial Home
Assistant MCP server, and its tools are the `ha_*` family (`ha_get_state`, `ha_set_entity`,
`ha_get_integration`, `ha_search`, `ha_config_get_dashboard`).

### Setup

ha-mcp runs inside Home Assistant as the `ha_mcp_tools` custom component from HACS, and reaches
Claude Code as a claude.ai connector rather than as a local MCP server. One connector serves
terminal sessions and Claude Code cloud environments, with nothing to configure per machine.

- **Endpoint:** a Home Assistant webhook, `https://<your-ha-external-host>/api/webhook/<your-webhook-id>`. It is the connect URL on the integration entry's **Configure** screen. Don't put a port in it, not even `:443`, because any port breaks remote MCP clients.
- **Auth:** the entry's **Authentication mode** is `ha_auth`. Home Assistant is the OAuth server, and clients sign in with an administrator account. A request without a token gets `401` and an OAuth challenge, so the URL alone is not a credential. Don't switch back to `none`, where the URL is the credential, because the endpoint is internet-facing.
- **Connector:** a custom connector named `ha-mcp`, added at [claude.ai/customize/connectors](https://claude.ai/customize/connectors). The name sets the tool prefix. To re-authorise, reconnect it on claude.ai, not with `/mcp`.
- **Startup:** terminal sessions fetch connectors at startup, so restart Claude Code after you add or re-authorise the connector. Connectors only load when Claude Code is logged in with a claude.ai subscription, not when `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` or `apiKeyHelper` is in use.
- **No `.mcp.json`:** don't add Home Assistant to a project `.mcp.json`. It duplicates every tool under a second prefix, the connect URL must not be committed (see the [PII and secrets policy](CLAUDE.md#pii-and-secrets-policy)), and OAuth tokens from `/mcp` stay in the local macOS Keychain, so they don't reach a cloud environment.

### Operating notes

- **Write tools need a rotating acknowledgement key.** `ha_config_set_automation`, `_script`, `_scene`, `_helper` and `_dashboard` refuse with `BPS_ACKNOWLEDGMENT_REQUIRED` until you read the server's best-practices skill and pass the key it prints as `BestPracticeKey`. The key rotates hourly, so re-read the skill when a key from earlier in the session is rejected.
- **Pass `MandatoryBPS=false` on later writes.** Without it, each write echoes the full reference files back, which can push the tool result past its size limit and hide the `success` and `entity_id` fields.
- **`python_transform` needs a `config_hash`** from a preceding `ha_config_get_automation`. It is the cheapest way to make a small edit without re-sending a large config.
- **The REST config API is not gated.** `./scripts/ha-api /api/config/automation/config/<id> -X POST -d @file.json`, followed by `POST /api/services/automation/reload`, runs the same validation with no skill round trip.
- **`ha_get_logs` searches a bounded window** of a buffer that holds about four hours. For anything older, query Loki as described in [_Home Assistant's own logs_](observability.md#home-assistants-own-logs).

## Home Assistant CLI

`hass-cli` downloads and uploads dashboards, and sends raw WebSocket commands
(`hass-cli raw ws`) for registry updates that the MCP server cannot make. The dashboard commands
are in [_Workflow_](dashboards.md#workflow).

The `dashboard` subcommands are not in upstream
[`home-assistant/home-assistant-cli`](https://github.com/home-assistant/home-assistant-cli).
They live on the `add-dashboard-commands` branch of the fork
[`tomwilkie/home-assistant-cli`](https://github.com/tomwilkie/home-assistant-cli/tree/add-dashboard-commands).
Install from the fork:

```sh
pipx install git+https://github.com/tomwilkie/home-assistant-cli.git@add-dashboard-commands
```

`hass-cli` reads the connection from the environment. The token is a long-lived access token,
separate from the MCP connector's OAuth sign-in, and stays out of files:

```sh
export HASS_SERVER=http://homeassistant.local:8123
export HASS_TOKEN=<your-long-lived-token>
```

## SSH

SSH is a last resort for information that the MCP server and API don't expose. Before you reach
for it, try `ha_get_integration(domain="<domain>")`, which returns config entries and their
option values: the `suggested_value` of each field in `options_schema` is the live value. For
the full options flow schema of one entry, use
`ha_get_integration(entry_id="...", include_schema=True)`.

To run a command, use `ssh root@homeassistant.local -C "<command>"`. Host key verification fails
with any other username or hostname.

The registry files live in `/config/.storage/` on the Home Assistant host:

| File | Contents |
|---|---|
| `core.entity_registry` | `.data.entities[]` (active) and `.data.deleted_entities[]` (orphaned, with `orphaned_timestamp`, `platform` and `entity_id`) |
| `core.device_registry` | `.data.devices[]` (active) and `.data.deleted_devices[]` (removed, with `identifiers` as `[integration, id]` pairs and `orphaned_timestamp`) |
| `core.config_entries` | `.data.entries[]` (active only) |

Inspect these files only. Don't edit them while Home Assistant is running, because it overwrites
the changes.

The following `jq` query counts deleted entities by platform, and the same shape works for the
other registries:

```bash
jq '[.data.deleted_entities[] | .platform] | group_by(.) | map({platform: .[0], count: length}) | sort_by(-.count)' /config/.storage/core.entity_registry
```

## UniFi MCP servers

The home network and cameras run on a UniFi Dream Machine Pro Max (UDM), which hosts UniFi
Network and UniFi Protect. Two MCP plugin servers from the
[`sirkirby/unifi-mcp`](https://github.com/sirkirby/unifi-mcp) marketplace expose it:

- **`unifi-protect`** covers cameras, the network video recorder (NVR), events and Alarm Manager rules.
- **`unifi-network`** covers clients, devices, firewall and DHCP reservations.

### Setup

- **Install** through the Claude Code plugin marketplace: `/plugin marketplace add sirkirby/unifi-mcp`, then `/plugin install unifi-protect@unifi-plugins` and `unifi-network@unifi-plugins`.
- **Auth** uses a dedicated local admin account on the UDM (**Admins & Users**, **Restrict to Local Access Only**, no MFA), not a Ubiquiti cloud account.
- **Credentials** come from the shell environment: `UNIFI_PROTECT_*`, `UNIFI_NETWORK_*` and `UNIFI_API_KEY`, with host `192.168.0.1`. Export them from `~/.zshrc` or a sourced secrets file, and keep them out of this repo and `settings.json`. The MCP servers read the environment at process startup, so a change needs a full Claude Code restart. `/reload-plugins` is not enough.
- **Tool loading is lazy.** Call `protect_tool_index` or `unifi_tool_index` to discover tools, then `protect_execute` or `unifi_execute` to run them. Write tools take `confirm: false`, which returns a preview, then `confirm: true`, which applies the change.
- **The UniFi site name is the home street address**, so `unifi_get_site_settings` and some device payloads return it. Don't echo it into repo files or commit messages.

### Useful operations

- **Reserve a DHCP address** with `unifi_set_client_ip_settings(mac_address, use_fixedip=true, fixed_ip=...)`. The server matches clients by lowercase MAC. If a MAC lookup returns "not found", find the record with `unifi_lookup_by_ip`.
- **Read and write Protect alarm rules** with `protect_alarm_list_rules`, `protect_alarm_get_rule` and `protect_alarm_update_rule`. This console has only legacy Protect automations, whose IDs carry a `_new` suffix (for example `66d12910038b6803e40003eb_new`), because the unified Alarm Manager API (`/api/v2/alarms`) is not active on it. The write tools accept these IDs from v0.5.2.
- **Find a wired device's switch and port** with `unifi_get_client_details(mac_address, summary=false)`, which returns `sw_mac`, `sw_port` and `last_uplink_name`. Read port isolation from `unifi_get_switch_ports(device_mac)` in `port_overrides[].isolation`.
- **Update a WLAN or network** with `unifi_update_wlan` or `unifi_update_network`. Both take the changed fields inside an `update_data` object, for example `update_data: {l2_isolation: true}`.

### Firewall tools

The VLAN and firewall design is in [network-security.md](network-security.md). The following
notes cover the tools:

- **The firewall tools need `UNIFI_API_KEY` and Zone-Based Firewall enabled on the UDM.** If either is missing, the reads return `success: true` with an empty list, not an auth error. To tell the two apart, call `unifi_get_firewall_policy_ordering`: a `401` means the key is missing or wrong, and a `400` means the key works and the gap is elsewhere.
- **The MCP server creates, updates and deletes policies and groups, but not zones.** Create zones and assign networks in the UniFi UI, then reference their IDs.
- **`unifi_create_firewall_policy` takes a `policy_data` object.** The `source` and `destination` fields are each `{zone_id, matching_target}`, where `matching_target` is one of the following:
  - `ANY`
  - `IP` with `matching_target_type: SPECIFIC` and `ips: [...]`
  - `NETWORK` with `matching_target_type: OBJECT` and `network_ids: [...]`
  - `CLIENT` with `matching_target_type: SPECIFIC` and `client_macs: [...]`
- **Set `logging: true` on BLOCK rules**, so the audit and the Loki pipeline see them.
- **A created custom rule lands last in its zone pair.** `unifi_reorder_firewall_policies` returned HTTP 500 and `index` edits through `unifi_update_firewall_policy` had no effect when the IOT rules were built, so the working way to move a rule is in [_Rule ordering_](network-security.md#rule-ordering).
- **`unifi_get_traffic_flows` is read-only and lags real time.** It returns allowed and blocked flows, one page per call, and each flow names the policies it matched.

If an MCP write tool fails, the UniFi API key also authenticates the raw v2 API. `GET` and
`POST` the collection, and `PUT` or `DELETE` a single policy by `_id`:

```sh
curl -sk -H "X-API-KEY: $UNIFI_API_KEY" \
  https://192.168.0.1/proxy/network/v2/api/site/default/firewall-policies[/POLICY_ID]
```

## UniFi SSH

`scripts/unifi-ssh` logs in to the UniFi gateway or to an adopted UniFi device, with the
credentials read from 1Password by the `op` CLI. Both sets live on the
`House Stuff/Unifi Ubiquiti Account` item:

| Target | User | 1Password fields |
|---|---|---|
| Gateway (UDM, `192.168.0.1`) | `root` | `Gateway SSH Password` |
| Adopted devices (access points, switches, U5G Max) | `Device SSH User` | `Device SSH Password` |

```sh
scripts/unifi-ssh gateway                                   # interactive shell on the UDM
scripts/unifi-ssh gateway 'conntrack -L -d 192.168.2.10'    # one command
scripts/unifi-ssh device 192.168.4.34                       # shell on the U5G Max
scripts/unifi-ssh device 192.168.4.34 "uiwwand-chat -t 5 'AT!GSTATUS?'"
```

Arguments after the target pass straight to `ssh`. For the `ssh root@192.168.0.1 …` commands in
[network-security.md](network-security.md), substitute `scripts/unifi-ssh gateway`.

- **The two sets of credentials are not interchangeable.** The gateway takes its own root password. Every adopted device takes the site-wide **Device SSH Settings** credentials (UniFi Network → Devices → **Device Updates and Settings**), so a change there must be copied to 1Password.
- **The script is its own askpass helper.** `ssh` reads a password only from a terminal or from an `SSH_ASKPASS` program. The script sets `SSH_ASKPASS` to itself with `SSH_ASKPASS_REQUIRE=force`, and when `ssh` calls it back it prints the `op read` result. Only the 1Password *reference* is passed in the environment, so the password never reaches the command line, the environment or a file, and `sshpass` is not needed.
- **`op` must be signed in.** If 1Password is locked, the desktop app prompts to unlock it. If `op read` fails, `ssh` gets no password and reports `Permission denied`, so run the `op read` on its own to see the real error.
- **New host keys are accepted automatically** (`StrictHostKeyChecking=accept-new`). With askpass forced, a host-key yes/no prompt would be answered with the password and fail. A *changed* key still fails, as it should: after a reinstall, remove the old entry with `ssh-keygen -R HOST`.
- **The script requires OpenSSH 10.1 or later.** It passes `WarnWeakCrypto=no-pq-kex`, because UniFi devices offer no post-quantum key exchange and OpenSSH 10 otherwise warns on every connection. Older clients reject the option.
- **The devices run BusyBox `ash`, not bash**, with a reduced command set (the U5G Max has no `hostname`, for example).

## Grafana

Home Assistant logs and metrics go to Grafana Cloud. To query them, use the `gcx` skills and
CLI. `gcx` is the [Grafana Cloud CLI](https://github.com/grafana/gcx), and the Claude skills are
a thin layer over it, so you install the two separately:

1. Install the CLI with Homebrew, then check it with `gcx version`:

   ```sh
   brew install grafana/grafana/gcx
   ```

   An older build under `~/go/bin` shadows the Homebrew binary on `PATH`, so remove it.

2. Install the skills through the Claude Code plugin marketplace, then run `gcx:setup-gcx` to authenticate:

   ```sh
   claude plugin marketplace add grafana/gcx
   claude plugin install gcx@gcx-marketplace
   ```

`gcx` stores its config and credentials under `~/.config/gcx`. Don't commit them.
