# Notifications

## Announce Scripts

### `script.annouce`

Delivers a message to the house. Accepts `title`, `message`, and optional `important` and `persistent` fields. Actions:
1. Temporarily lowers Tom's office speaker volume if it is playing
2. Speaks the message via ChimeTTS to the selected notification players (time-gated: 06:00–23:00, or always if `important: true`)
3. Creates a persistent notification in the HA UI, unless `persistent: false` (default `true`) — `notification_id` is derived from `title | slugify` so it can be addressed for later dismissal

#### Notification player selection

`media_player.notification_players` (a media player group helper) is the master list of candidate speakers. Each member has a matching toggle named `input_boolean.{player_slug}_notifications` (e.g. `media_player.kitchen_display` → `input_boolean.kitchen_display_notifications`); the script's `notification_targets` variable computes the TTS targets as *group members whose toggle is on*, and the TTS step is skipped entirely if none are selected. The toggles are controlled from the Broadcast view on the Settings dashboard.

**Group members must be the native integration entity** for each speaker (e.g. the `apple_tv`, `esphome`, `linkplay`, `fully_kiosk`, or `unifiprotect` entity) — **not** the Music Assistant proxy, even for a device that also has a Music Assistant entity. This is the opposite of the dashboard convention, which uses the Music Assistant entity for the same device (see the "Media player rule" in [@dashboards.md](dashboards.md)). The `{player_slug}` in the toggle name is therefore derived from the *native* entity ID (e.g. `media_player.master_bedroom_homepod_mini` → `input_boolean.master_bedroom_homepod_mini_notifications`).

When adding a player to the group, also create its `input_boolean.{player_slug}_notifications` toggle (display name `Notifications`, assigned to the player's area, turned on) and add it to the Broadcast view's Notification Players card — a group member without a toggle is never announced to, because its toggle lookup resolves to a non-existent entity.

### `script.broadcast`

Backs the Broadcast view on the Settings dashboard. Guards against an empty `input_text.broadcast_message`, calls `script.annouce` with the box's contents (`title: Broadcast`, `important: true`, `persistent: false`), then clears the box.

### `script.cancel_announce`

Dismisses a persistent notification previously created by `script.annouce`. Accepts a `title` field and calls `persistent_notification.dismiss` using the same `title | slugify` convention. Automations call this script on their dismiss trigger rather than calling the service directly.

---

## Pattern

Each appliance uses the same structure: an `input_select` state helper decouples device events from notification. One automation manages all state transitions; a second reacts to state changes and delivers or dismisses alerts. All state automations run in `restart` mode — a new trigger interrupts any in-progress run, so late-arriving events are never queued or dropped.

---

## Tumble Dryer Automation

---

### Helper: Tumble Dryer State

| Field | Value |
|---|---|
| Entity ID | `input_select.tumble_dryer_state` |
| Type | `input_select` |
| Options | `idle`, `active`, `finished` |
| Initial | `idle` |

Tracks the current phase of a drying cycle.

---

### Automation: Tumble Dryer State (`automation.tumble_dryer_state`)

Manages all transitions of the `tumble_dryer_state` helper. Triggered by three events:

| Trigger ID | Source | Event |
|---|---|---|
| `start` | `sensor.dryer_bsh_common_status_operationstate` | Operation state → `Run` |
| `finished` | `event.dryer_laundrycare_dryer_event_dryingprocessfinished` | `event_type` attribute → `Present` |
| `door_open` | `event.dryer_laundrycare_common_event_dooropen` | `event_type` attribute → `Present` |

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
| Initial | `Absent` |

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
| Initial | `idle` |

Tracks the current phase of a wash cycle.

---

### Automation: Washing Machine State (`automation.washing_machine_state`)

Manages all transitions of the `washing_machine_state` helper. Triggered by two sources:

| Trigger ID | Source | Event |
|---|---|---|
| `power_change` | `sensor.basement_washing_machine_smart_switch_power` | Any power reading change |
| `door_open` | `binary_sensor.0x00158d008c7104b7_contact` | Door opens (state → `on`) |

#### Transition logic

Each branch guards on the current state before acting, so spurious triggers are ignored:

**`power_change` trigger, power > 1W** — only if current state is `idle`:
- Sets state → `running`

**`power_change` trigger, power ≤ 1W** — only if current state is `running`:
- Waits 10 minutes, then sets state → `finished`

**`door_open` trigger** — only if current state is `finished`:
- Sets state → `idle`

Runs in `restart` mode — power fluctuations during the 10-minute wait restart the clock. The machine must sustain low power for a full uninterrupted 10 minutes before the state advances to `finished`.

---

### Automation: Washing Machine Notification (`automation.notify_on_washing_machine_has_finished`)

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
| `create` | `bin_full` → `true` | Announce via `script.annouce` |
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

