# Home Assistant Naming Conventions

## Areas

### Area IDs

Area IDs are slugified from the display name using these rules:

- Spaces → underscores (`_`)
- Apostrophes → **dropped** (not replaced with `_s_`)
- Everything lowercase

Examples:

| Display Name | area_id |
|---|---|
| Basement | `basement` |
| Tom's Office | `toms_office` |
| Nursery | `nursery` |
| Front Guest Room | `front_guest_room` |
| Hallway (Outside Tom's Office) | `hallway_outside_toms_office` |

> **Note:** HA auto-generates area IDs differently (apostrophes become `_s_`). When creating a new area whose name contains an apostrophe, create it first with a plain name (e.g. "Toms Office") to get the correct slug, then update the display name to the correct value (e.g. "Tom's Office").

---

## Devices

### Naming format

```
{Area Display Name} - {Device Specific Name}
```

- The area display name comes first, exactly as written (including apostrophes)
- A ` - ` separator (space-dash-space) separates area from device
- The device-specific name identifies the device within the area

Examples:

| Area | Device | Full Name |
|---|---|---|
| Kitchen | Netatmo | `Kitchen - Netatmo` |
| Tom's Office | Roomba | `Tom's Office - Roomba` |
| Nursery | Motion Sensor | `Nursery - Motion Sensor` |
| Master Bedroom | Lamp Tom's | `Master Bedroom - Lamp Tom's` |
| Front Guest Room | Nest Protect | `Front Guest Room - Nest Protect` |

### Scope

- Devices **with** an assigned area must follow this convention, regardless of type (including networking gear, infrastructure devices, etc.)
- Devices **without** an area (system/infrastructure devices such as HA Core, HACS, networking gear) are excluded

---

## Entities

### Entity ID format

```
{domain}.{area_id}_{device_slug}_{measurement}
```

- `domain` — the HA domain (e.g. `sensor`, `binary_sensor`, `light`, `switch`)
- `area_id` — the area's slug (see Area IDs above)
- `device_slug` — a short identifier for the device within the area
- `measurement` — what the entity measures or controls (e.g. `temperature`, `pressure`, `occupancy`)

Examples:

| Entity ID | Area | Device | Measurement |
|---|---|---|---|
| `sensor.kitchen_netatmo_pressure` | `kitchen` | netatmo | pressure |
| `sensor.toms_office_motion_sensor_temperature` | `toms_office` | motion_sensor | temperature |
| `binary_sensor.nursery_motion_sensor_occupancy` | `nursery` | motion_sensor | occupancy |
| `light.front_guest_room_lamp_desk` | `front_guest_room` | lamp | desk |

### Key rules

- Entity IDs must start with `{domain}.{area_id}_` — the area_id prefix is mandatory
- Apostrophes in area display names are **dropped** in the area_id slug, so they do not appear in entity IDs (e.g. `toms_office_...` not `tom_s_office_...`)
- Entities on devices without an area assignment are excluded from this convention
- Integration-auto-generated entity IDs (e.g. `device_tracker.unifi_default_...`) cannot always be controlled and may not comply

### Display names (friendly names)

Entity display names should be concise and reflect only what the entity measures or controls — they must **not** include the area or device name as a prefix.

- **Correct:** `Temperature`, `Battery Level`, `Smoke Status`, `Motion detection`
- **Incorrect:** `Nursery Motion Sensor Temperature`, `Nest Protect (Baby's Room) Smoke Status`

**Why this matters:** Integrations and HA itself sometimes auto-generate display names by prepending the device name (e.g. `{Device Name} {measurement}`). After a device rename, these baked-in names become stale and misleading.

**How to fix stale display names after renaming:**

1. If the entity has a user-set custom name (`name` field in entity registry is not null) that references the old device/area name — **clear it** with `ha_set_entity(entity_id, name="")` so it reverts to the integration default.
2. If the integration's own `original_name` embeds the old device name (e.g. `"Nest Protect (Baby's Room) Smoke Status"`) — **set a custom override** with `ha_set_entity(entity_id, name="Smoke Status")` to strip the prefix.

> **Note:** After renaming a device or entity ID, always check entity display names for each device and fix any that still reference the old name.

---

## Automations

### Entity ID format

Automation entity IDs are slugified from the alias (display name) using the same rules as area IDs:

- Lowercase, spaces → underscores
- Apostrophes → **dropped** (not `_s_`)
- ` - ` separators → `_`
- Special characters (parentheses, etc.) → dropped

```
automation.{slugified_alias}
```

Examples:

| Alias | entity_id |
|---|---|
| "Basement Lights" | `automation.basement_lights` |
| "Tom's Office Lights" | `automation.toms_office_lights` |
| "Nursery Lights" | `automation.nursery_lights` |
| "Living Room - Manual" | `automation.living_room_manual` |
| "Notify on Tumble Drier finished" | `automation.notify_on_tumble_drier_finished` |

> **Note:** HA auto-generates automation entity IDs from the alias when first created, using its own slugification (which maps apostrophes to `_s_`). When renaming an automation's alias after creation, the entity_id is **not** automatically updated — use `ha_rename_entity` to fix it manually.

---

## Changing IDs — Reference Checks

Before renaming any area ID, entity ID, or automation entity ID, check for references in:

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
