# Notifications

## Announce Scripts

### `script.annouce`

Delivers a message to the house. Accepts `title`, `message`, and optional `important`, `persistent` and `speak` fields. Actions:
1. Temporarily lowers Tom's office speaker volume if it is playing
2. Speaks the message via ChimeTTS to the selected notification players (time-gated: 06:00–23:00, or always if `important: true`), unless `speak: false`
3. Creates a persistent notification in the HA UI, unless `persistent: false` (default `true`) — `notification_id` is derived from `title | slugify` so it can be addressed for later dismissal

> **`speak: false` makes the call UI-only** (default `true`, so existing callers are
> unaffected). It suppresses the ChimeTTS step *and* the volume duck/restore either
> side of it — those exist only to make room for the TTS, so the flag is folded into
> the `was_playing` variable rather than gating three steps separately.
>
> The two flags are independent: `speak: false, persistent: false` is a no-op.

#### Which callers speak

**The rule: speak for something a person in the house should act on now; stay
silent for something that only needs a record.** Diagnostics are recorded, not
announced — the persistent notification is the log.

| Silent (`speak: false`) | Why |
|---|---|
| `automation.notify_on_automation_failure` | The message interpolates the raw error text, `Source File:` path and `Exception Details:` — a stack trace read aloud. `mode: queued, max: 20`, so one bad deploy could stack twenty of them. |
| `automation.notify_on_app_stopped` | Infrastructure churn: all 10 `device_class: running` add-ons bounce nightly around 03:00. It only avoided being noisy because TTS is gated to 06:00–23:00 — a *daytime* blip would announce a container name to the whole house. |
| `automation.vacuum_bin_full` | Low urgency, and up to three Roombas can report at once. |
| `automation.early_flight_hot_water` | Fires the evening before; see [wake-routines.md](wake-routines.md). |

| Speaks | Why |
|---|---|
| `automation.front_door_notification` | Someone is at the door — the whole point. |
| `automation.notify_on_moisture_detected` | `important: true`; a water leak must interrupt, day or night. |
| `automation.notify_on_tumble_drier_finished` | Chore prompt aimed at whoever is in. |
| `automation.notify_when_washing_machine_has_finished` | As above. |
| `script.broadcast` | Speech *is* the feature (`important: true`, `persistent: false`). |

> Each silenced call carries an inline `note:` explaining why, so it does not get
> "fixed" back. The `dismiss` branches call `script.cancel_announce`, which takes
> no `speak` argument.

### `automation.notify_on_automation_failure` needs `system_log: fire_event: true`

⚠️ It triggers on the `system_log_event` event — which **`system_log` does not fire
by default**:

```python
# homeassistant/components/system_log/__init__.py
DEFAULT_FIRE_EVENT = False
...
if self.fire_event:
    self.hass.bus.fire(EVENT_SYSTEM_LOG, entry.to_dict())
```

With no `system_log:` block in `configuration.yaml` the component loads with
defaults, the event is never fired, and this automation is **dead code that looks
healthy** — `state: on`, no errors, nothing in any log to suggest otherwise. The
only visible symptom is a `last_triggered` that never advances.

