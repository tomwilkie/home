# Home Assistant Naming Conventions

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

## Areas

### Area IDs

Area IDs are slugified from the display name using these rules:

- Spaces → underscores (`_`)
- Apostrophes → **dropped** (not replaced with `_`)
- Everything lowercase

Examples:

| Display Name | area_id |
|---|---|
| Basement | `basement` |
| Tom's Office | `toms_office` |
| Nursery | `nursery` |
| Front Guest Room | `front_guest_room` |

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

- Entities on devices without an area assignment are excluded from this convention
- `device_tracker.*` entities from network-scanning integrations (e.g. UniFi, etc.) follow a conditional rule: if the entity's device has an area assigned in HA, rename it per this convention; if the device has no area (bare network client with no HA counterpart), leave it as-is.

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

Automation entity IDs are slugified from the alias (display name) using the same rules as [area IDs](#area-ids):

- Lowercase, spaces → underscores
- Apostrophes → dropped (not `_s_`)
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

## Zigbee2MQTT sync

After renaming HA devices, sync the friendly names in zigbee2mqtt to match. See [@zigbee2mqtt-sync.md](zigbee2mqtt-sync.md) for the step-by-step procedure.