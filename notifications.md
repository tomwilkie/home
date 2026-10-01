# Notifications

This document covers the announce scripts, how they choose speakers, and the automations that
notify for the front door, the washing machine, the tumble dryer and the vacuums.

## Announce scripts

### `script.annouce`

`script.annouce` delivers a message to the house. It accepts `title` and `message`, and the
optional `important`, `persistent` and `speak` fields. It takes the following actions:

1. If Tom's office speaker is playing, it lowers the volume for the duration of the announcement.
2. Unless `speak: false`, it speaks the message through ChimeTTS on the selected notification players. Speech runs only between 06:00 and 23:00, unless `important: true`.
3. Unless `persistent: false`, it creates a persistent notification in the Home Assistant UI. The `notification_id` is `title | slugify`, so a later call can dismiss it.

`speak: false` makes the call UI-only. It suppresses the ChimeTTS step and the volume duck and
restore either side of it. The two flags are independent, so `speak: false, persistent: false`
does nothing.

### `script.cancel_announce`

`script.cancel_announce` dismisses a persistent notification that `script.annouce` created. It
accepts a `title` and calls `persistent_notification.dismiss` with the same `title | slugify`
ID. Automations call it on their dismiss trigger rather than calling the service directly.

### `script.broadcast`

`script.broadcast` backs the Broadcast view on the Settings dashboard. It guards against an
empty `input_text.broadcast_message`, calls `script.annouce` with the contents of the box
(`title: Broadcast`, `important: true`, `persistent: false`), then clears the box.

### Which callers speak

Speak for something a person in the house must act on at that moment. Stay silent for something
that only needs a record: the persistent notification is the log.

| Caller | Speaks | Why |
|---|---|---|
| `automation.front_door_notification` | yes | Someone is at the door. |
| `automation.notify_on_moisture_detected` | yes, `important: true` | A water leak must interrupt, day or night. |
| `automation.notify_on_tumble_drier_finished` | yes | A chore prompt for whoever is in. |
| `automation.notify_when_washing_machine_has_finished` | yes | A chore prompt for whoever is in. |
| `script.broadcast` | yes, `important: true` | Speech is the feature. |
| `automation.notify_on_automation_failure` | no | The message carries raw error text, a source path and exception details. The automation is `mode: queued, max: 20`, so one bad deploy could queue twenty of them. |
| `automation.notify_on_app_stopped` | no | Add-ons with `device_class: running` bounce nightly around 03:00, and a daytime blip would announce a container name to the house. |
| `automation.vacuum_bin_full` | no | Low urgency, and several Roombas can report at once. |
| `automation.early_flight_hot_water` | no | It fires the evening before. See [wake-routines.md](wake-routines.md). |
| `automation.netatmo_watchdog`, `automation.hive_watchdog` | no | Diagnostics. See [maintenance.md](maintenance.md). |

Each silenced call carries an inline `note:` that explains why, so that nobody restores the
speech.

### Enable `system_log` events for `automation.notify_on_automation_failure`

`automation.notify_on_automation_failure` triggers on the `system_log_event` event, which
`system_log` does not fire by default. Without the following block in `configuration.yaml` the
automation looks healthy and never runs: its only symptom is a `last_triggered` that does not
advance. `system_log` reads its config at setup, so a change needs a restart.

```yaml
system_log:
  fire_event: true
```

To test the automation, fire a synthetic event and watch `last_triggered` move:

```sh
./scripts/ha-api /api/events/system_log_event -X POST -d '{
  "level":"ERROR","name":"homeassistant.components.automation.some_automation",
  "message":["synthetic"],"source":["x.py",1],"exception":"","timestamp":0,"count":1}'
```

The test passes even while `fire_event` is false, because firing the event by hand bypasses
`system_log`. A passing test shows that the automation is wired correctly, not that real errors
reach it.

The automation matches any logger that contains `automation.` or `script.`, which includes
itself and the script it announces through. Its exclusion list breaks that loop: `script.annouce`
and `automation.notify_on_automation_failure` must stay in it, or an error while announcing
triggers another announcement. The `.automation_script_fail_detector` and
`script.email_notification` entries come from the original blueprint and match nothing in this
instance.

## Notification players

