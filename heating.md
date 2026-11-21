# Heating

This document covers how Home Assistant controls the central heating: the house thermostat, the
relay that drives the Hive thermostat, and the automation that picks the target temperature.

## House thermostat

`climate.house_thermostat` is a `generic_thermostat` defined in `configuration.yaml` on the Home
Assistant host. Edit it with `ha_config_set_yaml(yaml_path="climate")`, then call
`generic_thermostat.reload`. No restart is needed.

| Setting | Value | Notes |
|---|---|---|
| `heater` | `switch.heating_relay` | See [_Heating relay_](#heating-relay) |
| `target_sensor` | `sensor.hallway_thermostat_temperature` | The Hive thermostat's own reading. A template sensor helper on the `current_temperature` attribute of `climate.hallway_thermostat`, because `generic_thermostat` reads a sensor's state, not an attribute, and the Hive fork exposes no temperature sensor. |
| `min_temp` / `max_temp` | 15 / 23 | `max_temp` must stay below the relay's "on" setpoint |
| `away_temp` | 15 | Matches the relay's "off" setpoint |
| `cold_tolerance` / `hot_tolerance` | 0.3 / 0.1 | Heats below target − 0.3, stops at target + 0.1 |
| `min_cycle_duration` | 30 minutes | Protects the boiler and limits Hive cloud calls |

`away` is the only preset. The comfort and sleep targets are the `input_number` helpers
`input_number.house_comfort_temperature` and `input_number.house_sleep_temperature` (16 to 23 °C
in 0.5 °C steps), which are on the Settings view of the Settings dashboard, because
`generic_thermostat` reads its preset temperatures from YAML at load and has no service to change
them. The thermostat's `preset_mode` reads `none` in comfort and sleep.

Keep the helpers' minimum above `away_temp`. `generic_thermostat` reports the preset whose
temperature matches the target, so a comfort or sleep target of 15 °C would read as `away`.

## Heating relay

`switch.heating_relay` is a template switch in `configuration.yaml`. It does not switch the
boiler. It makes one `climate.set_temperature` call on the Hive thermostat
(`climate.hallway_thermostat`) with `hvac_mode: heat` and the setpoint. The `tomwilkie/ha-hive`
fork sends the mode to Hive first and then the setpoint, so a separate `climate.set_hvac_mode`
step only doubles the cloud calls, and each extra call is one more that Hive can refuse:

| Relay | Hive setpoint |
|---|---|
| On | 24 °C |
| Off | 15 °C |

- **"On" sits above `max_temp`.** Hive runs its own control loop, so the "on" setpoint is a ceiling on the room. When it was 21 °C, any target above 21 °C was unreachable and the two thermostats disagreed at 21 °C. If you raise `max_temp`, raise the "on" setpoint and the `state` threshold with it.
- **"On" is also the failsafe.** If Home Assistant dies with the relay on, Hive keeps heating to the "on" setpoint and no further.
- **The relay reports `unavailable` when Hive does.** Its `availability` template follows `climate.hallway_thermostat`. Without it, a Hive outage read as "off", and the thermostat believed it still had control.
- **Keep the Hive thermostat in `heat` mode, not `auto`.** In `auto` the Hive schedule would fight Home Assistant.

Home Assistant retries a Hive setup that fails after the 04:00 restart, as described in
[_Hive_](maintenance.md#hive).

## Thermostat automation

`automation.set_thermostat_state` sets the thermostat from presence and
`schedule.house_comfort_mode`:

| Mode | Action | When |
|---|---|---|
| Away | The `away` preset | `zone.home` has been `0` and `binary_sensor.house_occupancy` `off` for an hour |
| Comfort | Target from `input_number.house_comfort_temperature` | Otherwise, while the schedule is `on` |
| Sleep | Target from `input_number.house_sleep_temperature` | Otherwise, while the schedule is `off` |

It does nothing while the thermostat is `off`.

- **It acts on transitions only, so a manual change lasts until the next one.** The triggers are a schedule change, the house empty for an hour, a return from away, Home Assistant starting, and a change to either temperature helper. A helper change acts only when its mode is the active one, so moving the sleep slider during comfort hours does nothing until the schedule turns off. An hourly re-assert used to undo manual changes within the hour, which is why the automation was once disabled.
- **A return only acts when the preset is `away`.** Occupancy flips `on` many times a day, and acting on each flip would undo manual changes.
- **The away triggers carry `for: 1h`, and so do the away conditions.** Either dwell can finish first, so each trigger re-checks both.
- **At startup the away check drops the dwell.** A restart resets `last_changed`, so `for: 1h` cannot pass. Without this branch, the 04:00 restart of an empty house would switch it out of away for good.
- **`mode: restart`.** The zone and occupancy triggers can fire together, and every branch reads current state, so the latest run is the right one.

### Two definitions of away

`automation.update_house_state` sets `input_select.house_state` to `Away` after 24 hours
without occupancy. The heating uses one hour without occupancy and with nobody in `zone.home`.
The difference is deliberate: the heating should drop back for an afternoon out, while
`house_state` marks a trip away.

The `Away` branch reads `sensor.house_occupancy_last_24h` below `0.01` hours, not a state
condition with `for: 24h`, because the 04:00 restart resets `last_changed` and the `for:` timer
with it (see [_2026-10-30: house state never reached Away_](history.md#2026-10-30-house-state-never-reached-away)).
The sensor is described in [_Evening hot water_](wake-routines.md#evening-hot-water).
