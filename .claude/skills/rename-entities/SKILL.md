---
name: rename-entities
description: >
  Rename entities in a Home Assistant area to comply with naming-conventions.md.

  TRIGGER THIS SKILL WHEN:
  - User runs /rename-entities (optional <Area Display Name> or <Device Name>)`
  - User asks to rename, fix, or standardise entity IDs for a specific device or area.
---

# rename-entities

Rename entities in a Home Assistant area to comply with `naming-conventions.md`.

**Usage:** `/rename-entities (optional <Area Display Name> or <Device Name>)`

---

## Process

### Main agent

1. If the user asked to rename entities for a specific device, look up the device by calling `ha_get_device` and searching by name to resolve the `device_id`, then spawn a per-device subagent followed by a reference-fix subagent.
2. If the user asked to rename entities in a specific area, spawn a per-area subagent.
3. If the user doesn't specify, call `ha_config_list_areas` to get all areas, then spawn a per-area subagent for each, sequentially.

### Per-area subagent

1. Derive the `area_id` slug from the display name per the rules in `naming-conventions.md`.
2. Call `ha_get_device(area_id="<area_id>", detail_level="summary")` to get all devices. Paginate if `has_more: true`.
3. Spawn per-device subagents **in batches of up to 5** (send up to 5 Agent tool calls in a single message, wait for all to complete, then send the next batch). Pass the device name, device_id, area display name, and area_id to each. Do NOT look up entities in the main agent — delegate all entity work to subagents.
4. Collect the rename maps returned by each subagent (list of `{old_entity_id, new_entity_id}` pairs).
5. If any renames occurred, spawn a **single reference-fix subagent** (see below) passing the full rename map.
6. Print a summary table at the end: device name | changes made.

Do NOT use SSH at any point.

### Per-device subagent

Each subagent receives the device name, device_id, area display name, and area_id. It must:

1. Call `ha_get_device(device_id="...")` to get all entities.
2. For each entity, check:
   - **Entity ID**: does it start with `{domain}.{area_id}_`? If not, and it is not an exempt tracker (see below), rename it with `ha_rename_entity`. Do NOT search for or fix references — just rename.
   - **Display name**: does it embed the area or device name? If so, fix it per `naming-conventions.md`.
3. Return a structured list of all renames made: `[{old: "sensor.foo", new: "sensor.toms_office_bar"}, ...]`. Report what was already compliant too.

**`device_tracker.*` entities — conditional:**
Network-scanning integrations (UniFi, iRobot, ESPHome Presence Lite, etc.) create a tracker for every client they see. Apply this rule per entity:
- Device **has an area assigned** → rename per convention (it's a HA-managed device that happens to also be tracked)
- Device **has no area** → leave as-is (bare network client with no HA counterpart)

Use the `area_id` field from the step 1 `ha_get_device` result — no extra call needed. When invoked for a single device (not via a per-area subagent), the `area_id` may not have been passed in; read it from the device result.

### Reference-fix subagent

Runs once after all per-device subagents complete, only if at least one rename occurred. Receives the full rename map (all old→new entity ID pairs across all devices).

For each renamed entity:
1. Call `ha_deep_search` with the **old** entity ID to find references in automations, scripts, dashboards, and group helpers.
2. Update any references found to use the new entity ID.
3. Be careful with `ha_deep_search` false positives — short substrings can match unrelated IDs. Always verify before updating.

Report a summary of all references updated.

---

## Gotchas learned from practice

- **Z-Wave (zwave_js)**: integration bakes the device name into `original_name` (e.g. `"Tom's Office Spotlight: Electric Consumption [W]"`). Fix with `ha_set_entity(entity_id, name="Electric Consumption [W]")`.
- **ESPHome with hardware-suffix IDs** (e.g. `binary_sensor.everything_presence_lite_ee60e8_occupancy`): all non-tracker entities need renaming. Can be 70+ entities — subagent handles this fine.
- **Nest Protect**: generates IDs in the form `{domain}.nest_protect_{area_id}_{measurement}_N` — rename to `{domain}.{area_id}_nest_protect_{measurement}`.
- **UniFi networking gear** (access points, switches): entity IDs like `sensor.u5g_max_clients` or `sensor.link_speed_37` need renaming; only `device_tracker.*` is exempt.
- **Music Assistant virtual devices**: `original_name` is often null, causing display name to fall back to the full device name. Set a concise custom name.
- **`ha_deep_search` false positives**: short substrings can match unrelated IDs. Always verify matches before updating references.
