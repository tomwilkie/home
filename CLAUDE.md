# Repository Purpose

This repo contains config and guidance for my Home Assistant setup, including:
- **HA config backups** (`backups/`) — Ad-hoc exports of important automations, scripts, and helpers from the live HA instance for version history.
- **Policies** (e.g. `naming-conventions.md`) - Various documentation on how the home assistant setup is configured.

The live Home Assistant configuration (automations, scripts, helpers, dashboards) lives in the running HA instance and is accessed via the MCP server, not via files in this repo.

# Accessing Home Assistant

**MCP** Use the `mcp__home-assistant__*` tools to read and write live HA configuration. The MCP server connects to `http://homeassistant.local:8123` or `http://homeassitant.local` when on the local network.

**SSH** For information not exposed via MCP/API, SSH access is available as `root@homeassistant.local`.  This should be used as a last resort.

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

**Grafana** For access metrics & logs related to this home assistant instance, use the gcx skill & tools.