`media_player.notification_players`, a media player group helper, is the list of candidate
speakers. Each member has a toggle named `input_boolean.{player_slug}_notifications`, where the
slug comes from the entity that is in the group: `media_player.kitchen_display_ma_player` pairs
with `input_boolean.kitchen_display_ma_player_notifications`. The script's `notification_targets`
variable is the group members whose toggle is on, and the script skips the speech step when
there are none. The toggles are on the Broadcast view of the Settings dashboard.

### Choose the entity that supports announce

For each speaker, put the entity that advertises `MEDIA_ANNOUNCE` in the group. That is usually
the Music Assistant proxy. Fall back to the native integration entity only where no Music
Assistant equivalent exists. To check, test bit `1048576` of `supported_features`.

A native entity without `MEDIA_ANNOUNCE` replaces playback instead of overlaying it. On the
master bedroom HomePod that seized the AirPlay output from Music Assistant's stream and left a
silent room that Home Assistant still reported as `playing`. Announcing through the proxy keeps
the stream and the interruption under one component, so Music Assistant pauses its queue,
announces and resumes.

The group has the following members:

| Member | Why |
|---|---|
| `hallway_doorbell_speaker` and the `*_voice_assistant*` players | Native ESPHome entities, which support announce |
| `master_bedroom_homepod_mini_ma_player` | Music Assistant proxy. The native `apple_tv` entity cannot announce. |
| `living_room_arylic_lp10_ma_player` | Music Assistant proxy. The native `linkplay` entity cannot announce. |
| `kitchen_display_ma_player` | Music Assistant proxy. The native `fully_kiosk` entity cannot announce. |
| `garage_ai_pro_speaker` | Native `unifiprotect` entity with no Music Assistant equivalent, so it stays on the replace path |

### The Kitchen Display watchdog

`media_player.kitchen_display` and `media_player.kitchen_display_ma_player` are the same Pixel
Tablet. Music Assistant did not proxy the `fully_kiosk` entity: it discovered the tablet over
Google Cast. An announcement therefore opens a cast session, Android brings the Cast receiver
`com.google.android.apps.mediashell` to the foreground, and when the session ends Android
returns to the launcher, not to Fully Kiosk. Fully's Kiosk Mode is deliberately off, because the
kitchen dashboard launches Apple Music and YouTube, so nothing brings Fully back.

`automation.kitchen_display_foreground_watchdog` fixes this. It presses
`button.kitchen_display_bring_to_foreground` when `sensor.kitchen_display_foreground_app` sits on
`mediashell` or the launcher for 30 seconds. It matches only those two apps, so it leaves alone
an app launched from the dashboard, and it does not act while the Music Assistant player is
`playing`, so it cannot cut an announcement short. The healing lives in an automation rather
than in `script.annouce`, which keeps the script device-agnostic and also covers cast drift that
no announcement caused.

### Why the speech step is split in two

`announce` is a single flag on a `chime_tts.say` call, and Home Assistant rejects
`announce: true` against a player that lacks the feature. Mixed-capability targets therefore
cannot share one call. `script.annouce` partitions `notification_targets` by the
`supported_features` bit and calls `chime_tts.say` twice:

| Variable | Players | `announce` | Behaviour |
|---|---|---|---|
| `announce_targets` | Those with `MEDIA_ANNOUNCE` | `true` | Overlays, and the player resumes afterwards |
| `replace_targets` | The rest | `false` | Replaces playback |

The split follows capability, not a hardcoded list, so a member swapped for an announce-capable
entity moves to the right branch with no script edit. Both branches carry the same time,
`important` and `speak` guards, and each step has an inline `note:` so that nobody merges them.

### Add or swap a player

