# Device Maintenance

Scheduled restarts of devices that degrade with uptime, driven by **labels on
devices** rather than a hardcoded entity list.

Two schemes live here. Everything up to [Notes](#notes) is that label-driven
sweep. [Integration Watchdogs](#integration-watchdogs) at the end is its reactive
counterpart — bouncing a *config entry* that has wedged rather than a device that
has degraded.

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

> The 04:00 restart is also what strands the Netatmo integration every night —
> see [Netatmo](#netatmo--automationnetatmo_watchdog). Moving it changes that
> exposure too, for better or worse.

## Related automations

- **`automation.restart_audio_streamers` was deleted** and absorbed into this
  scheme. It did the same job for the two Arylic LP10s at 09:00 with a hardcoded
  entity list and an inline "not playing" guard — exactly what the labels and the
  generic guard now express.
- **`automation.restart_kitchen_display_browser` is deliberately NOT part of this
  scheme.** It presses `button.kitchen_display_restart_browser` at **04:45** to
  clear the Fully Kiosk WebView, which leaks memory while rendering the kitchen
  dashboard's WebRTC camera streams (see [dashboards.md](dashboards.md)). It
  cannot be a `restart-daily` label because the Kitchen Display exposes **two**
  `device_class: restart` buttons — `restart_browser` and `restart_device` — so
  the target-derivation step above cannot pick between them, and picking wrong
  would reboot the whole tablet nightly. 04:45 sits in the same gap the rest of
  the sweep uses: after `scheduled_device_restarts` (04:30, ~5 min worst case)
  and well before `update_esphome_devices` (05:30).
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
- **Not covered:** Tom's Office - Elgato Key Light (no known fault). The Kitchen
  Display is now handled by a bespoke automation rather than a label — see
  [Related automations](#related-automations).
- **Nursery - WiiM Sound cannot be restarted from HA.** It now has **no restart
  button at all**: the speaker moved to the dedicated **`wiim`** integration,
  which exposes only a `media_player` — no `restart`, no `sync_time`. So it
  cannot join this scheme even in principle, and the reason is no longer a bug
  to wait out. (It was previously on `linkplay`, whose restart button was
  present but permanently broken — see below.)

  > The speaker was for a while adopted by **both** `linkplay` *and* `wiim`,
  > giving one physical device two native `media_player` entities plus the
  > Music Assistant proxy. The `linkplay` entry was removed, keeping `wiim`:
  > it adds `NEXT_TRACK`, `PREVIOUS_TRACK` and `SEEK` and loses only
  > `SELECT_SOUND_MODE`, and the restart button it gave up never worked anyway.
  > `linkplay` still owns the two Arylic LP10s, which restart correctly — its
  > config entries are **per device**, so removing one does not touch the
  > others. zeroconf re-discovers the WiiM within seconds of removal, so the
  > re-discovery flow is parked as an **ignored** `linkplay` entry
  > (`source: ignore`, loads nothing) rather than left to nag. Deleting that
  > ignored entry is what would bring the duplicate back.

  Historically, on `linkplay`, the restart button failed every time with
  `LinkPlayRequestException: Didn't receive expected OK from https://192.168.2.10`
  (`linkplay/bridge.py` `reboot()` → `LinkPlayCommand.REBOOT`), and the device
  never rebooted — its `media_player` did not even blip `unavailable`, unlike the
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

  That HTTP call still works and is now the **only** way to reboot this speaker
  from HA, since `wiim` exposes no restart entity to fix. It does not fit the
  `device_class: restart` derivation this scheme relies on, so it would need a
  bespoke `rest_command` automation rather than a label — and a `python-linkplay`
  fix would no longer reach this device anyway, now that it is off `linkplay`.

## Notes

- Deliberate reboots do **not** trip ESPHome's [`safe_mode`](https://esphome.io/components/safe_mode/) —
  its failure counter resets after `boot_is_good_after: 1min`, so a schedule is safe.
- Two of the three Voice PE restart buttons shipped `disabled_by: integration`
  (`button.basement_voice_assistant_restart`,
  `button.rear_guest_room_voice_assistant_restart`). They were enabled, which
  required a config-entry reload before the entities appeared in the state
  machine. A newly adopted Voice PE will need the same treatment.

---

# Integration Watchdogs

The software counterpart of the restart sweep above: a watchdog bounces a **config
entry** that has wedged, rather than a device that has degraded. These are
**reactive, not scheduled**, and they carry no label — the unit of recovery is an
integration, not a device, so there is nothing for `label_devices()` to return.

## Netatmo — `automation.netatmo_watchdog`

### The failure

Every Netatmo sensor goes `unavailable` at the 04:00 restart and stays that way
for **days**. It is not flapping, and it is not the hardware: the long-term
statistics gaps are identical across all five modules — the weather station base,
the outdoor module and the three indoor modules — which rules out radio, battery
and WiFi.

| Outage start (UTC) | Recovered | Duration |
|---|---|---|
| 2026-09-05 03:00 | 09-05 20:00 | 16 h |
| 2026-09-07 03:00 | 09-08 03:00 | 23 h |
| 2026-09-09 03:00 | 09-11 03:00 | 47 h |
| 2026-09-12 03:00 | **09-19 05:12** | **169 h** |

Every outage begins at exactly 03:00 UTC = 04:00 BST =
`automation.restart_home_assistant_at_4am_every_day`. Every recovery coincides
with a *later* restart or a manual reload — **never** spontaneously. There are no
gaps at all between 2026-06-21 (the start of the 90-day statistics window
queried) and 2026-09-05.

> The onset is *consistent with* this instance moving onto 2026.8.x —
> `UNAVAILABLE_AFTER_ERRORS` and the publisher `available` flag do not exist in
> the netatmo coordinator before 2026.8.0 — but **the upgrade date was not
> confirmed**. The core log retains only ~4 hours, so there is no direct evidence
> either way; treat it as a plausible trigger, not an established one.

### Root cause

Confirmed against the 2026.8.3 source, and **still present in 2026.9.3**:

1. `NetatmoDataHandler.async_setup()` fetches the account topology **exactly
   once**: `await self.subscribe(ACCOUNT, ACCOUNT, None)`.
2. `subscribe()` calls `async_fetch_data()`, which **swallows `pyatmo.ApiError`
   and logs it at `DEBUG`** — so the failure is invisible and does not raise.
3. `async_dispatch()` then creates every entity by iterating
   `for home in self.account.homes.values()`; the weather modules are dispatched
   from `setup_modules()`, *inside* that loop.
4. If step 1 failed, `account.homes` is empty, the loop body never runs, and
   **no entities are dispatched at all**. The registry entries restore as
   `unavailable` stubs with nothing behind them.
5. `async_dispatch()` is called from exactly one place — inside `async_setup()`.
   So polling can never repair this. **Only a reload or a restart can.**

Throughout, the config entry reports `state: loaded`, `reason: null`,
`issues: []`, and `config_entry_setup` finishes in ~4 s. Nothing appears in the
log, because the one call that matters logs at `DEBUG`.

> **The only visible fingerprint** is a *different* call, made seconds later
> against the same sick backend, which happens to log at ERROR:
>
> ```
> ERROR homeassistant.components.netatmo.webhook
> Error during webhook registration - 503 - Service Unavailable -
> Service temporarily unavailable (27) when accessing 'https://api.netatmo.com/api/addwebhook'
> ```
>
> Per `pyatmo/const.py`, 429 + code 11 is concurrency and 403 + code 26 is
> throttling; **503 + code 27 is Netatmo's own backend being unhealthy**, raised
> as a plain `ApiError`. It is not a quota this end can fix. Note the webhook
> error is caught and logged but *not* re-raised, so it never fails setup — it is
> a symptom, not the cause.
>
> Corroborating: during a stranded window the log carries `not ready yet;
> Retrying in N seconds` lines for `roomba`, `norman_shutters` and
> `music_assistant`, and **none for `netatmo`** — it was never in `setup_retry`,
> it was "loaded" and empty.

### What the automation does

Every 15 minutes, if all five watched sensors have been `unavailable` for
≥ 15 minutes, it calls `homeassistant.reload_config_entry` and re-checks two
minutes later. If that reload did not bring them back it writes a persistent
notification; a separate trigger dismisses it on recovery.

| Decision | Why |
|---|---|
| `time_pattern` every 15 min, **not** a `state` trigger with a `for:` | The **retry** matters as much as the detection. A reload only helps if the API answers *that* time, and a one-shot trigger fires once and never again — the entities never change state while stranded. |
| All five sensors must be down | An unreachable module makes its own entities `unavailable` too (`NetatmoModuleEntity.available` checks `device.reachable`), so watching one would reload the whole integration because one battery went flat. |
| 15-minute dwell | Keeps it from firing during the 04:00 restart itself. |
| A **missing** entity counts as *not* stuck | The observed failure leaves entities present-but-unavailable. An entity that has vanished entirely means this list is wrong, and looping on a reload would not fix that. |
| Targets `sensor.toms_office_netatmo_pressure`, not `entry_id` | Entity IDs, not IDs that churn — see [CLAUDE.md](CLAUDE.md). The registry keeps `config_entry_id` even on an unavailable restored stub, so it still resolves when nothing was dispatched. Pressure is exposed only by the weather station base. |
| `speak: false` on the notification | A diagnostic — recorded, not announced (see [notifications.md](notifications.md)). `script.annouce` derives its `notification_id` from `Netatmo \| slugify`, so repeated failed reloads overwrite one notification instead of stacking. |
| Recovery watches only the base station | All five come back together; watching all five would queue five identical dismiss runs. |
| `mode: queued, max: 10` | The reload branch holds a run open for 2 min while triggers are 15 min apart, so nothing stacks. Queued (rather than `single`) only means a recovery landing mid-reload is not dropped. |

Cost while Netatmo is down: ~4 reloads/hour ≈ 13 API calls/hour, against the
`CLOUD_LIMIT` of 150/hour the integration applies to HA Cloud account linking
(this entry is `auth_implementation: "cloud"`; a personal Netatmo developer app
would get `DEV_LIMIT`, 400/hour, and poll ~3.5× faster).

### Verifying the watchdog

The two templates are the fragile part — render them against the live instance
rather than reading them. Both take the same `watched` prelude:

```bash
W="{% set watched = ['sensor.toms_office_netatmo_pressure','sensor.kitchen_netatmo_temperature','sensor.master_bedroom_netatmo_temperature','sensor.nursery_netatmo_temperature','sensor.garage_netatmo_temperature'] %}"

render() {
  curl -s -X POST -H "Authorization: Bearer $HASS_TOKEN" -H "Content-Type: application/json" \
    -d "$(python3 -c 'import json,sys; print(json.dumps({"template": sys.argv[1]}))' "$1")" \
    "$HASS_SERVER/api/template"; echo
}

# "stuck" — expect False while Netatmo is healthy
render "$W{% set ns = namespace(stuck = true) %}{% for e in watched %}{% if states[e] is none or states(e) not in ['unavailable','unknown'] or (now() - states[e].last_changed).total_seconds() < 900 %}{% set ns.stuck = false %}{% endif %}{% endfor %}{{ ns.stuck }}"

# "every watched sensor is back" — expect True while Netatmo is healthy
render "$W{{ (watched | reject('is_state', ['unavailable','unknown']) | list | count) == (watched | count) }}"
```

To exercise the **positive** path without waiting for an outage, swap `watched`
for five entities that are already long-`unavailable` (any stale Fully Kiosk or
camera entity will do) and confirm `stuck` renders `True`. This is the check that
matters: a template that silently renders `False` forever looks exactly like a
watchdog that is working.

`automation.trigger` is a safe smoke test — a manual trigger carries no
`trigger.id`, so both `choose` branches evaluate `false` and nothing is reloaded.
Confirm with `ha_get_automation_traces("automation.netatmo_watchdog")` that
`action/0` resolved `choice: null` with no error.

### Known gaps and follow-ups

- **This treats a symptom.** The real fix is upstream: `async_setup()` should
  raise `ConfigEntryNotReady` when the initial topology fetch fails, so HA retries
  on its own instead of loading an empty entry. Worth filing.
- **2026.9.3 does not fix it** — `async_dispatch()` is still setup-only and
  nothing raises. It *does* promote the first fetch error to `INFO`
  (`"Error while fetching %s data"`) with a matching recovery line, so the failure
  stops being invisible. Worth upgrading for that alone; re-read this section
  afterwards and check whether the watchdog is still earning its place.
- Safe from [home-assistant/core#181448](https://github.com/home-assistant/core/issues/181448)
  (2026.9.0 silently drops every entity when a Netatmo `Home` device is disabled):
  this instance has no `Home` device and all five Netatmo devices are enabled.
  Re-check before upgrading if that ever changes.
- **If the nightly restart moves, re-measure.** The whole failure rides on one API
  call landing at 03:00 UTC, so shifting
  `automation.restart_home_assistant_at_4am_every_day` is a cheap untested
  experiment — but see [Timing](#timing--why-0430) for what else is boxed into
  that window.
- **Not generalised.** `roomba`, `norman_shutters` and `music_assistant` all churn
  through `not ready yet` retries nightly, but those retry correctly on their own;
  they do not need a watchdog and should not get one by reflex.
