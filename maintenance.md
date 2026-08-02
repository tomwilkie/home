# Device Maintenance

Scheduled restarts of devices that degrade with uptime, driven by **labels on
devices** rather than a hardcoded entity list.

## Why

ESPHome voice assistants develop **choppy, delayed audio** after long uptimes —
the response is computed quickly but playback stutters, arrives late, or the
device wedges in `responding` with no audio at all. This is a well-documented
upstream failure mode, not a local misconfiguration:

- [Voice PE stuck in `responding`](https://github.com/esphome/home-assistant-voice-pe/issues/382)
  (~daily across a 5-device fleet; the reporter's own workaround is a restart automation)
- [20+ second delays before playback](https://github.com/esphome/home-assistant-voice-pe/issues/257)
  on one device while an identical sibling is fine — open since Dec 2024, no root cause
- [Choppy/truncated speech, "DMA queue destroyed"](https://github.com/home-assistant/core/issues/93280),
  [I2S race conditions](https://github.com/esphome/esphome/issues/14016),
  ["Speaker buffer full"](https://github.com/esphome/issues/issues/5180)

The mechanism is [ESP32 heap fragmentation](https://hubble.com/community/guides/esp32-memory-fragmentation-why-your-device-crashes-after-running-for-days/):
plenty of free heap but no large *contiguous* block — exactly what starves an
audio buffer. Devices in this house routinely reach 75+ days uptime.

> **This treats a symptom.** A periodic reboot hides a diagnosable fault, and the
> cadences below are judgement calls rather than measurements — see
> [Known gaps](#known-gaps).

## How it works

One automation, **`automation.scheduled_device_restarts`** (Maintenance
category), fires at **04:30** and presses the restart button on every device
labelled for that day's cadence.

**Adding a device to the schedule is one label. No automation edit is needed.**

### The labels

Applied to **devices**, not entities.

| Label | `label_id` | Fires |
|---|---|---|
| `restart-daily` | `restart_daily` | every day |
| `restart-weekly` | `restart_weekly` | Mondays |
| `restart-monthly` | `restart_monthly` | first Monday of the month |

**No label = never restarted.** Opt-in, so a newly adopted device is inert until
deliberately tagged.

### Target derivation

For each labelled device the automation selects **the entity whose
`device_class` is `restart`**. This is what makes device-level labelling safe:

- Every ESPHome reboot button carries `device_class: restart`.
- `factory_reset_mmwave_sensor`, `reboot_mmwave_sensor`, `apply_update` and
  `sync_time` all carry **no** device class, so they can never be selected.
- Every device currently labelled has **exactly one** `device_class: restart`
  button.

> ⚠️ **Do not label the button entity, and do not use `target: {label_id: …}`.**
> A device label passed straight to a `button.press` target expands to *every*
> button on that device — on an Everything Presence Lite that includes
> `factory_reset_mmwave_sensor`. The automation iterates devices in a template and
> *selects* the right button instead, which is why it is safe.

### Guard

A device is **skipped** if any entity on it is in use — a `media_player`
`playing`, a `vacuum` `cleaning`, or a `fan` `on`. Because the guard entity lives
on the same device as the restart button, it is found automatically; there is no
per-device configuration.

A skipped device is **not retried** — a daily device simply goes the next night.

Devices with no such entity (the Everything Presence Lites) can never skip.

### Stagger

Presses are 20 s apart so the whole fleet does not drop off WiFi at once. Worst
case (a first Monday, all 14 devices) is ~5 minutes.

## Current assignment

| Cadence | Devices | Rationale |
|---|---|---|
| **daily** (6) | 3 × Voice Assistant; Hallway - Doorbell; Living Room + Tom's Office Arylic LP10 | The reported fault. Community reports daily hangs on Voice PE. The doorbell must never be wedged. |
| **weekly** (1) | Kitchen - Boiler Monitor | 77 d uptime, WiFi −76 dBm — the weakest link in the fleet. |
| **monthly** (7) | Master Bedroom - Clock; 6 × Everything Presence Lite | No known fault, and the EP Lites drive occupancy → lighting, so churn is worth minimising. |

## Timing — why 04:30

The slot is boxed in on both sides by other Maintenance automations. **Do not
move it without re-checking these:**

| Time | Automation | Interaction |
|---|---|---|
| 04:00 | `automation.restart_home_assistant_at_4am_every_day` | Bounces every ESPHome connection; the sweep needs it finished first. |
| **04:30** | **`automation.scheduled_device_restarts`** | ~5 min worst case, so it ends by ~04:35. |
| 05:30 | `automation.update_esphome_devices` | OTA flashes with 3-min waits per device — must not be interrupted. |
| 06:00 | `automation.set_assistant_volumes` | Ordering the sweep *before* this means any volume a restart disturbs is re-applied the same morning. (In the 2026-08-02 test the three Voice PEs came back at `volume_level: 1.0` — already the target — so this is a safety margin, not a demonstrated need.) |

## Related automations

- **`automation.restart_audio_streamers` was deleted** and absorbed into this
  scheme. It did the same job for the two Arylic LP10s at 09:00 with a hardcoded
  entity list and an inline "not playing" guard — exactly what the labels and the
  generic guard now express.
- **`automation.power_cycle_dyson_fan` is deliberately NOT part of this scheme.**
  It cuts mains power to a smart plug for 10 s rather than pressing a restart
  button, and its guard reads a *different device* from the one it acts on:
  `fan.master_bedroom_dyson_fan` is one device, `switch.master_bedroom_switch_dyson_fan`
  (a Z-Wave metering plug) is another. No label can express "this plug powers that
  fan", so it stays standalone at 00:00.

## Adding a device

1. Confirm the device has exactly one entity with `device_class: restart`:
   ```jinja
   {{ device_entities(device_id('button.your_device_restart'))
      | select('match','button\.')
      | select('is_state_attr','device_class','restart') | list }}
   ```
   If it returns more than one (e.g. the Kitchen Display, which has both
   `restart_browser` and `restart_device`), this scheme cannot pick for you —
   leave it out or restructure.
2. Apply one cadence label to the **device** (Settings → Devices → the device →
   ⋮ → Add label), or `ha_set_device(device_id=…, labels=["restart_weekly"])`.
   Note `ha_set_device` **replaces** the label list — read the existing labels
   first if the device has any.
3. Verify it appears in the right bucket:
   ```jinja
   {{ label_devices('restart_weekly') }}
   ```

## Verifying

Re-run these after changing labels, the automation, or the fleet.

**1. The buckets resolve to the right buttons.** This is the make-or-break check —
if a label was attached to an *entity* rather than a device, `label_devices()`
returns empty and the sweep silently does nothing.

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

Expect **6 / 1 / 7**, and confirm no `factory_reset_mmwave_sensor`, `sync_time`
or `apply_update` button appears.

**2. The guard actually discriminates** (it is easy to write a busy-filter that
silently matches nothing). List everything in the house currently matching it:

```jinja
{{ states | map(attribute='entity_id') | select('match','media_player\.|vacuum\.|fan\.')
   | select('is_state',['playing','cleaning','on']) | list }}
```

If that is non-empty while the buckets above are full, the filter is live.

**3. A press really reaches the device** — the button's state is a timestamp that
updates *even when the underlying call fails*, so a fresh timestamp alone proves
nothing. Check an uptime sensor instead (`sensor.hallway_doorbell_uptime`,
`sensor.kitchen_boiler_monitor_uptime`), or watch the device's `media_player`
blip `unavailable` in `ha_get_history`.

**4. The cadence branches gate correctly.** Trigger manually and read the trace:
`ha_get_automation_traces("automation.scheduled_device_restarts")`. On a non-Monday
the weekly and monthly `if` blocks must both show `result: false` with
`now_weekday` set accordingly.

### Result of the 2026-08-02 commissioning run

Triggered manually on a Sunday, so only the daily block ran.

- All 7 iterations fired **exactly 20 s apart** (15:53:20 → 15:55:21 UTC).
- Weekly and monthly blocks correctly skipped (`now_weekday: "sun"`).
- **Hallway - Doorbell went from 77.8 days uptime to 23 seconds** — proof the
  press reached the hardware.
- Living Room Arylic blipped `unavailable` → `idle`, confirming its reboot.
- All three `assist_satellite` entities returned to `idle`.
- The Nursery WiiM press **failed** (see [Known gaps](#known-gaps)) and
  `continue_on_error: true` did its job — the sweep completed regardless
  (`script_execution: finished`). This is why that flag is there.

## Accepted best-practice deviations

`ha_config_set_automation` raises two warnings against this automation. Both are
deliberate; do not "fix" them without reading this.

- **Templated `target.entity_id`** (`{{ repeat.item }}`). This is the standard
  `repeat.for_each` idiom. The suggested alternative — hardcoded literals or a
  `choose` — would defeat the whole point of a label-driven list. The stated risk
  (a template resolving to a non-existent entity) is mitigated three ways: the
  list is derived from the live registry, `unavailable` entities are rejected, and
  `continue_on_error: true` contains any failure.
- **`{{ now().day <= 7 }}` date condition.** The warning suggests a `sensor.date`
  state condition, but a state condition is equality-based and cannot express
  "day of month ≤ 7", and the one-shot self-disabling pattern does not apply to
  recurring logic. There is no native day-of-month condition, so "first Monday"
  requires this template. It carries an inline `alias` saying so.

## On `CLAUDE.md`'s "entity IDs, not device IDs" rule

This design uses `label_devices()`, `device_entities()` and `device_id()`, all of
which resolve **dynamically at render time**. That is the same category as the
rule's explicit exception for Jinja `device_id(...)` calls. No device ID is
hardcoded anywhere — the automation contains no IDs at all, which is precisely
the property the rule exists to protect.

## Known gaps

- **No telemetry behind the cadences.** The ESPHome [`debug` component](https://esphome.io/components/debug/)
  would expose free heap, largest contiguous block, fragmentation % and loop time,
  which is the evidence-based way to decide *when* a device needs restarting. It
  requires device YAML edits and reflashing, which this repo does not manage. Until
  then the cadences are guesses, and there is no signal telling us whether daily is
  overkill or insufficient.
- **No symptom-driven restart.** A watchdog on `assist_satellite` stuck in
  `responding`, or on a device unavailable for N minutes, would catch a hang the
  same day rather than at the next sweep. Worth adding if the schedule alone does
  not settle the audio.
- **Upstream may fix this.** ESPHome has been [rewriting the audio stack through 2026](https://esphome.io/changelog/2026.6.0/)
  (zero-copy ring buffers, fewer per-chunk allocations). `automation.update_esphome_devices`
  keeps the fleet current, so re-evaluate whether this automation is still needed
  after major ESPHome releases.
- **Not covered:** Kitchen Display (two `device_class: restart` buttons, needs an
  explicit choice) and Tom's Office - Elgato Key Light (no known fault).
- **Nursery - WiiM Sound cannot be restarted from HA — a known upstream bug.**
  It was labelled `restart-daily` initially and the label was removed again: the
  restart button fails every time with
  `LinkPlayRequestException: Didn't receive expected OK from https://192.168.2.10`
  (`linkplay/bridge.py` `reboot()` → `LinkPlayCommand.REBOOT`), and the device
  never reboots — its `media_player` does not even blip `unavailable`, unlike the
  two Arylic LP10s on the same integration, which restart correctly.

  **Root cause, confirmed directly against the device:**

  ```console
  $ curl -sk "https://192.168.2.10/httpapi.asp?command=reboot"
  unknown command
  ```

  The speaker (`project: WiiM_Sound`, firmware `Linkplay.5.2.813247`) simply does
  not implement the `reboot` httpapi command. `python-linkplay` sends `reboot` and
  raises because the response is `unknown command` rather than `OK`. Nothing on the
  HA side can fix it.

  **Upstream:** [Velleman/python-linkplay#121 "Alternate Reboot function"](https://github.com/Velleman/python-linkplay/issues/121)
  — open since 2025-08-02, same symptom reported on GGMM E5 and Edifier S1000W.
  No fix PR; `consts.py` still defines only `REBOOT = "reboot"`. Nothing matching
  is filed against `home-assistant/core`; the bug lives in the library, not the
  integration.

  **A workaround exists but is not implemented upstream.** Commenters found the
  undocumented command `StartRebootTime:1` reboots these devices, and asked for it
  as a fallback when `reboot` errors. Until the library adopts it, the same effect
  is available locally via a `rest_command` + `shell_command`-free HTTP call:

  ```console
  curl -sk "https://192.168.2.10/httpapi.asp?command=StartRebootTime:1"
  ```

  Adopting that would mean the WiiM no longer fits the `device_class: restart`
  derivation this scheme relies on, so it would need a bespoke automation rather
  than a label. Recheck issue #121 after a `python-linkplay` bump before building
  anything custom.

## Notes

- Deliberate reboots do **not** trip ESPHome's [`safe_mode`](https://esphome.io/components/safe_mode/) —
  its failure counter resets after `boot_is_good_after: 1min`, so a schedule is safe.
- Two of the three Voice PE restart buttons shipped `disabled_by: integration`
  (`button.basement_voice_assistant_restart`,
  `button.rear_guest_room_voice_assistant_restart`). They were enabled, which
  required a config-entry reload before the entities appeared in the state
  machine. A newly adopted Voice PE will need the same treatment.
