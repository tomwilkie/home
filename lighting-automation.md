# Lighting automation

Each room combines the following components for occupancy-based lighting with adaptive
brightness and colour temperature:

- **Occupancy group:** one binary sensor that aggregates the area's motion, presence and TV-playing sensors.
- **Lighting automation:** an instance of the `twilkie/motion_lights.yaml` blueprint, which turns the room lights on when the area is occupied and off after a timeout.
- **`room-light` label:** marks the light entities in the area that the automation controls.
- **Adaptive lighting:** a per-area instance that adjusts brightness and colour temperature by time of day and sun position.

## Naming

| Component | Display name | Entity ID | Example |
|---|---|---|---|
| Occupancy group | `{Area Display Name} Occupancy` | `binary_sensor.{area_id}_occupancy` | `binary_sensor.toms_office_occupancy` |
| TV playing helper | `{Area Display Name} TV Playing` | `binary_sensor.{area_id}_tv_playing` | `binary_sensor.living_room_tv_playing` |
| Lighting automation | `{Area Display Name} Lights` | `automation.{area_id}_lights` | `automation.living_room_lights` |
| Adaptive lighting instance | `{Area Display Name}` | `switch.{area_id}_adaptive_lighting` | `switch.toms_office_adaptive_lighting` |

The adaptive lighting integration creates its entities as `switch.adaptive_lighting_{area_id}`.
Rename them area-first, as described in
[_Entity ID format_](naming-conventions.md#entity-id-format).

## Occupancy group membership

Each occupancy group includes the following:

- Every motion sensor in the area
- Every presence sensor in the area, such as the mmWave Everything Presence devices
- A TV playing helper, if the area has a TV or media player, which keeps the lights on while someone watches TV without moving

Add every area occupancy group to the `House Occupancy (Raw)` group.

## `room-light` eligibility

Label a light entity `room-light` if all of the following are true:

1. Its primary purpose is room illumination: lamps, spotlights, dimmers, ceiling lights.
2. It is not a status or indicator light on a device whose primary purpose is something else, such as a smart plug or presence sensor.
3. No conflicting automation governs it, such as a sleep and wake routine in a bedroom.
4. It is in a room where occupancy-based control makes sense, which excludes server racks, garages and utility spaces.

Decorative and accent lights and utility task lights, such as a 3D printer light, have no
exemption. Apply the same rules.

## Adaptive lighting

Each area with `room-light` entities has its own adaptive lighting instance, named after the
area. Its `lights` option lists every `room-light` entity in the area that supports brightness
or colour temperature, and is the only setting that varies by area.

Every instance uses the following non-default values. Settings that are not listed stay at the
integration's defaults. A per-instance difference without a documented reason is configuration
drift.

| Setting | Value | Notes |
|---|---|---|
| `interval` | `90` | Seconds between adaptation updates |
| `transition` | `45.0` | Seconds to transition when adapting |
| `initial_transition` | `1.0` | Seconds for the first transition after turn-on |
| `max_brightness` | `100` | |
| `min_brightness` | `25` | 10% was too dim after the post-sunset ramp bottomed out |
| `min_color_temp` | `2000` | Kelvin |
| `max_color_temp` | `5500` | Kelvin |
| `brightness_mode` | `tanh` | A smooth S-curve that avoids jumps at sunrise and sunset |
| `brightness_mode_time_dark` | `900` | Seconds over which brightness ramps at night |
| `brightness_mode_time_light` | `1800` | Seconds over which brightness ramps by day |
| `min_sunrise_time` | `08:00` | Earliest time treated as sunrise |
| `max_sunset_time` | `21:00` | Latest time treated as sunset, which prevents bright lights on long summer evenings |
| `take_over_control` | `true` | Pause adaptive control when a light is adjusted by hand |
| `take_over_control_mode` | `pause_all` | |
| `autoreset_control_seconds` | `14400` | Resume adaptive control four hours after a manual override |
| `intercept` | `true` | |
| `multi_light_intercept` | `true` | |

### Audit `lights` after a light rename

An entity rename does not reach the `lights` list. Adaptive lighting stores it in config-entry
options, which the entity registry does not rewrite, so the instance keeps pointing at the old
entity IDs. The switch still reports `on` and logs nothing, so a dead instance looks the same as
a working one. The only loud symptom is that the options flow validates `lights` on every save
and rejects any change with `entity_missing`.

After any light rename, read every instance's `lights` and confirm that each ID resolves:

```
ha_get_integration(domain="adaptive_lighting", include_options=True)
```

Repair a stale list in the UI: **Settings**, **Devices & Services**, **Adaptive Lighting**, the
instance, **Configure**. Pick the lights again, and make any other pending change in the same
submit. `ha_set_integration` cannot repair it, because it does not pass a `lights` value into
the flow, so the stored stale list is what the flow validates.

## Intentional exceptions

- **No occupancy automation.** If another automation controls an area's lighting, the area has no `motion_lights` automation. The `room-light` label and adaptive lighting instance still apply. Master Bedroom is such an area, as described in [_Master Bedroom_](#master-bedroom).
- **No adaptive lighting.** A light that is on/off only stays out of the adaptive lighting instance. It still gets the `room-light` label and the occupancy automation.
- **No smart lights.** An area with occupancy sensors and no smart lights has no automation, no adaptive lighting instance and no `room-light` entities. The occupancy sensor serves other purposes, such as heating or security.

### Master Bedroom

The following bespoke automations control the Master Bedroom:

- `turn_bedroom_lights_on_before_sunset` turns the lights on at 20:00 or sunset, whichever is earlier, plays the [sleep sound](wake-routines.md#bedroom-sleep-sound) and closes the shutters.
- `toggle_bedroom_lights` handles the wall switch.
- `turn_off_lights_in_master_bedroom` turns the lights off after 20 minutes with no presence, before sunset only.

"20:00 or sunset, whichever is earlier" is two triggers and one `or` condition that lets only
the earlier trigger through. The `sun` trigger (ID `sunset`) needs `condition: time` before
20:00, and the `time` trigger (ID `eight_pm`) needs `condition: sun` before sunset. Exactly one
run happens each evening. We prefer two triggers with native conditions over one template
trigger. `mode: single` stays, because the routine's `repeat` loop holds the run open until
23:00.

The shutter close is skipped on hot evenings. If the bedroom
(`sensor.master_bedroom_netatmo_temperature`) is more than 1 °C above the house thermostat's
setpoint (the `temperature` attribute of `climate.house_thermostat`) and it is more than 1 °C
cooler outside (the `temperature` attribute of `weather.home`), the windows are presumed open,
and the shutters stay open to be closed by hand at bedtime. Only the `cover.close_cover` step is
guarded. The comparison is a template condition, because `numeric_state` cannot read both
thresholds from entity attributes or apply the 1 °C margin. Its `float()` defaults fail safe: an
unavailable sensor closes the shutters.

## Blueprint management

The blueprint lives at `blueprints/automation/twilkie/motion_lights.yaml` in this repo, which is
the source of truth, and at `/config/blueprints/automation/twilkie/motion_lights.yaml` on Home
Assistant.

1. Check for remote changes. If Home Assistant has changes that are not in this repo, download the live version first:

   ```bash
   diff -u blueprints/automation/twilkie/motion_lights.yaml \
     <(ssh root@homeassistant.local -C "cat /config/blueprints/automation/twilkie/motion_lights.yaml")
   ssh root@homeassistant.local -C "cat /config/blueprints/automation/twilkie/motion_lights.yaml" \
     > blueprints/automation/twilkie/motion_lights.yaml
   ```

2. Edit the file in this repo.
3. Review the outgoing change by running the same `diff` with its arguments swapped.
4. Push to Home Assistant:

   ```bash
   scp blueprints/automation/twilkie/motion_lights.yaml \
     root@homeassistant.local:/config/blueprints/automation/twilkie/motion_lights.yaml
   ```

5. Reload blueprints: **Settings**, **Automations**, **Blueprints**, **Reload**.
6. Commit.

### Without SSH

Claude Code cloud environments have no `ssh` or `scp` and no route to the home LAN. The MCP
server covers the same steps:

| Step | MCP equivalent |
|---|---|
| Read the live file | `ha_manage_blueprints(action="get", path="twilkie/motion_lights.yaml")`. Check that `yaml_source` is `file`. |
| Push and reload | `ha_manage_blueprints(action="save", path=…, yaml=…, overwrite=True)`, which writes the file and reloads every automation that uses it |

Before a blueprint edit touches the live automations, test it:

1. `save` it to a path that nothing consumes, for example `twilkie/motion_lights_preflight.yaml`. Home Assistant validates the blueprint schema on `save`.
2. Render it against each room's real inputs with `ha_manage_blueprints(action="substitute", path=…, input={…})`, which resolves every `!input`. Render one `use_sun: true` room and one `use_sun: false` room.
3. `delete` the test copy with `confirm=True`, then `save` over the real path.

`save` normalises the file. It parses the YAML and dumps it again, so the copy on disk loses
every comment, expands selectors, floats numbers and changes quoting. The semantics are
unchanged, but the textual `diff` in step 1 no longer comes back clean. Compare the rendered
`config` object or the `substitute` output instead. To restore the commented copy, `scp` this
repo's file over it from a machine with LAN access.

## Blueprint reference

`twilkie/motion_lights.yaml` is titled "Motion Activated Light (with brightness, sun & labels)"
and takes the following inputs:

| Input | Description | Default | Standard |
|---|---|---|---|
| `motion_entity` | The occupancy group binary sensor | required | required |
| `area_id` | Area whose lights to control | required | required |
| `label_filter` | Only control lights with this label | none | `room_light` |
| `no_motion_wait` | Seconds to leave lights on after last motion | 120 | 1800 |
| `use_sun` | Only control lights at night, turn them on when the night window opens and off when it closes | false | per room |
| `sunrise_offset` | Offset from sunrise (positive is after) | 00:00:00 | 01:00:00 if `use_sun` |
| `sunset_offset` | Offset from sunset (positive is after) | 00:00:00 | -01:00:00 if `use_sun` |
| `use_brightness` | Only turn on lights when the room is dark | false | false |
| `brightness_entity` | Illuminance sensor for the darkness check | none | none |
| `brightness_trigger` | Maximum lux level to trigger lights | 20 | 20 |

`use_sun` is a per-room decision. With the standard offsets, the night window opens one hour
before sunset and closes one hour after sunrise.

### Triggers

The blueprint has the following triggers:

| Trigger ID | Fires when | Gated by |
|---|---|---|
| `occupied` | The occupancy group goes `off` to `on` | nothing |
| `darkness_fell` | `sunset + sunset_offset` | `enabled: !input use_sun` |
| `daylight` | `sunrise + sunrise_offset` | `enabled: !input use_sun` |

`occupied` and `darkness_fell` share one condition, that the occupancy group is `on`, which sits
ahead of the brightness and sun conditions. `daylight` bypasses all of them: it turns the
`room-light` lights off and stops.

- **`darkness_fell` turns the lights on for a room that is already occupied when the window opens.** With `use_sun` as a condition alone, the only way in is an `off` to `on` occupancy edge. Someone who sits down before the window opens produces no further edge, so the lights stay off all evening. Living Room is the worst case, because `binary_sensor.living_room_tv_playing` holds occupancy `on` for hours.
- **`daylight` turns the lights off for a room that is still occupied when the window closes.** The turn-off otherwise waits for the occupancy group to stay `off` for `no_motion_wait`, and a playing TV can hold it `on` all morning. It turns off any `room-light` that is on at that moment, including one switched on by hand on a dark morning. It fires once a day, so a light switched on later stays on until the room empties.
- **Native triggers, not one template trigger.** This is the same choice as the Master Bedroom automation.
- **`mode: restart` is safe.** Home Assistant evaluates conditions before it stops the previous run, so a `darkness_fell` firing into an empty room does nothing and cannot cancel a pending turn-off. `daylight` always passes, and cancelling the pending turn-off is what it wants. The occupancy condition also closes a race on the `occupied` trigger, where the group flickers back to `off` before the run starts.

### Known gaps

- **`unavailable` to `on` is not a trigger.** The occupancy groups go `unavailable` at every 04:00 restart and on sensor dropouts. A bare `to: "on"` trigger would catch those and switch the lights on at 04:00 in an occupied dark room, so the narrow `from: "off"` stays.
- **`use_brightness` has the same gap as `use_sun` had:** a room that darkens around someone already in it. No room sets it, so the blueprint has no lux-threshold trigger.
- **Rooms without `use_sun` have no daylight turn-off.** In Basement and Tom's Office the lights go off only on the `no_motion_wait` timeout.
