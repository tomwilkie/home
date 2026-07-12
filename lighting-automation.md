# Lighting Automation

## Overview

Each room uses a four-component pattern for occupancy-based lighting with adaptive brightness and colour temperature:

1. **Occupancy Group** — aggregates all motion, presence, and TV-playing sensors into a single binary sensor for the area.
2. **Lighting Automation** — an instance of the `twilkie/motion_lights.yaml` blueprint that turns room lights on when the area is occupied and off after a timeout.
3. **`room-light` Label** — marks which light entities in the area are controlled by automation.
4. **Adaptive Lighting** — a per-area instance that continuously adjusts brightness and colour temperature of capable lights based on time of day and sun position.

---

## Naming Conventions

### Occupancy Groups

| | Format | Example |
|---|---|---|
| Display name | `{Area Display Name} Occupancy` | `Tom's Office Occupancy` |
| Entity ID | `binary_sensor.{area_id}_occupancy` | `binary_sensor.toms_office_occupancy` |

### TV Playing Helpers

| | Format | Example |
|---|---|---|
| Display name | `{Area Display Name} TV Playing` | `Living Room TV Playing` |
| Entity ID | `binary_sensor.{area_id}_tv_playing` | `binary_sensor.living_room_tv_playing` |

### Lighting Automations

| | Format | Example |
|---|---|---|
| Display name (alias) | `{Area Display Name} Lights` | `Living Room Lights` |
| Entity ID | `automation.{area_id}_lights` | `automation.living_room_lights` |

### Adaptive Lighting Instances

| | Format | Example |
|---|---|---|
| Instance name | `{Area Display Name}` | `Tom's Office` |
| Main switch entity ID | `switch.adaptive_lighting_{area_id}` | `switch.adaptive_lighting_toms_office` |

---

## Occupancy Group Membership

Each Occupancy group should include:

1. **All motion sensors** in the area
2. **All presence sensors** in the area (e.g. mmWave / Everything Presence devices)
3. **A TV playing helper** (`binary_sensor.{area_id}_tv_playing`) if the area has a TV or media player — this keeps lights on while watching TV even when no motion is detected

Every area Occupancy group must also be added as a member of the **`House Occupancy (Raw)`** group.

---

## room-light Eligibility Rules

Tag a light entity `room-light` if ALL of the following are true:

1. Its primary purpose is room illumination (lamps, spotlights, dimmers, ceiling lights)
2. It is **not** a status or indicator light on a device whose primary purpose is something else (e.g. a smart plug, presence sensor, or other appliance)
3. It is **not** already governed by a conflicting automation (e.g. a sleep/wake routine in a bedroom)
4. It is in a room where occupancy-based control makes sense (not server racks, garages, or utility spaces)

Decorative/accent lights and utility task lights (e.g. a 3D printer light) have no special exemption — apply the four rules above as normal.

---

## Adaptive Lighting

Each area that has `room-light` entities should have its own dedicated adaptive lighting instance, named after the area. Include any `room-light` entity that supports brightness or colour temperature control.

All instances should use identical settings — do not customise per-instance unless there is a specific documented reason. Divergence from the defaults is treated as configuration drift.

### Standard Settings

The table below lists every non-default value that all instances must share. Settings not listed here are left at the adaptive lighting integration's built-in defaults.

| Setting | Value | Notes |
|---|---|---|
| `interval` | `90` | Seconds between adaptation updates |
| `transition` | `45.0` | Seconds to transition when adapting |
| `initial_transition` | `1.0` | Seconds for first transition after turn-on |
| `max_brightness` | `100` | |
| `min_color_temp` | `2000` | Kelvin |
| `max_color_temp` | `5500` | Kelvin |
| `min_brightness` | `10` | |
| `brightness_mode` | `tanh` | Smooth S-curve; avoids harsh jumps at sunrise/sunset |
| `brightness_mode_time_dark` | `900` | Seconds over which brightness ramps at night |
| `brightness_mode_time_light` | `1800` | Seconds over which brightness ramps at day |
| `min_sunrise_time` | `08:00` | Earliest time adaptive lighting treats as sunrise |
| `max_sunset_time` | `21:00` | Latest time adaptive lighting treats as sunset (prevents bright lights on long summer evenings) |
| `take_over_control` | `true` | Pause adaptive control when lights are manually adjusted |
| `take_over_control_mode` | `pause_all` | |
| `autoreset_control_seconds` | `14400` | Auto-resume adaptive control 4 hours after manual override |
| `intercept` | `true` | |
| `multi_light_intercept` | `true` | |

### Per-Instance Settings

The only setting that varies by area is `lights` — the `room-light` entities for that area.