That was the case here until 2026-09-20, which is why the Hive hot-water failure
that morning produced no notification at all and the first sign of it was a cold
shower (see [maintenance.md](maintenance.md#integration-watchdogs)). The fix is
three lines in `configuration.yaml`, and it needs a **restart** — `system_log`
reads its config only at setup:

```yaml
system_log:
  fire_event: true
```

> **Verify it rather than trusting it**, since the failure mode is silence. Fire a
> synthetic event onto the bus and watch `last_triggered` move — this exercises the
> trigger, both conditions and the announce path without waiting for a real error:
>
> ```sh
> ./scripts/ha-api /api/events/system_log_event -X POST -d '{
>   "level":"ERROR","name":"homeassistant.components.automation.some_automation",
>   "message":["synthetic"],"source":["x.py",1],"exception":"","timestamp":0,"count":1}'
> ```
>
> Note this test works *even while `fire_event` is false* — firing the event by
> hand bypasses `system_log` entirely. So a passing test proves the automation is
> wired correctly, **not** that real errors will reach it; only the config above
> does that.

**The exclusion list is a loop-breaker, not a filter.** The automation matches any
logger containing `automation.` or `script.`, which includes *itself* and the script
it announces through. Without the exclusions, an error while announcing re-triggers
the announcement. `script.annouce` and `automation.notify_on_automation_failure` were
added on 2026-09-20; the pre-existing `.automation_script_fail_detector` and
`script.email_notification` entries are inherited from the blueprint this came from
and no longer exist in this instance. Both new exclusions were verified by firing
synthetic events from those loggers and confirming `last_triggered` did not move.

#### Notification player selection

`media_player.notification_players` (a media player group helper) is the master list of candidate speakers. Each member has a matching toggle named `input_boolean.{player_slug}_notifications` (e.g. `media_player.kitchen_display_ma_player` → `input_boolean.kitchen_display_ma_player_notifications`); the script's `notification_targets` variable computes the TTS targets as *group members whose toggle is on*, and the TTS step is skipped entirely if none are selected. The toggles are controlled from the Broadcast view on the Settings dashboard.

**Prefer the entity that supports `MEDIA_ANNOUNCE`** — which is usually the Music
Assistant proxy — and fall back to the native integration entity only where no MA
equivalent exists. This aligns the group with the dashboard convention (see the
"Media player rule" in [@dashboards.md](dashboards.md)) rather than opposing it.

> This rule used to say the opposite (*always* the native entity). It was changed
> after a silent failure on 2026-08-19: the bedroom sleep sound
> (see [wake-routines.md](wake-routines.md)) went inaudible because a tumble-dryer
> announcement was delivered to `media_player.master_bedroom_homepod_mini`, the
> **native `apple_tv` entity for the same speaker that Music Assistant was
> streaming to**. An `apple_tv` HomePod does **not** advertise `MEDIA_ANNOUNCE`, so
> ChimeTTS *replaced* playback: the announcement seized the HomePod's AirPlay
> output, and the HomePod never returned to MA's stream. Music Assistant is
> fire-and-forget on its `cliraop` process, so it never noticed — its process
> stayed alive with established TCP sessions and its queue kept advancing, leaving
> a silent room, a dashboard reading `playing`, and a session that `pause`/`play`
> could not recover because it was never torn down. Announcing through the MA
> proxy instead keeps the stream and the interruption under one component, so MA
> pauses its queue, announces, and resumes.

Current members (announce support checked via the `supported_features` bit `1048576`):

| Member | Why |
|---|---|
| `hallway_doorbell_speaker`, the three `*_voice_assistant*` | native ESPHome — already support announce |
| `master_bedroom_homepod_mini_ma_player` | MA proxy; the native `apple_tv` entity cannot announce |
| `living_room_arylic_lp10_ma_player` | MA proxy; the native `linkplay` entity cannot announce |
| `kitchen_display_ma_player` | MA proxy; the native `fully_kiosk` entity cannot announce (but see the Cast note below) |
| `garage_ai_pro_speaker` | native `unifiprotect` — no MA equivalent exists, so it stays on the replace path |

> ⚠️ **The Kitchen Display's MA player is a *Google Cast* player, and announcing
> to it backgrounds Fully Kiosk.** Music Assistant did not proxy the `fully_kiosk`
> entity — it discovered the Pixel Tablet over Chromecast independently (its
> device registry entry reads `manufacturer: Google, model: Pixel Tablet`). So an
> announcement opens a cast session, Android foregrounds the Cast receiver
> `com.google.android.apps.mediashell`, and when the session ends Android returns
> to the **launcher**, not to Fully — leaving the tablet on the Android home
> screen. Fully's Kiosk Mode is deliberately off (the kitchen dashboard launches
> Apple Music and YouTube), so nothing pulls Fully back on its own.
>
> This is the mirror image of the HomePod failure above: there the *native*
> entity hijacked the MA stream; here the *MA* entity hijacks the native app.
> The fix keeps the MA proxy — it genuinely supports `MEDIA_ANNOUNCE` and resumes
> its queue — and adds **`automation.kitchen_display_foreground_watchdog`**, which
> presses `button.kitchen_display_bring_to_foreground` when
> `sensor.kitchen_display_foreground_app` sits on `mediashell` or the launcher for
> 30 s. It matches only those two apps, so an app launched deliberately from the
> dashboard is left alone, and it is gated on the MA player not `playing` so it
> can never cut an announcement short. Keeping the healing in an automation rather
> than in `script.annouce` leaves the announce script device-agnostic and also
> covers cast drift that no announcement caused.

> ⚠️ **`media_player.kitchen_display` and `media_player.kitchen_display_ma_player`
> are the same Pixel Tablet** — the `fully_kiosk` device *Kitchen - Display* and the
> `music_assistant` device *Kitchen - Display (Music Assistant)*. Only the MA one is
> in the group.

The `{player_slug}` in the toggle name is derived from whichever entity is actually
in the group (e.g. `media_player.master_bedroom_homepod_mini_ma_player` →
`input_boolean.master_bedroom_homepod_mini_ma_player_notifications`).

#### Why the TTS step is split in two

`announce` is a **single flag on a single `chime_tts.say` call**, and HA rejects
`announce: true` against a player that lacks the feature — so mixed-capability
targets cannot share one call. `script.annouce` therefore partitions
`notification_targets` into two variables by testing the `supported_features` bit,
and calls `chime_tts.say` twice:

| Variable | Players | `announce` | Behaviour |
|---|---|---|---|
| `announce_targets` | those with `MEDIA_ANNOUNCE` | `true` | overlays, player resumes afterwards |
| `replace_targets` | the rest | `false` | replaces playback (the original behaviour) |

The split is **capability-driven, not a hardcoded list**, so swapping a group
member for an announce-capable entity moves it to the right branch automatically.
Both branches carry the same time/`important`/`speak` guards. Each step has an
inline `note:` explaining this, so it does not get merged back into one call.

When adding a player to the group, also create its `input_boolean.{player_slug}_notifications` toggle (display name `Notifications`, assigned to the player's area, turned on) and add it to the Broadcast view's Notification Players card — a group member without a toggle is never announced to, because its toggle lookup resolves to a non-existent entity.

> **When *swapping* a member, delete the outgoing toggle too.** The lookup is
> derived from the group member's entity ID, so a toggle whose player is no
> longer in the group is simply never read — but it still sits in the entity
> list looking live and flippable, inviting someone to "fix" a silent speaker
> with the wrong switch. Moving the group from the native entities to the MA
> proxies left three behind (`kitchen_display`, `living_room_arylic_lp10`,
> `master_bedroom_homepod_mini`), since the proxies' toggles carry the
> `_ma_player` suffix; they were deleted. Audit with the two renders below — a
> live group member missing its toggle is silently mute, and a toggle matching
> no member is dead:
>
> ```jinja
> {% set m = state_attr('media_player.notification_players','entity_id') %}
> missing: {{ m | map('replace','media_player.','input_boolean.')
>                | map('regex_replace','$','_notifications')
>                | reject('in', states | map(attribute='entity_id') | list) | list }}
> orphans: {{ states.input_boolean | map(attribute='entity_id')
>             | select('search','_notifications$')
>             | reject('in', m | map('replace','media_player.','input_boolean.')
>                              | map('regex_replace','$','_notifications') | list) | list }}
> ```

### `script.broadcast`

Backs the Broadcast view on the Settings dashboard. Guards against an empty `input_text.broadcast_message`, calls `script.annouce` with the box's contents (`title: Broadcast`, `important: true`, `persistent: false`), then clears the box.

### `script.cancel_announce`

Dismisses a persistent notification previously created by `script.annouce`. Accepts a `title` field and calls `persistent_notification.dismiss` using the same `title | slugify` convention. Automations call this script on their dismiss trigger rather than calling the service directly.

---

## Pattern

Each appliance uses the same structure: an `input_select` state helper decouples device events from notification. One automation manages all state transitions; a second reacts to state changes and delivers or dismisses alerts. All state automations run in `restart` mode — a new trigger interrupts any in-progress run, so late-arriving events are never queued or dropped.

### The state helpers must **not** set `initial`

`initial` on an `input_select` is not "the value it starts life with" — it
**disables last-state restore** and forces that value on every Home Assistant
restart. `InputSelect.async_added_to_hass` short-circuits before the
`RestoreEntity` lookup whenever an initial value is present:

```python
async def async_added_to_hass(self) -> None:
    await super().async_added_to_hass()
    if self.current_option is not None:   # set from CONF_INITIAL
        return                            # ← async_get_last_state() never runs
    state = await self.async_get_last_state()
```

Both appliance helpers originally carried `initial: idle`, so the nightly
`automation.restart_home_assistant_at_4am_every_day` reset any cycle in flight
and its "finished" notification was silently lost — e.g. `washing_machine_state`
`running` → `idle` at 04:00:31 on 2026-08-17, and `tumble_dryer_state` `active`
→ `idle` mid-cycle at 04:00:15 on 2026-08-22. **`initial` is now unset on both**,
so they restore across a restart.

> ⚠️ `ha_config_set_helper` **cannot** clear it — it merges, preserving fields not
> re-passed, and `initial=None` means "not passed". Use the WebSocket API, whose
> `InputSelectStorageCollection._update_data` *replaces* the record
> (`{CONF_ID: item[CONF_ID]} | update_data`), so omitting `initial` drops it.
> `name` and `options` are required, and `icon` must be re-sent or it is lost too:
>
> ```sh
> hass-cli raw ws input_select/update --json='{
>   "input_select_id": "washing_machine_state",
>   "name": "Washing Machine State",
>   "icon": "mdi:washing-machine",
>   "options": ["idle", "running", "finished"]
> }'
> ```

**`input_select.front_door_state` deliberately keeps `initial: Absent`.** Its
2-minute auto-reset is a `delay` inside `automation.front_door_state`, which a
restart destroys — restoring `Someone at the Door` would wedge it there
permanently. Resetting to `Absent` on restart is the correct behaviour for that
one helper, and the difference is intentional, not drift.

---

## Tumble Dryer Automation

---

### Helper: Tumble Dryer State

| Field | Value |
|---|---|
| Entity ID | `input_select.tumble_dryer_state` |
| Type | `input_select` |
| Options | `idle`, `active`, `finished` |
| Initial | *(unset — see [the restore note](#the-state-helpers-must-not-set-initial))* |

Tracks the current phase of a drying cycle.

---

### Automation: Tumble Dryer State (`automation.tumble_dryer_state`)

Manages all transitions of the `tumble_dryer_state` helper. Triggered by three events:

| Trigger ID | Source | Event |
|---|---|---|
| `start` | `sensor.basement_dryer_bsh_common_status_operationstate` | Operation state → `Run` |
| `finished` | `event.basement_dryer_laundrycare_dryer_event_dryingprocessfinished` | `event_type` attribute → `Present` |
| `door_open` | `sensor.basement_dryer_bsh_common_status_doorstate` | Door state `Closed` → `Open` |

#### Transition logic

Each branch guards on the current state before acting, so spurious triggers are ignored:

**`start` trigger** — only if current state is `idle`:
- Sets state → `active`

**`finished` trigger** — only if current state is `active`:
- Sets state → `finished`

**`door_open` trigger** — only if current state is `finished`:
- Sets state → `idle`

> The state guards also prevent the anti-wrinkle tumble (a second Run→Finished cycle after the main drying completes) from re-triggering the notification.

---

### Automation: Tumble Dryer Notification (`automation.notify_on_tumble_drier_finished`)

Two triggers, branched by `trigger.id`:

| Trigger ID | Condition | Action |
|---|---|---|
| `create` | `tumble_dryer_state` transitions `active` → `finished` | Announce via `script.annouce` (title: "Tumble Drier") |
| `dismiss` | `tumble_dryer_state` leaves `finished` (door opened → `idle`) | Dismiss notification via `script.cancel_announce` |

The `from` guard on the `create` trigger prevents spurious fires on HA restart or unknown state initialisation. The `dismiss` trigger fires on the same `door_open` transition that resets the state helper to `idle`, so the persistent notification is cleared automatically when the user retrieves the laundry.

---

## Front Door Automation

---

### Helper: Front Door State

| Field | Value |
|---|---|
| Entity ID | `input_select.front_door_state` |
| Type | `input_select` |
| Options | `Absent`, `Someone at the Door` |
| Initial | `Absent` — **deliberately set**, unlike the appliance helpers ([why](#the-state-helpers-must-not-set-initial)) |

Tracks whether someone is currently at the front door.

---

### Automation: Front Door State (`automation.front_door_state`)

Manages all transitions of the `front_door_state` helper. Triggered by four events:

| Trigger ID | Source | Event |
|---|---|---|
| `knocking` | `binary_sensor.front_door_vibration_vibration` | Vibration detected (`off` → `on`) |
| `doorbell` | `binary_sensor.front_door_doorbell` | Doorbell pressed (`off` → `on`, UniFi Protect) |
| `webhook` | UniFi Protect "Ring" alarm rule → HA webhook `<your-webhook-id>` | GET request received |
| `door_open` | `binary_sensor.front_door_contact_contact` | Door opens (state → `on`) |

> The `doorbell` and `webhook` triggers are **redundant paths for the same doorbell press** — both fire within milliseconds of each other. In `restart` mode one supersedes the other, and the `Absent`-only state guard means only one announcement is produced. The native `doorbell` trigger is the primary path; the `webhook` is belt-and-suspenders (see [Webhook source](#webhook-source-unifi-protect) below).

> The `doorbell` trigger uses `from: off` (not just `to: on`) so that `unavailable` → `on` transitions during the nightly restart or UniFi Protect reconnects cannot fire it.

#### Transition logic

Each branch guards on the current state before acting, so spurious triggers are ignored:

**`door_open` trigger** — only if current state is `Someone at the Door`:
- Sets state → `Absent`

**`knocking` trigger** — only if current state is `Absent` AND `front_door_contact_contact` has been `off` for ≥ 1 minute (door was closed, not just opened):
- Sets state → `Someone at the Door`

**`doorbell` or `webhook` trigger** — only if current state is `Absent`:
- Sets state → `Someone at the Door`

#### Auto-reset

After the choose block, if the state is now `Someone at the Door` (i.e. one of the above branches fired), the automation waits **2 minutes** then resets to `Absent`. The door-open trigger can fire earlier to reset sooner.

Runs in `restart` mode — if the door opens during the 2-minute wait, the reset fires immediately rather than waiting for the current run to finish.

#### Webhook source (UniFi Protect)

The `webhook` trigger is fed by a **UniFi Protect Alarm Manager rule** named **"Ring"** on the Dream Machine Pro Max, scoped to the front-door doorbell camera (trigger: `ring`). The rule's Custom Webhook action does a `GET` to HA at `http://<ha-lan-ip>:8123/api/webhook/<your-webhook-id>`; the same rule also sends UniFi push notifications to household phones.

Originally the rule pointed at the **external** (Nabu Casa) HA URL, which forced the UDM to round-trip every ring out to the internet and back. That path silently stopped delivering — no webhook reached HA for 7+ days, consistent with the 2026 UniFi Alarm Manager / Protect 7.x transition — which is why the native `doorbell` trigger was added as the primary path. The rule was then repointed to HA's **local LAN IP**, which the UDM delivers directly without leaving the network. HA's IP is held stable by a **DHCP reservation** on the UDM (keyed to HA's NIC MAC); HAOS itself stays on DHCP.

Edit this rule via `protect_alarm_update_rule` (the MCP server handles `_new`-suffixed legacy rule ids as of v0.5.2+) or in the UniFi Protect UI.

---

### Automation: Front Door Notification (`automation.front_door_notification`)

Two triggers, branched by `trigger.id`:

| Trigger ID | Condition | Action |
|---|---|---|
| `create` | `front_door_state` transitions `Absent` → `Someone at the Door` | Announce + push notify (see below) |
| `dismiss` | `front_door_state` leaves `Someone at the Door` | Dismiss notification via `script.cancel_announce` |

**`create` branch actions:**
1. If Tom's Office media player is playing, temporarily lower volume to 10%
2. In parallel:
   - Announce "Someone is at the front door." via `script.annouce`
   - If Tom is in his office (`sensor.tom_s_iphone_area` = `Tom's Office`): take a snapshot from the front door camera and send a push notification to Tom's iPhone with the image and a "Tell them I'm coming!" action button
3. Restore the media player volume

The `dismiss` trigger fires when the state helper resets to `Absent` — either via the door opening (immediate) or the 2-minute auto-reset — clearing the persistent notification automatically.

---

## Washing Machine Automation

---

### Helper: Washing Machine State

| Field | Value |
|---|---|
| Entity ID | `input_select.washing_machine_state` |
| Type | `input_select` |
| Options | `idle`, `running`, `finished` |
| Initial | *(unset — see [the restore note](#the-state-helpers-must-not-set-initial))* |

Tracks the current phase of a wash cycle.

---

### Automation: Washing Machine State (`automation.washing_machine_state`)

Manages all transitions of the `washing_machine_state` helper. Triggered by two sources:

| Trigger ID | Source | Event |
|---|---|---|
| `power_change` | `sensor.basement_washing_machine_smart_switch_power` | Any power reading change |
| `door_open` | `binary_sensor.basement_washing_machine_door_contact` | Door opens (state → `on`) |
| `catchup` | `homeassistant` | HA start — re-arms a 10-minute wait a restart destroyed |

#### Transition logic

Each branch guards on the current state before acting, so spurious triggers are ignored:

**`power_change` trigger, power > 1W** — only if current state is `idle`:
- Sets state → `running`

**`power_change` trigger, power ≤ 1W** — only if current state is `running`:
- Waits 10 minutes, then sets state → `finished`

**`door_open` trigger** — only if current state is `running` or `finished`:
- Sets state → `idle`

**`catchup` trigger** — only if current state is `running` AND power is already ≤ 1W:
- Waits 10 minutes, then sets state → `finished`

Runs in `restart` mode — power fluctuations during the 10-minute wait restart the clock. The machine must sustain low power for a full uninterrupted 10 minutes before the state advances to `finished`.

> **Why the `catchup` branch exists.** The 10-minute wait is a `delay`, which a
> restart destroys, and the only other trigger is a power **state change** — at a
> flat 0 W there is never another one. So a wash that ended in the 04:00 restart
> window would restore as `running` and stick there forever. On HA start, if the
> helper is `running` while the machine is already drawing ≤ 1 W, this branch
> re-arms the wait; worst case the notification lands 10 minutes late. Because
> `mode: restart` is retained, genuine power activity during the catch-up delay
> supersedes the run via the `power_change` trigger. Same pattern as the
> `catchup` trigger in `automation.early_flight_hot_water` (see
> [wake-routines.md](wake-routines.md#the-0400-restart-hole)).
>
> The tumble dryer needs no equivalent: its transitions are purely event-driven
> with no `delay` to lose.

---

### Automation: Washing Machine Notification (`automation.notify_when_washing_machine_has_finished`)

Two triggers, branched by `trigger.id`:

| Trigger ID | Condition | Action |
|---|---|---|
| `create` | `washing_machine_state` transitions `running` → `finished` | Announce via `script.annouce` (title: "Washing Machine") |
| `dismiss` | `washing_machine_state` leaves `finished` (door opened → `idle`) | Dismiss notification via `script.cancel_announce` |

---

## Vacuum Bin Full Automation

---

### Automation: Vacuum Bin Full (`automation.vacuum_bin_full`)

Announces when a Roomba's dust bin needs emptying. Unlike the appliance
automations above, this needs **no `input_select` state helper** — `bin_full` is
already a clean two-state boolean attribute on the vacuum entity, so the
automation triggers directly on the attribute transition.

Two triggers, branched by `trigger.id`, both watching `attribute: bin_full` on
`vacuum.basement_roomba`, `vacuum.living_room_roomba`, and
`vacuum.toms_office_roomba`:

| Trigger ID | Condition | Action |
|---|---|---|
| `create` | `bin_full` → `true` | Announce via `script.annouce` (**`speak: false`** — UI only) |
| `dismiss` | `bin_full` → `false` (bin emptied) | Dismiss via `script.cancel_announce` |

The title is templated as `{{ trigger.to_state.attributes.friendly_name }} Bin
Full` (e.g. "Tom's Office - Roomba Bin Full"). Because `script.annouce` derives
its `notification_id` from `title | slugify`, this gives each vacuum its own
independent persistent notification from a single shared automation, rather than
needing one automation per vacuum.

> **Why this matters:** a Roomba with a full bin still *accepts* a start command
> — it drives off the dock, then aborts back within ~30 seconds with
> `cleaning_time: 0` and `cleaned_area: 0`. So the failure is silent: the morning
> routine appears to run, but nothing is cleaned. This automation surfaces the
> real cause. The [home dashboard](dashboards.md) also flags it visually.

> **Scope is Roombas only.** `vacuum.kitchen_vacuum` is a Deebot and exposes no
> `bin_full` attribute (`state_attr` returns `None`), so it is deliberately
> excluded from both the automation and the dashboard styling.

