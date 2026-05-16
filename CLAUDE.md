# Repository Purpose

This repo contains config and guidance for my Home Assistant setup, including:
- **HA config backups** (`backups/`) — Ad-hoc exports of important automations, scripts, and helpers from the live HA instance for version history.
- **Policies** (e.g. `naming-conventions.md`, `lighting-automation.md` and `notifications.md`) - Various documentation on how the home assistant setup is configured.

The live Home Assistant configuration (automations, scripts, helpers, dashboards) lives in the running HA instance and is accessed via the MCP server, not via files in this repo.

# Accessing Home Assistant

**MCP** Use the `mcp__home-assistant__*` tools to read and write live HA configuration. The MCP server connects to `http://homeassistant.local:8123` or `http://homeassitant.local` when on the local network.

**SSH** For information not exposed via MCP/API, SSH access is available as `root@homeassistant.local`. SSH is a last resort — prefer MCP tools. In particular:
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

**Grafana** For access metrics & logs related to this home assistant instance, use the gcx skill & tools.

---

# Naming Conventions

Always consult `naming-conventions.md` before creating or renaming entities, helpers, automations, or devices. Key rules that are easy to miss:

## Entity IDs must be area-first

Entity IDs follow `{domain}.{area_id}_{device_slug}_{measurement}`. The area comes **first** — this applies to all entities including those auto-created by integrations (adaptive lighting, template helpers, etc.). When an integration creates entities with the wrong order (e.g. `switch.adaptive_lighting_living_room`), rename them with `ha_set_entity(new_entity_id=...)` immediately.

## Display names must not include the area or device

Integration `original_name` values often embed the area (e.g. "Adaptive Lighting: Living Room"). After renaming an entity ID, check the display name and override it with `ha_set_entity(name="...")` to strip the area prefix. Correct names: `Adaptive Lighting`, `Adapt Brightness`, `Sleep Mode`. Incorrect: `Adaptive Lighting: Living Room`.

## Dashboard cards need explicit name overrides

When an entity's display name is intentionally generic (e.g. "Adaptive Lighting" for every room's switch), use the object form in entities cards to show the room name in the UI:
```yaml
entities:
  - entity: switch.living_room_adaptive_lighting
    name: Living Room
```
This keeps the entity name convention-compliant while remaining readable in the dashboard.

## After any rename, update all consumers

Renaming an entity ID does **not** propagate automatically. Always update:
1. Dashboard cards (use `ha_config_get_dashboard(entity_id=...)` to find them)
2. Automations that reference the old entity ID
3. Template helpers whose `state` template references the old entity ID
4. Scripts