---

## Intentional Exceptions

Some areas may be intentionally excluded from parts of the pattern:

- **No occupancy automation**: If an area's lighting is already controlled by another automation (e.g. a sleep/wake routine), it should not also have a `motion_lights` automation. The `room-light` label and adaptive lighting instance still apply to eligible lights in that area.
  - **Master Bedroom** is the current exception. It is controlled by three bespoke automations: `turn_bedroom_lights_on_before_sunset` (turns lights on at sunset, plays music, closes the shutters), `toggle_bedroom_lights` (wall-switch toggles), and `turn_off_lights_in_master_bedroom` (turns lights off after 20 min no presence, but only before sunset). Adaptive lighting uses `switch.adaptive_lighting_master_bedroom`.

    > The shutter close is **skipped on hot evenings**: if the bedroom is more than 1 °C above the house thermostat's setpoint (`climate.house_thermostat`'s `temperature` attribute) *and* it is more than 1 °C cooler outside (`weather.home`'s `temperature` attribute) than in the room (`sensor.master_bedroom_netatmo_temperature`), the windows are presumed open to cool the room, and the shutters are left open to be closed by hand with the windows at bedtime. Only the `cover.close_cover` step is guarded — the lights and music still run. The comparison is a template condition rather than `numeric_state` because both thresholds are entity *attributes* (which `numeric_state`'s entity-reference form cannot read) and neither can carry the ±1 °C margin. Its `float()` defaults fail safe: any unavailable sensor closes the shutters as before.
- **No adaptive lighting**: If a light is on/off only with no brightness or colour control, exclude it from the adaptive lighting instance. It still gets the `room-light` label and is controlled by the occupancy automation.
- **No smart lights**: Some areas have occupancy sensors but no smart light entities. These areas have no automation, no adaptive lighting instance, and no `room-light` labelled entities — the occupancy sensor exists for other purposes (e.g. presence-based heating or security).

---

## Blueprint Management

The blueprint lives at `blueprints/automation/twilkie/motion_lights.yaml` in this repo. This repo is the **source of truth** — all edits must be made here, then uploaded to HA.

### File path on HA

```
/config/blueprints/automation/twilkie/motion_lights.yaml
```

### Workflow

1. **Check for remote changes** before editing — if HA has changes not in this repo, pull them first:
   ```bash
   diff -u blueprints/automation/twilkie/motion_lights.yaml \
     <(ssh root@homeassistant.local -C "cat /config/blueprints/automation/twilkie/motion_lights.yaml")
   ```
   If there are differences, download the live version before proceeding:
   ```bash
   ssh root@homeassistant.local -C "cat /config/blueprints/automation/twilkie/motion_lights.yaml" \
     > blueprints/automation/twilkie/motion_lights.yaml
   ```
2. Edit `blueprints/automation/twilkie/motion_lights.yaml` in this repo
3. Diff to review your outgoing change:
   ```bash
   diff -u <(ssh root@homeassistant.local -C "cat /config/blueprints/automation/twilkie/motion_lights.yaml") \
     blueprints/automation/twilkie/motion_lights.yaml
   ```
4. Push to HA:
   ```bash
   scp blueprints/automation/twilkie/motion_lights.yaml \
     root@homeassistant.local:/config/blueprints/automation/twilkie/motion_lights.yaml
   ```
5. Reload blueprints in HA (Settings → Automations → Blueprints → Reload, or restart HA)
6. Commit to git

---

## Blueprint Reference

**`twilkie/motion_lights.yaml`** — "Motion Activated Light (with brightness, sun & labels)"

| Input | Description | Default | Standard |
|---|---|---|---|
| `motion_entity` | The Occupancy group binary sensor | required | required |
| `area_id` | Area whose lights to control | required | required |
| `label_filter` | Only control lights with this label | none | `room_light` |
| `no_motion_wait` | Seconds to leave lights on after last motion | 120 | **1800** |
| `use_sun` | Only control lights at night | false | per-room |
| `sunrise_offset` | Offset from sunrise (positive = after) | 00:00:00 | **01:00:00** (if use_sun) |
| `sunset_offset` | Offset from sunset (positive = after) | 00:00:00 | **-01:00:00** (if use_sun) |
| `use_brightness` | Only turn on lights when room is dark | false | false |
| `brightness_entity` | Illuminance sensor for darkness check | none | none |
| `brightness_trigger` | Maximum lux level to trigger lights | 20 | 20 |

`use_sun` is decided per room. When enabled, always set `sunrise_offset: 01:00:00` and `sunset_offset: -01:00:00` so lights activate one hour before sunset and deactivate one hour after sunrise.