To add a player to the group, also create its `input_boolean.{player_slug}_notifications` toggle
(display name `Notifications`, assigned to the player's area, turned on) and add it to the
Notification Players card on the Broadcast view. A member without a toggle is silently mute,
because its toggle lookup resolves to an entity that does not exist.

To swap a member, also delete the outgoing toggle. A toggle whose player has left the group is
not read, but it still looks live in the entity list.

The following template audits both directions. `missing` lists members without a toggle, and
`orphans` lists toggles without a member:

```jinja
{% set m = state_attr('media_player.notification_players','entity_id') %}
missing: {{ m | map('replace','media_player.','input_boolean.')
               | map('regex_replace','$','_notifications')
               | reject('in', states | map(attribute='entity_id') | list) | list }}
orphans: {{ states.input_boolean | map(attribute='entity_id')
            | select('search','_notifications$')
            | reject('in', m | map('replace','media_player.','input_boolean.')
                             | map('regex_replace','$','_notifications') | list) | list }}
```

## Appliance pattern

Each appliance uses an `input_select` state helper to decouple device events from notification.
One automation manages the state transitions, and a second reacts to state changes to deliver or
dismiss the alert. Each branch of a state automation guards on the helper's state, so spurious
triggers are ignored. The state automations run in `restart` mode, so a trigger interrupts any
run in progress.

Each notification automation has the same two triggers, branched by `trigger.id`:

| Trigger ID | Condition | Action |
|---|---|---|
| `create` | The helper moves from its active state to its finished state | Announce through `script.annouce` |
| `dismiss` | The helper leaves its finished state | Dismiss through `script.cancel_announce` |

The `from` guard on the `create` trigger prevents a fire on restart or from an unknown state.

### Don't set `initial` on the appliance helpers

`initial` on an `input_select` disables last-state restore and forces that value on every
restart: `InputSelect.async_added_to_hass` returns before the `RestoreEntity` lookup when an
initial value is present. With `initial: idle`, the nightly 04:00 restart reset any cycle in
flight and its "finished" notification was lost. `initial` is unset on
`input_select.washing_machine_state` and `input_select.tumble_dryer_state`, so they restore
across a restart.

`ha_config_set_helper` cannot clear `initial`, because it merges and preserves fields that are
not passed. Use the WebSocket API, which replaces the record. `name` and `options` are required,
and `icon` is lost unless it is sent again:

```sh
hass-cli raw ws input_select/update --json='{
  "input_select_id": "washing_machine_state",
  "name": "Washing Machine State",
  "icon": "mdi:washing-machine",
  "options": ["idle", "running", "finished"]
}'
```

`input_select.front_door_state` deliberately keeps `initial: Absent`. Its two-minute auto-reset
is a `delay` inside `automation.front_door_state`, which a restart destroys, so restoring
`Someone at the Door` would leave it stuck there.

## Tumble dryer

`input_select.tumble_dryer_state` has the options `idle`, `active` and `finished`.

`automation.tumble_dryer_state` manages the helper from the following triggers:

| Trigger ID | Source | Event | Guard | Transition |
|---|---|---|---|---|
| `start` | `sensor.basement_dryer_bsh_common_status_operationstate` | State becomes `Run` | `idle` | to `active` |
| `finished` | `event.basement_dryer_laundrycare_dryer_event_dryingprocessfinished` | `event_type` attribute becomes `Present` | `active` | to `finished` |
| `door_open` | `sensor.basement_dryer_bsh_common_status_doorstate` | `Closed` to `Open` | `finished` | to `idle` |

The guards also stop the anti-wrinkle tumble, a second run after the main cycle, from
triggering the notification again.

`automation.notify_on_tumble_drier_finished` announces with the title "Tumble Drier" on `active`
to `finished`, and dismisses when the door opens.

## Front door

`input_select.front_door_state` has the options `Absent` and `Someone at the Door`.

`automation.front_door_state` manages the helper from the following triggers:

| Trigger ID | Source | Event | Guard | Transition |
|---|---|---|---|---|
| `knocking` | `binary_sensor.front_door_vibration_vibration` | `off` to `on` | `Absent`, and `binary_sensor.front_door_contact_contact` has been `off` for at least one minute | to `Someone at the Door` |
| `doorbell` | `binary_sensor.front_door_doorbell` (UniFi Protect) | `off` to `on` | `Absent` | to `Someone at the Door` |
| `webhook` | UniFi Protect "Ring" alarm rule, by a GET to webhook `<your-webhook-id>` | Request received | `Absent` | to `Someone at the Door` |
| `door_open` | `binary_sensor.front_door_contact_contact` | State becomes `on` | `Someone at the Door` | to `Absent` |

- **`doorbell` and `webhook` are redundant paths for the same press.** Both fire within milliseconds. In `restart` mode one supersedes the other, and the `Absent` guard means one announcement. The native `doorbell` trigger is the primary path.
- **The `doorbell` trigger uses `from: off`,** so an `unavailable` to `on` transition during the nightly restart or a Protect reconnect cannot fire it.
- **The state resets after two minutes.** After the choose block, if the state is `Someone at the Door`, the automation waits two minutes and sets `Absent`. A door-open trigger during the wait restarts the run and resets at once.

### Webhook source

A UniFi Protect Alarm Manager rule named "Ring", scoped to the front-door doorbell camera with
trigger `ring`, feeds the `webhook` trigger. Its Custom Webhook action sends a `GET` to
`http://<ha-lan-ip>:8123/api/webhook/<your-webhook-id>`. The same rule sends UniFi push
notifications to household phones.

Point the rule at Home Assistant's LAN address, not the external URL, so that the UDM delivers
the ring without leaving the network. The address is held stable by the DHCP reservation
described in [_Network map_](network-security.md#network-map). To edit the rule, use
`protect_alarm_update_rule` or the UniFi Protect UI.

### `automation.front_door_notification`

On `create` (`Absent` to `Someone at the Door`) the automation takes the following actions:

1. If Tom's Office media player is playing, it lowers the volume to 10%.
2. In parallel, it announces "Someone is at the front door." through `script.annouce`. If Tom is in his office (`sensor.tom_s_iphone_area` is `Tom's Office`), it also takes a snapshot from the front door camera and sends a push notification to Tom's iPhone with the image and a "Tell them I'm coming!" action button.
3. It restores the media player volume.

On `dismiss`, which follows the door opening or the two-minute reset, it clears the persistent
notification.

## Washing machine

`input_select.washing_machine_state` has the options `idle`, `running` and `finished`.

`automation.washing_machine_state` manages the helper from the following triggers:

| Trigger ID | Source | Event | Guard | Transition |
|---|---|---|---|---|
| `power_change` | `sensor.basement_washing_machine_smart_switch_power` | Power above 1 W | `idle` | to `running` |
| `power_change` | `sensor.basement_washing_machine_smart_switch_power` | Power at or below 1 W | `running` | Wait 10 minutes, then to `finished` |
| `door_open` | `binary_sensor.basement_washing_machine_door_contact` | State becomes `on` | `running` or `finished` | to `idle` |
| `catchup` | `homeassistant` start | Home Assistant starts | `running`, and power at or below 1 W | Wait 10 minutes, then to `finished` |

In `restart` mode, power fluctuations during the wait restart the clock, so the machine must
hold low power for an uninterrupted 10 minutes.

The `catchup` trigger exists because the wait is a `delay`, which a restart destroys, and at a
flat 0 W the power sensor produces no further state change. Without it, a wash that ends in the
04:00 restart window restores as `running` and stays there. The tumble dryer needs no
equivalent, because its transitions are event-driven with no `delay`.

`automation.notify_when_washing_machine_has_finished` announces with the title "Washing Machine"
on `running` to `finished`, and dismisses when the door opens.

## Vacuum bin full

`automation.vacuum_bin_full` announces when a Roomba's dust bin needs emptying. It needs no
state helper, because `bin_full` is already a two-state attribute on the vacuum entity. Both
triggers watch `attribute: bin_full` on `vacuum.basement_roomba`, `vacuum.living_room_roomba`
and `vacuum.toms_office_roomba`:

| Trigger ID | Condition | Action |
|---|---|---|
| `create` | `bin_full` becomes `true` | Announce through `script.annouce` with `speak: false` |
| `dismiss` | `bin_full` becomes `false` | Dismiss through `script.cancel_announce` |

The title is `{{ trigger.to_state.attributes.friendly_name }} Bin Full`. Because the
`notification_id` comes from the title, each vacuum gets its own persistent notification from
one shared automation.

A Roomba with a full bin still accepts a start command. It drives off the dock and returns
within about 30 seconds with `cleaning_time: 0`, so the morning routine appears to run and
nothing is cleaned. This automation and the bin-full styling in
[dashboards.md](dashboards.md#vacuum-bin-full-tiles) surface the cause.

`vacuum.kitchen_vacuum` is a Deebot with no `bin_full` attribute, so the automation and the
dashboard styling leave it out.
