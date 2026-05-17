# Accessing Home Assistant

You can talk to Home Assistant in the following ways

## Home Assistant MCP server

Use the `mcp__home-assistant__*` tools to read and write live HA configuration. The MCP server connects to `http://homeassistant.local:8123` or `http://homeassistant.local` when on the local network.

## Home Assistant CLI

There is the `hass-cli` command which can be used to e.g. download & upload dashboards:

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

SSH access: `ssh root@homeassistant.local -C "<command>"`

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

## Grafana

Home Assistant logs and metrics are sent to Grafana Cloud.
For access metrics & logs related to this home assistant instance, use the `gcx` skill & tools.