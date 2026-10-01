# Home Assistant naming conventions

Areas, devices, entities, automations and labels follow the conventions in this document. Entity
IDs are area-first, and display names are bare, so that Home Assistant composes
`{Area} - {Device} {Entity}` for dashboards and Grafana.

## Areas

Area IDs are slugified from the display name: lower case, spaces to underscores, and apostrophes
dropped.

| Display name | `area_id` |
|---|---|
| Basement | `basement` |
| Tom's Office | `toms_office` |
| Front Guest Room | `front_guest_room` |

Home Assistant generates area IDs differently: an apostrophe becomes `_s_`. To create an area
whose name contains an apostrophe, create it with a plain name ("Toms Office") to get the slug,
then change the display name ("Tom's Office").

## Devices

Name a device `{Area Display Name} - {Device Specific Name}`: the area display name as written,
including apostrophes, then a space, a hyphen and a space, then the name that identifies the
device within the area.

| Area | Device | Full name |
|---|---|---|
| Kitchen | Netatmo | `Kitchen - Netatmo` |
| Tom's Office | Roomba | `Tom's Office - Roomba` |
| Master Bedroom | Lamp Tom's | `Master Bedroom - Lamp Tom's` |

To distinguish devices of the same kind in one area, append a qualifier in parentheses:
`Hallway - Nest Protect (Outside Main Bath)`, `Hallway - Nest Protect (Ground Floor)`. Home
Assistant drops parentheses when it slugifies, so the entity ID stays clean:
`binary_sensor.hallway_nest_protect_outside_main_bath_smoke_status`.

The convention applies to every device with an assigned area, whatever its type. Devices without
an area, such as Home Assistant Core and HACS, are out of scope.

## Entities

### Entity ID format

Entity IDs follow `{domain}.{area_id}_{device_slug}_{measurement}`:

| Entity ID | Area | Device | Measurement |
|---|---|---|---|
| `sensor.kitchen_netatmo_pressure` | `kitchen` | netatmo | pressure |
| `sensor.toms_office_motion_sensor_temperature` | `toms_office` | motion_sensor | temperature |
| `binary_sensor.nursery_motion_sensor_occupancy` | `nursery` | motion_sensor | occupancy |

- **The area comes first for every entity,** including the ones that integrations create, such as adaptive lighting switches and template helpers. When an integration creates an entity with the area elsewhere (`switch.adaptive_lighting_living_room`), rename it with `ha_set_entity(new_entity_id=...)`.
- **Entities on a device without an area are out of scope.**
- **A `device_tracker` entity from a network-scanning integration** follows the convention only if its device has an area. Leave a bare network client as it is.

### Display names

The entity name and the `friendly_name` are different things:

| | What it is | Where it lives |
|---|---|---|
| Entity name | What the entity measures or controls | Entity registry `name` (user override) or `original_name` (integration default) |
| `friendly_name` | What Home Assistant displays and exports | Computed at runtime |

For an entity with `has_entity_name: true` on a device, Home Assistant composes
`friendly_name = "{device name} {entity name}"`. Because devices are named `{Area} - {Device}`,
the composition produces `Kitchen - Netatmo Temperature`, which is also the Grafana
`friendly_name` label.

The entity name must therefore be bare: `Temperature`, `Battery Level`, `Smoke Status`, not
`Nursery Motion Sensor Temperature`.

### Don't override a name that is already bare

A registry `name` override replaces the whole composed name. Home Assistant uses the string
verbatim and drops the `{Area} - {Device}` prefix:

| Entity | Registry `name` | `friendly_name` |
|---|---|---|
| `sensor.kitchen_netatmo_humidity` | none | `Kitchen - Netatmo Humidity` |
| `sensor.garage_netatmo_humidity` | `Humidity` | `Humidity` |

Set a `name` override on a `has_entity_name: true` entity only when the integration's
`original_name` is wrong: it embeds an area or old device name (`Adaptive Lighting: Living Room`
becomes `Adaptive Lighting`), or it is unreadable (`Electric Consumption [W]` becomes `Power`).
The override costs the prefix, so compensate with an explicit `name:` on the dashboard card:

```yaml
entities:
  - entity: switch.living_room_adaptive_lighting
    name: Living Room
```

An override that restates `original_name` only strips the prefix. To find overrides, run the
following, and clear every row where `name` equals `original_name`:

