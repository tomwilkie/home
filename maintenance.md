# Device maintenance

This document covers two schemes. The scheduled restart sweep restarts devices that degrade with
uptime, driven by labels on devices rather than a hardcoded entity list. The
[integration watchdogs](#integration-watchdogs) are its reactive counterpart: they reload a
config entry that has wedged.

## Scheduled restarts

ESPHome voice assistants develop choppy, delayed audio after long uptimes. The response is
computed quickly, but playback stutters, arrives late, or the device stays in `responding` with
no audio. This is an upstream failure mode caused by
[ESP32 heap fragmentation](https://hubble.com/community/guides/esp32-memory-fragmentation-why-your-device-crashes-after-running-for-days/):
free heap remains, but no contiguous block large enough for an audio buffer. The upstream
reports include [Voice PE stuck in `responding`](https://github.com/esphome/home-assistant-voice-pe/issues/382)
and [20-second delays before playback](https://github.com/esphome/home-assistant-voice-pe/issues/257).

A periodic reboot treats the symptom and hides a diagnosable fault. The cadences are judgement
calls, not measurements, as [_Known gaps_](#known-gaps) explains.

### How it works

`automation.scheduled_device_restarts` (Maintenance category) fires at 04:30 and presses the
restart button on every device labelled for that day's cadence. To add a device to the schedule,
apply one label. The automation needs no edit.

Apply the labels to devices, not entities:

| Label | `label_id` | Fires |
|---|---|---|
| `restart-daily` | `restart_daily` | Every day |
| `restart-weekly` | `restart_weekly` | Mondays |
| `restart-monthly` | `restart_monthly` | The first Monday of the month |

A device with no label is not restarted, so an adopted device is inert until it is labelled.

- **Target:** for each labelled device, the automation selects the entity whose `device_class` is `restart`. Every ESPHome reboot button carries that class, and `factory_reset_mmwave_sensor`, `reboot_mmwave_sensor`, `apply_update` and `sync_time` carry no device class, so the automation cannot select them.
- **Guard:** the automation skips a device if any entity on it is in use: a `media_player` that is `playing`, a `vacuum` that is `cleaning` or a `fan` that is `on`. The guard entity lives on the same device as the restart button, so there is no per-device configuration. A skipped device is not retried until its next scheduled night.
- **Stagger:** presses are 20 seconds apart, so the fleet does not drop off WiFi at once.

Don't label the button entity, and don't use `target: {label_id: …}`. A device label passed to a
`button.press` target expands to every button on that device, which on an Everything Presence
Lite includes `factory_reset_mmwave_sensor`. The automation iterates devices in a template and
selects the button instead.

### Assignment

| Cadence | Devices | Rationale |
|---|---|---|
| Daily | The Voice Assistants, Hallway - Doorbell, and the Living Room and Tom's Office Arylic LP10s | The reported audio fault. The doorbell must not be wedged. |
| Weekly | Kitchen - Boiler Monitor | The weakest WiFi link in the fleet (−76 dBm) |
| Monthly | Master Bedroom - Clock and the Everything Presence Lites | No known fault. The presence sensors drive occupancy and lighting, so churn is worth minimising. |

### Timing

Other Maintenance automations box the 04:30 slot in on both sides. Check the following before
you move it:

| Time | Automation | Interaction |
|---|---|---|
| 04:00 | `automation.restart_home_assistant_at_4am_every_day` | Bounces every ESPHome connection. The sweep needs it finished first. |
| 04:30 | `automation.scheduled_device_restarts` | Takes about five minutes with every device due |
| 04:45 | `automation.restart_kitchen_display_browser` | Clears the Fully Kiosk WebView |
| 05:30 | `automation.update_esphome_devices` | Flashes firmware with three-minute waits per device, and must not be interrupted |
| 06:00 | `automation.set_assistant_volumes` | Runs after the sweep, so it re-applies any volume that a restart disturbs |

The 04:00 restart is also what strands Netatmo and Hive, as described in
[_Integration watchdogs_](#integration-watchdogs).

### Related automations

- **`automation.restart_kitchen_display_browser` is separate from this scheme.** It presses `button.kitchen_display_restart_browser` to clear the Fully Kiosk WebView, which leaks memory while it renders the kitchen dashboard's camera streams (see [dashboards.md](dashboards.md#keep-background-false-on-the-camera-cards)). The Kitchen Display exposes two `device_class: restart` buttons, `restart_browser` and `restart_device`, so the target selection cannot choose between them, and the wrong choice would reboot the tablet nightly.
- **`automation.power_cycle_dyson_fan` is separate from this scheme.** At 00:00 it cuts mains power for 10 seconds at `switch.master_bedroom_switch_dyson_fan`, a Z-Wave metering plug, and its guard reads `fan.master_bedroom_dyson_fan`, which is a different device. No label can express "this plug powers that fan".
- **Nursery - WiiM Sound has no restart button.** The `wiim` integration exposes only a `media_player`. The only way to reboot it from Home Assistant is the undocumented HTTP command `curl -sk "https://192.168.2.10/httpapi.asp?command=StartRebootTime:1"`, which would need a `rest_command` automation rather than a label. The speaker's firmware does not implement the `reboot` command that the `linkplay` integration sends.
- **A `linkplay` config entry for the WiiM is parked as ignored.** Zeroconf rediscovers the speaker within seconds, and deleting the ignored entry brings back a duplicate device alongside the `wiim` one.

### Add a device

1. Confirm that the device has exactly one entity with `device_class: restart`. If the following template returns more than one entity, this scheme cannot choose between them:

   ```jinja
   {{ device_entities(device_id('button.your_device_restart'))
      | select('match','button\.')
      | select('is_state_attr','device_class','restart') | list }}
   ```

2. Apply one cadence label to the device: **Settings**, **Devices**, the device, **Add label**, or `ha_set_device(device_id=…, labels=["restart_weekly"])`. `ha_set_device` replaces the label list, so read the existing labels first.
3. Confirm that it appears in the bucket with `{{ label_devices('restart_weekly') }}`.

A Voice PE restart button can ship `disabled_by: integration`. Enable it and reload the config
entry before the entity appears in the state machine.

### Verify

Run these checks after you change labels, the automation or the fleet.

**The buckets resolve to the right buttons.** If a label is attached to an entity rather than a
device, `label_devices()` returns nothing and the sweep does nothing, with no error. Compare the
output of the following template with the assignment table, and confirm that no
`factory_reset_mmwave_sensor`, `sync_time` or `apply_update` button appears:

```jinja
{% macro targets(label) %}
{%- set ns = namespace(t=[]) -%}
{%- for d in label_devices(label) -%}
  {%- if device_entities(d) | select('match','media_player\.|vacuum\.|fan\.')
         | select('is_state',['playing','cleaning','on']) | list | count == 0 -%}
    {%- set ns.t = ns.t + (device_entities(d) | select('match','button\.')
         | select('is_state_attr','device_class','restart')
         | reject('is_state','unavailable') | list) -%}
  {%- endif -%}
{%- endfor -%}
{{ ns.t | count }} -> {{ ns.t }}
{% endmacro %}
DAILY:   {{ targets('restart_daily') }}
WEEKLY:  {{ targets('restart_weekly') }}
MONTHLY: {{ targets('restart_monthly') }}
```

**The guard discriminates.** A busy filter can match nothing without any error. The following
template lists everything in the house that matches it. If it is non-empty while the buckets are
full, the filter is live:

```jinja
{{ states | map(attribute='entity_id') | select('match','media_player\.|vacuum\.|fan\.')
   | select('is_state',['playing','cleaning','on']) | list }}
```

**A press reaches the device.** The button's state is a timestamp that updates even when the
underlying call fails. Check an uptime sensor instead, such as `sensor.hallway_doorbell_uptime`,
or watch the device's `media_player` blip `unavailable` in `ha_get_history`.

**The cadence branches gate correctly.** Trigger the automation by hand and read the trace with
`ha_get_automation_traces("automation.scheduled_device_restarts")`. On a day other than Monday,
the weekly and monthly `if` blocks show `result: false`.

### Accepted deviations

`ha_config_set_automation` raises two warnings against this automation. Both are deliberate:

- **Templated `target.entity_id`** (`{{ repeat.item }}`). This is the `repeat.for_each` idiom, and hardcoded literals would defeat a label-driven list. The list comes from the live registry, the template rejects `unavailable` entities, and `continue_on_error: true` contains a failed press.
- **`{{ now().day <= 7 }}` date condition.** A state condition is equality-based and cannot express "day of month at most 7", and Home Assistant has no native day-of-month condition. The step carries an inline `alias` that says so.

The automation uses `label_devices()`, `device_entities()` and `device_id()`, which resolve at
render time. That is the exception for Jinja `device_id(...)` calls in the
[entity ID rule](CLAUDE.md#entity-ids-not-device-ids): the automation hardcodes no IDs.

Deliberate reboots do not trip ESPHome's [`safe_mode`](https://esphome.io/components/safe_mode/),
because its failure counter resets after `boot_is_good_after: 1min`.

### Known gaps

- **No telemetry backs the cadences.** The ESPHome [`debug` component](https://esphome.io/components/debug/) exposes free heap, largest contiguous block and fragmentation, which would show when a device needs a restart. It needs device YAML edits and reflashing, which this repo does not manage.
- **No symptom-driven restart.** A watchdog on an `assist_satellite` stuck in `responding`, or on a device unavailable for some minutes, would catch a hang the same day. Add one if the schedule does not settle the audio.
- **Upstream might fix the fault.** ESPHome has been [rewriting its audio stack](https://esphome.io/changelog/2026.6.0/). After a major ESPHome release, re-evaluate whether the sweep is still needed.
- **Tom's Office - Elgato Key Light is not covered.** It has no known fault.

## Integration watchdogs

A watchdog reloads a config entry that has wedged. Watchdogs are reactive, not scheduled, and
they carry no label, because the unit of recovery is an integration, not a device.

Both watchdogs share the following design:

| Decision | Why |
|---|---|
| `time_pattern` every 15 minutes, not a `state` trigger with `for:` | The retry matters as much as the detection. A reload only helps if the cloud API answers that time, and the entities don't change state while stranded, so a one-shot trigger fires once. |
| Every watched entity must be `unavailable` for 15 minutes | The dwell keeps the watchdog quiet during the 04:00 restart. Requiring every entity separates an entry-level failure from one device dropping out. |
| The reload targets an entity, not an `entry_id` | The [entity ID rule](CLAUDE.md#entity-ids-not-device-ids). The registry keeps `config_entry_id` on an unavailable restored stub, so the target resolves when nothing was set up. |
| A failed reload announces with `speak: false` | A diagnostic is recorded, not announced (see [_Which callers speak_](notifications.md#which-callers-speak)). The title is fixed, so repeated failures overwrite one notification. |
| A separate trigger dismisses the notification on recovery, and watches one entity | The entities come back together, so watching them all would queue identical dismiss runs. |
| `mode: queued, max: 10` | The reload branch holds a run open for two minutes while triggers are 15 minutes apart, so nothing stacks, and a recovery that lands mid-reload is not dropped. |

Don't add a watchdog by reflex. `roomba`, `norman_shutters` and `music_assistant` go through
`not ready yet` retries every night and recover without help. Hive and Netatmo need one because
they fail in ways that Home Assistant does not retry.

### Netatmo

After a restart, every Netatmo sensor can come back `unavailable` and stay that way until the
next reload or restart, while the config entry reports `loaded` with no error.

The cause is in the integration, confirmed against the 2026.8.3 source and present in 2026.9.3:

1. `NetatmoDataHandler.async_setup()` fetches the account topology once.
2. The fetch swallows `pyatmo.ApiError` and logs it at `DEBUG`, so a failure does not raise.
3. `async_dispatch()` creates entities by iterating `account.homes`. If the fetch failed, that is empty, and no entities are dispatched.
4. `async_dispatch()` is called only from `async_setup()`, so polling cannot repair it.

The only visible sign is a different call a few seconds later, which logs at `ERROR`:
`Error during webhook registration - 503 - Service Unavailable`. A 503 with code 27 is Netatmo's
backend being unhealthy, not a quota.

`automation.netatmo_watchdog` watches the temperature sensors of the indoor and outdoor modules
and `sensor.toms_office_netatmo_pressure` on the base station. When they are all stranded, it
calls `homeassistant.reload_config_entry`, and it checks again two minutes later. If the reload
did not bring them back, it writes a persistent notification.

- **Every module must be down.** An unreachable module makes its own entities `unavailable`, so watching one sensor would reload the integration for a flat battery.
- **A missing entity counts as not stuck.** The failure leaves entities present and `unavailable`. An entity that has vanished means the watch list is wrong, and a reload loop would not fix that.
- **The reload targets `sensor.toms_office_netatmo_pressure`.** Only the base station exposes pressure.

While Netatmo is down, the watchdog costs about four reloads and 13 API calls an hour, against
the limit of 150 an hour that applies to an entry linked through Home Assistant Cloud.

To verify the templates, render them against the live instance. Both take the same `watched`
prelude:

```bash
W="{% set watched = ['sensor.toms_office_netatmo_pressure','sensor.kitchen_netatmo_temperature','sensor.master_bedroom_netatmo_temperature','sensor.nursery_netatmo_temperature','sensor.garage_netatmo_temperature'] %}"

render() {
  curl -s -X POST -H "Authorization: Bearer $HASS_TOKEN" -H "Content-Type: application/json" \
    -d "$(python3 -c 'import json,sys; print(json.dumps({"template": sys.argv[1]}))' "$1")" \
    "$HASS_SERVER/api/template"; echo
}

# "stuck": expect False while Netatmo is healthy
render "$W{% set ns = namespace(stuck = true) %}{% for e in watched %}{% if states[e] is none or states(e) not in ['unavailable','unknown'] or (now() - states[e].last_changed).total_seconds() < 900 %}{% set ns.stuck = false %}{% endif %}{% endfor %}{{ ns.stuck }}"

# "every watched sensor is back": expect True while Netatmo is healthy
render "$W{{ (watched | reject('is_state', ['unavailable','unknown']) | list | count) == (watched | count) }}"
```

To exercise the positive path without an outage, swap `watched` for entities that are already
long `unavailable` and confirm that `stuck` renders `True`. A template that renders `False`
whatever happens looks the same as a working watchdog.

`automation.trigger` is a safe smoke test. A manual trigger carries no `trigger.id`, so both
`choose` branches evaluate `false` and nothing is reloaded. Confirm in the trace that `action/0`
resolved `choice: null`.

The following gaps remain:

- **The fix belongs upstream.** `async_setup()` needs to raise `ConfigEntryNotReady` when the topology fetch fails, so that Home Assistant retries.
- **2026.9.3 logs the first fetch error at `INFO`** (`Error while fetching %s data`) with a matching recovery line, which makes the failure visible. After upgrading, check whether the watchdog still earns its place.
- **[core#181448](https://github.com/home-assistant/core/issues/181448) does not apply.** 2026.9.0 drops every entity when a Netatmo `Home` device is disabled. This instance has no `Home` device. Check again before an upgrade if that changes.
- **If the nightly restart moves, measure again.** The failure rides on one API call landing at 04:00.

### Hive

If Hive's setup hits a transient error at startup, the config entry lands in `SETUP_ERROR`,
which Home Assistant does not retry. The entry stays down until a reload, with no heating or hot
water control. Hive's services are not registered either, so `automation.morning_hot_water` fails
on its first action with `Action hive.boost_hot_water not found`.

The following upstream defects combine:

1. **`getLoginInfo` returns `None` on a timeout.** `requests.ReadTimeout` subclasses `OSError`, which the library catches and logs, and `async_init` then raises `AttributeError`. [Pyhive #145](https://github.com/Pyhass/Pyhive/pull/145) fixes it but is unreleased, and core pins `pyhive-integration==1.0.9`.
2. **Core catches an exception that cannot be raised.** `async_setup_entry` handles `HiveReauthRequired` and a server-side `HTTPException` class, so every other failure becomes `SETUP_ERROR`. This is [core#182752](https://github.com/home-assistant/core/issues/182752).
3. **Every startup forces a fresh sign-in.** In [Pyhive #123](https://github.com/Pyhass/Pyhive/issues/123), `tokenCreated` defaults to `datetime.min`, so stored tokens read as expired, and a restart calls the sign-in endpoint with a five-second timeout.

With #145 released, the crash becomes `HiveUnknownConfiguration`, which is still uncaught and
still not retried. The watchdog stays necessary.

`automation.hive_watchdog` watches `water_heater.hallway_thermostat`,
`climate.hallway_thermostat` and `binary_sensor.basement_hive_hub_status`. When every one of them is
stranded and is a restored stub, it calls `homeassistant.reload_config_entry` and checks again
two minutes later. A third branch handles "unavailable and not stubs" by announcing without
reloading. Recovery after the 04:00 restart lands at about 04:30, ahead of the morning boost.

The following details carry the design:

- **Every watched entity must have `restored: true`.** A loaded entry whose hub is offline also makes every entity `unavailable`, without the `restored` attribute. Reloading a loaded entry wedges it: `async_unload_entry` unloads the full platform list, this house has no Hive lights, unloading `light` raises, and the entry lands in `FAILED_UNLOAD`, which only a Home Assistant restart clears. This is [core#182753](https://github.com/home-assistant/core/issues/182753). A plain reload of the integration from the UI triggers it too.
- **The reload step has `continue_on_error: true`.** `restored: true` does not prove that the entry was not loaded, because an entry in `FAILED_UNLOAD` leaves restored stubs too. `reload_config_entry` raises on such an entry. Without the flag, the run stops at the reload, and the delay and the announcement do not run.

The guard stops the watchdog causing a wedge. It does not recover a wedge that exists.
[core#176594](https://github.com/home-assistant/core/pull/176594) makes the unload failure
non-fatal from 2026.10, after which the guard is defensive rather than required.

Every watched entity must be a stub, because one entity can be a stub while its entry is loaded.

To verify the guard, test it in isolation, because a wrong entity ID in a native condition fails
silently. Create a throwaway automation with the same condition and a `system_log.write` action,
force the state, and read the log:

```bash
./scripts/ha-api /api/states/water_heater.hallway_thermostat -X POST \
  -d '{"state":"unavailable","attributes":{"restored":true}}'
```

Then read the watchdog's trace with `ha_get_automation_traces`, which lists each entity of a
multi-entity `state` condition separately.

- **`restored` is live-only.** The recorder strips it from stored attributes, so it does not appear in `/api/history`.
- **Don't test the reload branch against a healthy, loaded Hive entry.** That is the path that wedges it.

The following gaps remain:

- **`homeassistant.components.hive: debug` is set** in the `logger:` block of `configuration.yaml`. It is noisy. Remove it after the upstream issues settle.
- **`automation.morning_hot_water` depends on the reload.** Its catch-up triggers are in [_Catch-up triggers_](wake-routines.md#catch-up-triggers).
