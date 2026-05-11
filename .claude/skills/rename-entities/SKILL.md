---
name: rename-entities
description: >
  Rename devices & entities in a Home Assistant area to comply with naming-conventions.md.

  TRIGGER THIS SKILL WHEN:
  - User runs /rename-entities (optional <Area Display Name> or <Device Name>)`
  - User asks to rename, fix, or standardise entity IDs for a specific device or area.
---

# rename-entities

Rename devices & entities in a Home Assistant area to comply with `naming-conventions.md`.

**Usage:** `/rename-entities (optional <Area Display Name> or <Device Name>)`

## Main agent

1. If the user asked to rename entities for a specific device, look up the device by calling `ha_get_device` and searching by name to resolve the `device_id`, then spawn a per-device subagent followed by a reference-fix subagent. Use the `area_id` field from `ha_get_device` result — no extra call needed.
2. If the user asked to rename entities in a specific area, run the instructions for the per-area renaming.
3. If the user doesn't specify, call `ha_config_list_areas` to get all areas, then process the per-area renaming for earch area, sequenitally.

## Per-area renaming

Given an area name or id, you must:

1. Derive the `area_id` slug from the display name per the rules in `naming-conventions.md` (if needed).
2. Call `ha_get_device(area_id="<area_id>", detail_level="summary")` to get all devices. Paginate if `has_more: true`.
3. Spawn per-device subagents to do the renaming, in parallel. Pass the device name, device_id, area display name, and area_id to each. Do NOT look up entities in the main agent — delegate all entity work to subagents.
4. Collect the rename maps returned by each subagent (list of `{old_entity_id, new_entity_id}` pairs).
5. If any renames occurred, spawn a **single reference-fix subagent** (see below) passing the full rename map.
6. Print a summary table at the end; include all the devices you checked and any changes that were made.

## Per-device subagent

Each subagent receives the device name, device_id, area display name, and area_id. This subagent should use the Haiku model. It must:

0. Check the device name follows the right pattern.
1. Call `ha_get_device(device_id="...")` to get all entities.
2. For each entity, check:
   - **Entity ID**: does it start with `{domain}.{area_id}_`? If not, rename it with `ha_rename_entity`. Do NOT search for or fix references at this point — just rename.
   - **Display name**: does it embed the area or device name? If so, fix it per `naming-conventions.md`.
3. Return a structured list of all renames made: `[{old: "sensor.foo", new: "sensor.toms_office_bar"}, ...]`. Report what was already compliant too.

**`device_tracker.*` entities — conditional:**
Network-scanning integrations (UniFi, iRobot, ESPHome Presence Lite, etc.) create a tracker for every client they see. Apply this rule per entity:
- Device **has an area assigned** → rename per convention (it's a HA-managed device that happens to also be tracked)
- Device **has no area** → leave as-is (bare network client with no HA counterpart)

## Reference-fix subagent

Runs once per area, after all the per-device subagents complete, only if at least one rename occurred. Receives the full rename map (all old→new entity ID pairs across all devices).

For each renamed entity:
1. Call `ha_deep_search` with the **old** entity ID to find references in automations, scripts, dashboards, and group helpers.
2. Update any references found to use the new entity ID.
3. Be careful with `ha_deep_search` false positives — short substrings can match unrelated IDs. Always verify before updating.

Report a summary of all references updated.

### Changing IDs — Reference Checks

After renaming any area ID, entity ID, or automation entity ID, check for references in:

> **Note:** `ha_deep_search` uses substring matching. Short queries (e.g. `nas_`) can produce false positives by matching unrelated entity IDs (e.g. `rachanas_` contains `nas_`). Always verify matches manually before updating references.

### 1. Dashboards

Use `ha_config_get_dashboard` on every dashboard (list them first with `ha_config_get_dashboard(list_only=True)`). References to IDs appear in:

- `entity` fields on tile, button, and other cards
- `tap_action.target.entity_id` and `tap_action.perform_action` data
- `filter.include[].area` on `auto-entities` cards
- Jinja templates inside `icon_color`, `primary`, `secondary` strings (e.g. `area_entities('area_id')`, `area_id_filter: "area_id"`)
- `visibility` conditions comparing against sensor states that return area IDs
- Entity lists inside `entities` cards (can be plain strings or `{entity: ...}` objects)
- `badges` arrays on heading cards
- `footer.entity` on entities cards

> **Warning:** `ha_config_get_dashboard(entity_id=...)` search mode only finds entities in top-level `entity` and `entities` card fields. It **does not** find references in `visibility` conditions, `badges`, `footer.entity`, or nested structures. Always fetch the **full dashboard config** and grep for the old entity ID string to catch everything.

### 2. Automations

Do **not** rely on manually guessing which automations reference a renamed entity — use `ha_deep_search` with the old entity ID first to get an exhaustive list. Then use `ha_config_get_automation` on each match and check:

- `trigger` — state triggers on the entity, or `event_data.entity_id`
- `condition` — state or template conditions referencing the entity
- `action` — service calls targeting the entity (e.g. `automation.turn_on`, `automation.trigger`, `light.turn_on` with `area_id`)
- Blueprint `input` fields (e.g. `area_id: "old_area_id"`)

> **Warning:** Automations that synchronise or mirror an entity (e.g. a "Synchronise Alarm Time" automation triggered by `time.clock_alarm_time`) are easily missed because they don't control the device being renamed — they just observe it. `ha_deep_search` will surface them; manual inspection will not.

### 3. Group helpers

Use `ha_get_integration(domain="group")` to list **all** group config entries, then check every group whose domain matches the renamed entity's domain. Do not limit checks to occupancy groups — media_player groups, light groups, and others can all contain stale entity IDs.

For each candidate group, read its current members via `ha_get_state(entity_id)` and inspect the `entity_id` attribute. If any member IDs are stale, update via `ha_set_config_entry_helper` with the corrected `entities` list.

Common groups to check (not exhaustive):
- `binary_sensor.{area_id}_occupancy` — room-level occupancy group
- `binary_sensor.house_occupancy_raw` — aggregates all room occupancy groups
- `media_player.notification_players` — all notification speaker targets
- Any light group, cover group, or other domain group that may include the renamed entity

To update: `ha_get_integration(domain="group")` to find the `entry_id`, then `ha_set_config_entry_helper("group", entry_id=..., config={"group_type": "<type>", "entities": [...], "hide_members": false})`.

### 4. Update order

1. Identify all references first (dashboards + automations + group helpers)
2. Rename the ID (`ha_rename_entity` for entities/automations, delete+recreate for areas)
3. Update all references immediately after — dashboards via `ha_config_set_dashboard` with `python_transform`, automations via `ha_config_set_automation`, group helpers via `ha_set_config_entry_helper`

---

## Gotchas learned from practice

- Do NOT use SSH at any point for this skill.
- **Z-Wave (zwave_js)**: integration bakes the device name into `original_name` (e.g. `"Tom's Office Spotlight: Electric Consumption [W]"`). Fix with `ha_set_entity(entity_id, name="Electric Consumption [W]")`.
- **ESPHome with hardware-suffix IDs** (e.g. `binary_sensor.everything_presence_lite_ee60e8_occupancy`): all non-tracker entities need renaming. Can be 70+ entities — subagent handles this fine.
- **Nest Protect**: generates IDs in the form `{domain}.nest_protect_{area_id}_{measurement}_N` — rename to `{domain}.{area_id}_nest_protect_{measurement}`.
- **UniFi networking gear** (access points, switches): entity IDs like `sensor.u5g_max_clients` or `sensor.link_speed_37` need renaming; only `device_tracker.*` is exempt.
- **Music Assistant virtual devices**: `original_name` is often null, causing display name to fall back to the full device name. Set a concise custom name.
- **`ha_deep_search` false positives**: short substrings can match unrelated IDs. Always verify matches before updating references.
- **ESPHome sub-devices share entities with parent**: When an ESPHome device has a Bluetooth proxy sub-device (e.g. "Everything Presence Lite" + "Everything Presence Lite (Bluetooth)"), `ha_get_device` on the sub-device returns the **same** entity list as the parent. Do NOT rename entities that already comply with the parent device's slug — they belong to the parent. A sub-device whose entities are already correctly prefixed with `{area_id}_{parent_slug}_` should be treated as fully compliant and left alone.