```bash
ssh root@homeassistant.local -C 'jq -r ".data.entities[]
  | select(.has_entity_name == true and .name != null and .device_id != null)
  | [.entity_id, .name, (.original_name // \"-\")] | @tsv" /config/.storage/core.entity_registry'
```

To clear an override, use `ha_set_entity(entity_id, name="")` for one entity, or the WebSocket
call in a loop for many:

```bash
hass-cli raw ws config/entity_registry/update \
  --json='{"entity_id":"sensor.foo","name":null}'
```

### Legacy entities

An older integration with `has_entity_name: false` opts out of composition. The `friendly_name`
is the override if one is set, and otherwise whatever the integration builds. Hive prepends the
device name itself.

When such an integration's own name repeats a word in the device name, neither entity-side
option works: an override strips the area, and clearing it leaves a stutter. Rename the device
so that it does not repeat the word. The Hive device is named `Hallway - Hive`, not
`Hallway - Thermostat`, so that `climate.hallway_thermostat` displays as
`Hallway - Hive Thermostat`.

- **The Hive entity IDs keep the `thermostat` device slug** (`climate.hallway_thermostat`). A device slug in an entity ID can lag a device rename that was made to fix name composition, because renaming the IDs would break every consumer for no functional gain.
- **`climate.hallway_thermostat` and `water_heater.hallway_thermostat` share a display name.** The one Hive device hosts the heating and the hot water entities (`*.basement_hotwater_*`), and Hive gives both an `original_name` of `Thermostat`. An override would strip the prefix.

Entities with no device, such as the `min_max` helper `sensor.house_temperature`, get no
composition and are out of scope.

### After you rename a device

1. If an entity has a `name` override that references the old device or area name, clear it, so that the name composes again.
2. If the integration's `original_name` embeds the old device name (`Nest Protect (Baby's Room) Smoke Status`), set a bare override with `ha_set_entity(entity_id, name="Smoke Status")`.
3. For a Zigbee device, sync the friendly name in zigbee2mqtt, as described in [zigbee2mqtt-sync.md](zigbee2mqtt-sync.md).

## After you rename an entity

An entity ID rename does not reach the things that reference it. To find references, run
`ha_search(query="old.entity_id")` with the exact old ID, then update each of the following:

1. Dashboard cards. `ha_config_get_dashboard(entity_id=...)` finds them.
2. Automations
3. Template helpers whose `state` template references the old ID
4. Scripts
5. Groups. Read the member list with `ha_get_state("group.entity_id")` or `ha_get_state("media_player.group_entity")`, and update it with `ha_config_set_helper(helper_type="group", ...)`.
6. Config-entry options. The entity registry does not rewrite them, and `ha_search` does not read them. The adaptive lighting `lights` list is the known case: see [_Audit `lights` after a light rename_](lighting-automation.md#audit-lights-after-a-light-rename).

## Automations

An automation's entity ID is its alias, slugified by the area ID rules: lower case, spaces and
` - ` separators to underscores, apostrophes and other special characters dropped.

| Alias | `entity_id` |
|---|---|
| "Basement Lights" | `automation.basement_lights` |
| "Tom's Office Lights" | `automation.toms_office_lights` |
| "Living Room - Manual" | `automation.living_room_manual` |
| "Notify on Tumble Drier finished" | `automation.notify_on_tumble_drier_finished` |

Home Assistant generates the entity ID from the alias at creation, with its own slugification,
which maps an apostrophe to `_s_`. Renaming the alias later does not update the entity ID. In
both cases, fix the ID with `ha_set_entity(new_entity_id=...)`.

## Labels

A label's display name is kebab-case (`room-light`, `restart-daily`), and Home Assistant
slugifies it to a snake_case `label_id` (`room_light`, `restart_daily`).

Give every label a `description` that says what applying it does. A label is an interface to an
automation, and the description is the only place the UI shows that contract. Say in the
description whether the label goes on the device or the entity:

- **Label the entity** when the automation acts on that entity and a sibling entity would be wrong to touch. `room-light` marks individual light entities.
- **Label the device** when the automation needs to find related entities on the same device, such as a restart button and the media player that says whether the device is busy. `restart-daily` in [maintenance.md](maintenance.md) works this way.

A device label passed to `target: {label_id: …}` expands to every matching entity on that
device. When you label devices, the automation must iterate them in a template and select the
intended entity, typically by `device_class`.

The converse does not hold: `label_entities()` returns only entities that are labelled directly.
A label on a device does not roll down to its entities.
