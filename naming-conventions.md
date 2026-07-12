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
5. Groups — use `ha_get_state("group.entity_id")` or `ha_get_state("media_player.group_entity")` to inspect member lists, then `ha_config_set_helper(helper_type="group", ...)` to update. Use `ha_deep_search(query="old_entity_id")` to find any group or script that references the old ID.

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

### Sub-location qualifiers

When a device needs a qualifier to distinguish it from others in the same area (e.g. a Nest Protect positioned outside a specific room within the hallway), append the qualifier in parentheses after the device name:

```
{Area Display Name} - {Device Specific Name} ({Sub-location})
```

Examples:

| Full Name |
|---|
| `Hallway - Nest Protect (Outside Main Bath)` |
| `Hallway - Nest Protect (Outside Tom's Office)` |
| `Hallway - Nest Protect (Ground Floor)` |

Parentheses are dropped during HA slugification, so entity IDs remain clean — `binary_sensor.hallway_nest_protect_outside_main_bath_smoke_status` not `…_outside_main_bath_…`.

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

Two different things are easily confused here, and conflating them silently breaks
dashboards:

| | What it is | Where it lives |
|---|---|---|
| **Entity name** | What the entity measures or controls, on its own | entity registry `name` (user override) / `original_name` (integration default) |
| **`friendly_name`** | What HA actually displays and exports | **computed at runtime**, never stored |

For a modern entity (`has_entity_name: true`) attached to a device, HA composes:

```
friendly_name = "{device name} {entity name}"
```

Since devices are named `{Area} - {Device}`, that composition is what produces the
useful `Kitchen - Netatmo Temperature` seen in dashboards and in the Grafana
`friendly_name` label (see [@observability.md](observability.md)).

**The entity name must therefore be bare** — the area and device are supplied by the
composition, not by the entity:

- **Correct:** `Temperature`, `Battery Level`, `Smoke Status`, `Motion detection`
- **Incorrect:** `Nursery Motion Sensor Temperature`, `Nest Protect (Baby's Room) Smoke Status`

#### ⚠️ A custom `name` override replaces the *whole* composed name

Setting the registry `name` (renaming an entity in the UI, or `ha_set_entity(name=…)`)
makes HA use that string **verbatim** and **drop the `{Area} - {Device}` prefix
entirely**. HA offers no way to override only the entity portion.

| entity | registry `name` | resulting `friendly_name` |
|---|---|---|
| `sensor.kitchen_netatmo_humidity` | *(null)* | `Kitchen - Netatmo Humidity` ✅ |
| `sensor.garage_netatmo_humidity` | `Humidity` | `Humidity` ❌ |

So: **never set a `name` override on a `has_entity_name: true` entity unless the
integration's `original_name` is genuinely wrong.** Such an entity is almost always
*already* compliant — the integration supplies a bare `original_name` — and an
override that merely restates it is a no-op that only serves to strip the prefix. A
sweep in July 2026 found 54 such redundant overrides (`name == original_name`);
all were cleared, restoring the composed names.

**Audit for them:**

```bash
ssh root@homeassistant.local -C 'jq -r ".data.entities[]
  | select(.has_entity_name == true and .name != null and .device_id != null)
  | [.entity_id, .name, (.original_name // \"-\")] | @tsv" /config/.storage/core.entity_registry'
```

Any row where `name == original_name` is redundant. Rows where they differ are a
judgement call: the override buys a tidier entity name at the cost of the area/device
prefix — only worth it when `original_name` is genuinely bad (e.g. `Electric Consumption [W]` → `Power`).

**Clear an override** (reverts to the integration default and restores the prefix):

```bash
hass-cli raw ws config/entity_registry/update \
  --json='{"entity_id":"sensor.foo","name":null}'
```

`ha_set_entity(entity_id, name="")` does the same thing for one-offs; the WebSocket
call above is what to loop over for a bulk sweep.

#### Legacy entities (`has_entity_name: false`)

Older integrations opt out of composition: `friendly_name` is the entity name
verbatim if an override is set, and otherwise whatever the integration builds —
which for some (Hive) means the integration prepends the device name *itself*.

That means neither entity-side lever works when the integration's own name already
repeats a word in the device name: an override strips the area (leaving a useless
`Current Temperature`), and clearing it leaves a stutter. **The fix is to rename the
device so it doesn't duplicate the word the integration already supplies.** The Hive
device was renamed `Hallway - Thermostat` → **`Hallway - Hive`** for exactly this
reason:

| entity | before | after |
|---|---|---|
| `climate.hallway_thermostat` | `Hallway - Thermostat Thermostat` | `Hallway - Hive Thermostat` |
| `sensor.hallway_thermostat_current_temperature` | `Hallway - Thermostat Thermostat Current Temperature` | `Hallway - Hive Thermostat Current Temperature` |

> **Accepted drift:** the entity IDs still carry the old `thermostat` device slug
> (`climate.hallway_thermostat`, not `climate.hallway_hive_thermostat`). Renaming
> them would break every dashboard and automation that references them, for no
> functional gain — the device slug in an entity ID is allowed to lag a device
> rename done purely to fix name composition.

> **Known wart:** this one Hive device also hosts the hot-water entities
> (`*.basement_hotwater_*`), and Hive gives both `climate.hallway_thermostat` and
> `water_heater.hallway_thermostat` an `original_name` of `Thermostat` — so they
> share the display name `Hallway - Hive Thermostat`. Pre-existing; unfixable
> without an override that would strip the prefix again.

Entities with no device at all (e.g. `min_max` helpers like
`sensor.house_temperature`) get no composition either and are out of scope for this
convention.

#### After renaming a device

1. If the entity has a user-set custom name (`name` is not null) that references the old device/area name — **clear it** (above) so it reverts to the integration default and re-composes correctly.
2. Only if the integration's own `original_name` embeds the old device name (e.g. `"Nest Protect (Baby's Room) Smoke Status"`) — **set a custom override** with `ha_set_entity(entity_id, name="Smoke Status")`. Accept that this loses the `{Area} - {Device}` prefix; use an explicit `name:` in dashboard cards to compensate.

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